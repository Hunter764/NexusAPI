# NexusAPI — Multi-Tenant Credit-Gated Backend

A production-shaped backend API built with **FastAPI**, **async SQLAlchemy**, **PostgreSQL**, **Redis**, and **ARQ**. The system supports multi-tenant isolation, credit-gated access, background job processing, rate limiting, and idempotent credit operations.

---

## Project Structure

```text
NexusAPI/
├── backend/                  # FastAPI Application
│   ├── app/                  # Application code (routers, services, models)
│   ├── migrations/           # Alembic database migrations
│   ├── tests/                # Pytest suite
│   ├── requirements.txt      # Python dependencies
│   ├── alembic.ini           # Alembic configuration
│   ├── Dockerfile            # Backend container definition
│   └── pytest.ini            # Pytest configuration
├── frontend/                 # Next.js Application
│   ├── app/                  # Next.js App Router (dashboard, auth)
│   ├── components/           # React components (shadcn/ui)
│   ├── lib/                  # Utilities and styling helpers
│   ├── public/               # Static assets
│   ├── package.json          # Node dependencies
│   ├── tailwind.config.ts    # Tailwind CSS configuration
│   └── next.config.mjs       # Next.js configuration
├── docker-compose.yml        # PostgreSQL + Redis for local dev
├── .env.example              # Environment variables template
├── .gitignore
├── README.md
└── DECISIONS.md
```

---

## Setup Instructions

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for PostgreSQL and Redis)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/NexusAPI.git
cd NexusAPI
```

### 2. Start Infrastructure (PostgreSQL + Redis)

```bash
docker-compose up -d
```

### 3. Backend Setup (FastAPI)

Open a new terminal and navigate to the `backend` directory:

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your actual values (Google OAuth, JWT secret, etc.)

# Run database migrations
alembic upgrade head

# Start the application server (runs on http://localhost:8000)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Background Worker Setup (ARQ)

In a separate terminal within the `backend` directory:

```bash
cd backend
source venv/bin/activate
arq app.worker.WorkerSettings
```

### 5. Frontend Setup (Next.js)

Open another terminal and navigate to the `frontend` directory:

```bash
cd frontend
npm install

# Start the Next.js development server (runs on http://localhost:3000)
npm run dev
```

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Health check (200 or 503) |
| `GET` | `/auth/google` | None | Start Google OAuth flow |
| `GET` | `/auth/callback` | None | Handle OAuth callback, return JWT |
| `GET` | `/me` | JWT | Get authenticated user profile |
| `GET` | `/credits/balance` | JWT | Get org credit balance + last 10 txns |
| `POST` | `/credits/grant` | Admin | Add credits: `{ amount, reason }` |
| `POST` | `/api/analyse` | JWT | Sync analysis, costs 25 credits |
| `POST` | `/api/summarise` | JWT | Async summarise, costs 10 credits |
| `GET` | `/api/jobs/{job_id}` | JWT | Poll job status |

---

## Example API Calls

### 1. Health check

```bash
curl http://localhost:8000/health
```

**Response (200):**
```json
{
  "status": "healthy",
  "database": "connected"
}
```

### 2. Grant credits (requires admin JWT)

```bash
curl -X POST http://localhost:8000/credits/grant \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "reason": "Initial credit allocation"}'
```

**Response (200):**
```json
{
  "message": "Granted 100 credits",
  "transaction_id": "a1b2c3d4-...",
  "new_balance": 100
}
```

### 3. Analyse text (costs 25 credits)

```bash
curl -X POST http://localhost:8000/api/analyse \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"text": "The quick brown fox jumps over the lazy dog. This is a sample text for analysis."}'
```

**Response (200):**
```json
{
  "result": "Analysis complete. Word count: 17. Unique words: 15.",
  "credits_remaining": 75
}
```

### 4. Summarise text (async, costs 10 credits)

```bash
curl -X POST http://localhost:8000/api/summarise \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: unique-request-123" \
  -d '{"text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. This is a longer text."}'
```

**Response (200):**
```json
{
  "job_id": "f7e8d9c0-...",
  "status": "pending",
  "credits_remaining": 65
}
```

### 5. Poll job status

```bash
curl http://localhost:8000/api/jobs/f7e8d9c0-... \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

**Response (200):**
```json
{
  "job_id": "f7e8d9c0-...",
  "status": "completed",
  "result": {
    "summary": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
    "original_word_count": 13,
    "summary_word_count": 8
  },
  "created_at": "2025-01-01T00:00:00Z",
  "completed_at": "2025-01-01T00:00:02Z"
}
```

---

## Running Tests

```bash
cd backend
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_credits.py -v
```

---

## Deployment

### Docker

```bash
docker build -t nexusapi .
docker run -p 8000:8000 --env-file .env nexusapi
```

### Railway / Render / Fly.io

1. Push to GitHub
2. Connect the repository on your hosting platform
3. Set environment variables in the platform dashboard
4. Configure the start command: `gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`
5. Add a PostgreSQL and Redis addon
6. Run `alembic upgrade head` as a release command
