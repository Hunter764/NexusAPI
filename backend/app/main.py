"""
NexusAPI — FastAPI application factory.

This is the main entry point for the application. It configures:
- Middleware (request ID, logging, CORS)
- Routers (health, auth, credits, API)
- Global exception handlers
- Lifespan management (DB, Redis, ARQ connections)
"""

import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import structlog
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from redis.asyncio import Redis
from redis.asyncio import Redis

from app.config import settings
from app.exceptions import (
    NexusAPIError,
    InsufficientCreditsError,
    RateLimitExceededError,
)
from app.middleware.logging_middleware import LoggingMiddleware, configure_logging
from app.middleware.request_id import RequestIdMiddleware, get_request_id
from app.middleware.rate_limiter import RateLimiter
from app.routers import health, auth, credits, api as api_router, dev

logger = structlog.get_logger("nexusapi.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application lifecycle — initialises and tears down shared resources.
    """
    # Configure structured logging
    configure_logging(settings.LOG_LEVEL)

    # Auto-create tables for SQLite (dev without Alembic)
    if "sqlite" in settings.DATABASE_URL:
        from app.database import engine, Base
        # Import all models
        from app.models.organisation import Organisation  # noqa
        from app.models.user import User  # noqa
        from app.models.credit_transaction import CreditTransaction  # noqa
        from app.models.job import Job  # noqa
        from app.models.idempotency_record import IdempotencyRecord  # noqa
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("sqlite_tables_created")

    # Initialise Redis connection (for rate limiting and ARQ)
    redis_client = None
    arq_pool = None

    try:
        redis_client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        await redis_client.ping()
        logger.info("redis_connected", url=settings.REDIS_URL)
    except Exception as e:
        logger.warning(
            "redis_connection_failed",
            error=str(e),
            detail="Rate limiting and background jobs may be unavailable",
        )
        redis_client = None

    # Initialise ARQ pool for enqueueing jobs
    try:
        from arq import create_pool
        from app.worker import get_redis_settings
        arq_pool = await create_pool(get_redis_settings())
        logger.info("arq_pool_connected")
    except Exception as e:
        logger.warning(
            "arq_pool_connection_failed",
            error=str(e),
            detail="Background job enqueueing may be unavailable",
        )
        arq_pool = None

    # Store shared resources on app state
    app.state.redis = redis_client
    app.state.rate_limiter = RateLimiter(redis_client)
    app.state.arq_pool = arq_pool

    yield

    # Cleanup
    if redis_client:
        await redis_client.close()
    if arq_pool:
        await arq_pool.close()

    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title=settings.APP_NAME,
        description="Multi-tenant credit-gated backend API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # --- Middleware (order matters: outermost first) ---

    # Session middleware for OAuth state management
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.JWT_SECRET_KEY,
    )

    # Structured logging for every request
    app.add_middleware(LoggingMiddleware)

    # Request ID generation
    app.add_middleware(RequestIdMiddleware)

    # --- CORS (for frontend development) ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Routers ---
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(auth.me_router)  # /me at root level
    app.include_router(credits.router)
    app.include_router(api_router.router)
    app.include_router(dev.router)  # /dev/seed — development only

    # --- Global Exception Handlers ---

    @app.exception_handler(NexusAPIError)
    async def nexus_error_handler(request: Request, exc: NexusAPIError):
        """Handle all custom NexusAPI exceptions."""
        content = {
            "error": exc.error_code,
            "message": exc.message,
            "request_id": get_request_id(),
        }

        # Add extra fields for specific error types
        if isinstance(exc, InsufficientCreditsError):
            content["balance"] = exc.balance
            content["required"] = exc.required

        headers = {}
        if isinstance(exc, RateLimitExceededError):
            headers["Retry-After"] = str(exc.retry_after)

        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ):
        """Handle Pydantic/FastAPI validation errors with consistent shape."""
        errors = exc.errors()
        # Build a human-readable message from the validation errors
        messages = []
        for error in errors:
            loc = " -> ".join(str(l) for l in error["loc"])
            messages.append(f"{loc}: {error['msg']}")

        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "; ".join(messages),
                "request_id": get_request_id(),
            },
        )

    @app.exception_handler(Exception)
    async def general_error_handler(request: Request, exc: Exception):
        """
        Catch-all handler — ensures no raw stack traces are ever returned.
        Logs the full error internally but returns a generic message.
        """
        logger.error(
            "unhandled_exception",
            error=str(exc),
            error_type=type(exc).__name__,
            path=request.url.path,
            request_id=get_request_id(),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred. Please try again later.",
                "request_id": get_request_id(),
            },
        )

    return app


# Application instance
app = create_app()
