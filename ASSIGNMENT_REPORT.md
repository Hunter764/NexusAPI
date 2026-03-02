# NexusAPI — End-to-End Assignment Report

This document outlines the complete end-to-end implementation of the NexusAPI backend, following the strict requirements of the Kasparro AI Backend Engineering assignment.

The system is built with **FastAPI**, **async SQLAlchemy**, **PostgreSQL**, and **Redis**, fully dockerized and structured for production scale.

---

## Tier 1 — Core Backend

### R1: Project Setup
The project structure enforces a clear separation of concerns across `models/`, `schemas/`, `routers/`, `services/`, and `middleware/`. 

All configuration is loaded via `pydantic-settings` from environment variables, ensuring zero hardcoded secrets. 

**Execution:**
```bash
# Boot the surrounding infrastructure (Postgres + Redis)
docker-compose up -d

# Run the FastAPI server
uvicorn app.main:app --reload
```

**Health Check endpoint (`/health`):**
We implemented an active health check that executes a `SELECT 1` query against the database. If it fails, it returns a `503 Service Unavailable`.
```python
@router.get("/health", status_code=200)
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unreachable")
```

### R2: Database Schema
We utilized `uuid` primary keys across all tables and established foreign key relationships. We manage all schema versioning strictly through **Alembic** migrations.

**Reasoning: Why no balance column?**
The current balance is dynamically derived by `SUM(amount)` from the `CreditTransactions` table.
*Reasoning:* Using a pure transaction ledger guarantees a perfect, immutable audit trail. A mutable integer column is highly susceptible to race conditions (lost updates) and data drift. If a dispute arises over billing, a ledger allows us to cryptographically prove exactly where every single credit went.

### R3 & R4: Google OAuth and JWT Middleware
Authentication is handled entirely via Google OAuth2, meaning NexusAPI stores no passwords.

**Implementation Steps:**
1. `GET /auth/google` redirects the user to the official Google consent screen using our `.env` Client ID.
2. `GET /auth/callback` catches the returning Google code, swaps it for an identity payload, and upserts the `Organisation` (based on email domain) and `User` records.
3. We sign a stateless JWT containing the `user_id`, `organisation_id`, and `role`, valid for 24 hours.

**JWT Middleware:**
We created a FastAPI `Depends` dependency that intercepts protected routes. It verifies the HS256 signature, asserts expiration, and extracts the `organisation_id`. 
*Security boundary:* By injecting the `organisation_id` directly from the cryptographic token into the route context, we completely eradicate Insecure Direct Object Reference (IDOR) vulnerabilities. Users physically cannot query data for an organisation ID they don't own, because the ID is strictly pulled from their signed token.

### R5: Credit System (Simultaneous Deductions)
The core of the billing engine is the `deduct_credits` service.

**Handling Concurrent Deductions:**
What happens if `deduct_credits` is called twice simultaneously for an organisation with exactly enough credits for one call?
*Implementation:* We utilized **PostgreSQL Transaction-level Advisory Locks** (`pg_advisory_xact_lock`). 
When a deduction begins, it acquires an exclusive lock hashed to the `organisation_id`. The second simultaneous request is forced to wait. Once the first request inserts its negative transaction line item and commits (releasing the lock), the second request acquires the lock, recalculates the `SUM(amount)`, sees the balance is now 0, and immediately rejects the request with an `InsufficientCreditsError` (HTTP 402). 

---

## Tier 2 — Product Endpoints and Failure Handling

### R6: Synchronous Endpoint (`/api/analyse`)
Costs 25 credits. It deducts the credits *before* executing the NLP workload.

**Failure Handling (Credit Refunds):**
If the deduction succeeds but the NLP processing crashes, the user loses credits for nothing. To prevent this, our endpoint wraps the deduction and processing in a distinct `try/except` block. If the processing throws an exception, the `except` block automatically triggers a `refund_credits` service call, inserting a `+25` transaction into the ledger titled "Refund: Analysis failed", before bubbling up the 500 error to the user.

### R7: Asynchronous Endpoint (`/api/summarise`)
Costs 10 credits. Since summarization of a 2000-character string can be slow, this endpoint returns a `job_id` instantly (< 200ms) and offloads the work.

**Implementation:**
We used **ARQ** (Async Redis Queue). 
1. The user hits `/api/summarise`, we deduct 10 credits and insert a `Job` row into Postgres with status `PENDING`.
2. We enqueue the job to Redis.
3. The user polls `GET /api/jobs/{job_id}`. 
4. The background ARQ Python worker picks up the job from Redis, executes the summarization, and updates the Postgres `Job` row status to `COMPLETED` along with the JSON payload result. 

**Stuck Jobs:**
If the ARQ worker crashes mid-execution, the exception block inside the background worker safely catches the error, marks the Postgres job as `FAILED`, and automatically issues a `+10` refund transaction to the organisation!

### R8: Rate Limiting
We implemented a Redis-backed Sliding Window rate limiter middleware that intercepts every request and tracks against a generic `rate_limit:{organisation_id}` key. Max: 60 rpm. 
Rejections return `HTTP 429 Too Many Requests` with a `Retry-After` header.

**Fail-open Strategy:**
If Redis goes down, our custom highly-available middleware executes a `try/except` around the Redis ping. If it throws a `ConnectionError`, it logs a warning via Structlog and **fails open** (allows the request through). 
*Reasoning:* Rate limiting is a protective layer, not a core business function. It is better to temporarily accept a slightly higher load than to accidentally take the entire API offline for paying customers just because a secondary caching server restarted.

### R9: Structured Logging and Error Handling
We integrated **Structlog** to output JSON-formatted logs instead of plaintext.
- We injected a `Request-ID` middleware that generates a UUID for every incoming HTTP request.
- Using `structlog.contextvars`, we bind the `request_id`, `organisation_id`, and `duration_ms` to the thread. Every single log emitted during that request automatically appends those trace identifiers.
- A global exception handler ensures 500 errors never leak Python stack traces, returning a safe, sanitized generic JSON response containing the `request_id` for support tickets.

---

## Tier 3 — Idempotency

### R10: Idempotent Credit Deduction
Handling network retries gracefully is the hardest part of billing APIs. If a mobile client loses connection while waiting for a response, they will retry the exact same `POST /api/analyse` request. 

**Implementation (The Double-Lock Strategy):**
We require the client to pass an `Idempotency-Key` header. 
1. **Application Layer (Fast Path):** When the request starts, we check the `IdempotencyRecords` table. If the key exists within 24 hours, we instantly return the cached JSON response. No credits deducted.
2. **Database Layer (The Safety Net):** If the key is new, two *simultaneous* identical requests could bypass the application read check at the exact same millisecond. To solve this race condition, we added a `UNIQUE` index constraint on the Postgres `IdempotencyRecord.idempotency_key` column. 
3. When both parallel threads attempt to `INSERT` the final result with that idempotency key at the end of the transaction, the Postgres unique constraint physically rejects the slower thread with an `IntegrityError`, rolling back its transaction and preventing double-billing at the strictest database level. 
