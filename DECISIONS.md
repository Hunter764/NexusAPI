# DECISIONS.md — NexusAPI Design Decision Log

## Question 1: Why does the credit system use a transaction ledger instead of a balance column?

The credit system in NexusAPI stores every credit change as a row in the CreditTransactions table rather than maintaining a mutable balance column on the organisations table. The current balance is derived at read time by computing SUM(amount) across all transactions for a given organisation. This design was chosen for three specific reasons.

First, auditability. A balance column tells you what the current number is, but it does not tell you how you got there. In any system where credits have monetary or operational value, the ability to reconstruct the exact sequence of events — who granted credits, when, why, and which API call consumed them — is essential. The ledger provides a complete, immutable audit trail without any additional infrastructure.

Second, correctness under concurrency. A mutable balance column is susceptible to lost updates. If two requests read the balance simultaneously, both see 50 credits, both deduct 25, and both write 25 back, the organisation has effectively received two services for the price of one. The ledger approach sidesteps this entirely because each deduction is an INSERT operation, not an UPDATE to a shared row. Combined with the advisory lock strategy described below, this guarantees that credits are never double-spent.

Third, reconciliation. If a dispute arises — a customer claims they were charged incorrectly — the ledger provides the raw data to investigate. With a balance column, you would need separate logging to achieve the same capability, which duplicates state and introduces the risk of the log and balance diverging.

The tradeoff is read performance. Computing SUM across potentially thousands of rows is slower than reading a single column. For the current scale this is negligible, but at higher volumes I would add a materialised balance cache that is updated transactionally alongside each ledger entry — effectively getting the best of both approaches while keeping the ledger as the source of truth.

## Question 2: How did you handle the simultaneous credit deduction problem?

When two requests arrive simultaneously for the same organisation, each requiring 25 credits and the organisation has exactly 25, the system must ensure only one succeeds. My implementation uses PostgreSQL advisory locks via pg_advisory_xact_lock.

When deduct_credits is called, the first thing it does — before checking the balance — is acquire a transaction-scoped advisory lock keyed to the organisation's UUID. This lock is exclusive: if a second request for the same organisation calls deduct_credits while the first is still in its transaction, the second request blocks at the lock acquisition until the first transaction either commits or rolls back.

The flow for the two simultaneous requests is: Request A acquires the advisory lock, reads the balance as 25, confirms 25 >= 25, inserts a negative transaction for -25, and commits. The lock is released automatically at commit. Request B, which has been waiting at the lock, now acquires it, reads the balance as 0 (because Request A's transaction committed), sees 0 < 25, and raises InsufficientCreditsError, returning HTTP 402 to the caller.

I chose advisory locks over SELECT FOR UPDATE because the credit balance is derived from a SUM across multiple rows rather than stored in a single row. SELECT FOR UPDATE would require locking every transaction row for the organisation, which is both awkward and potentially slow. An advisory lock provides a clean, explicit serialisation point scoped to the organisation without coupling to any particular row. The lock is automatically released when the transaction ends, so there is no risk of deadlock from forgetting to release it.

## Question 3: What happens when the background worker fails after credits have been deducted?

When POST /api/summarise is called, credits are deducted immediately and a job record is created with status PENDING and a credits_deducted field recording the amount charged. The job is then enqueued to ARQ for background processing.

If the worker process crashes or the job fails for any reason, the error handler in the worker catches the exception, marks the job as FAILED, records the error message, and immediately issues a refund by inserting a positive credit transaction with a reason like "Refund: summarise job {job_id} failed". This refund appears in the organisation's transaction history and restores their balance.

I chose automatic refund over retry for this assignment because retries introduce complexity around idempotency of the work itself and risk consuming resources repeatedly for a permanently failing input. A refund is simple, auditable, and gives the caller clear feedback: the job failed, credits were returned, they can try again if they choose.

There is an edge case where the worker crashes so hard that even the error handler does not execute — for example, if the process is killed by the operating system. In that case, the job would remain in PENDING or RUNNING status indefinitely. To handle this, a production system would include a stale job detector — a periodic task that scans for jobs stuck in non-terminal states beyond a timeout threshold (such as 5 minutes, which matches the ARQ job_timeout) and marks them as FAILED with an automatic refund. The job model already stores credits_deducted to support this recovery path.

## Question 4: How does your idempotency implementation work, and where does it live?

The idempotency system operates at two levels: the application layer and the database layer, and they work together to handle both normal duplicate requests and simultaneous duplicates.

At the application layer, when a request arrives at /api/analyse or /api/summarise with an Idempotency-Key header, the router first queries the idempotency_records table for a matching record (same key, same organisation, same endpoint, created within the last 24 hours). If found, the original response is returned immediately — no credit deduction, no processing.

If no record exists, the request proceeds normally. The idempotency key is passed into deduct_credits and stored in the credit_transactions table on the resulting deduction row. After the endpoint has completed its work (whether analysis or job creation), the response is saved to the idempotency_records table with the status code and full response body.

At the database layer, the credit_transactions table has a UNIQUE constraint on idempotency_key. This is the critical safety net. If two identical requests arrive simultaneously — before either has completed the application-level check — both will pass the initial query (neither finds a record yet). However, when they both attempt to INSERT a credit transaction with the same idempotency_key, the database's unique constraint will cause exactly one of them to fail with an IntegrityError. The application catches this and returns an appropriate error.

The dual-layer approach is essential because an application-level check alone is not sufficient. Between the moment you query for an existing record and the moment you insert a new one, there is a window where a concurrent request can slip through. The database constraint closes that window completely. This is the same pattern used in real payment systems — the application layer provides the fast path for normal duplicates, and the database constraint provides the safety guarantee for the race condition.

## Question 5: What would break first at 10x the current load, and what would you do about it?

At 10x load, the most likely bottleneck is the credit balance computation. Every call to deduct_credits computes the balance by running SUM(amount) across all credit_transactions rows for an organisation. As the transaction table grows — both from increased request volume and from the accumulated history of a growing organisation — this query becomes progressively slower, and every API call that requires credits depends on it.

The solution is to introduce a cached balance. I would add a credit_balances table with one row per organisation containing a precomputed balance value. This row would be updated transactionally alongside every credit transaction INSERT using a SELECT FOR UPDATE on the balance row within the same database transaction. The advisory lock can be replaced by the row lock on this balance record, which also simplifies the concurrency model. The ledger remains the source of truth for auditing, but the hot path reads from the single-row cache.

Beyond the database, the Redis-backed rate limiter and ARQ job queue would also need attention. I would move to a Redis cluster or Redis Sentinel for high availability, add connection pooling, and consider horizontally scaling the ARQ workers. For the PostgreSQL layer, read replicas could serve the balance check endpoint while writes remain on the primary. Adding a database connection pool like PgBouncer in front of PostgreSQL would also help manage connection overhead at higher concurrency.
