"""
Structured JSON logging middleware using structlog.
Logs every request with: timestamp, method, path, org_id, user_id, status, duration_ms.
"""

import time
import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.request_id import get_request_id

logger = structlog.get_logger("nexusapi.access")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Structured JSON access logging for every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.perf_counter()

        # Extract org/user IDs if available (set by auth middleware)
        org_id = None
        user_id = None

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Try to read org/user from request state (set by auth dependency)
        org_id = getattr(request.state, "organisation_id", None)
        user_id = getattr(request.state, "user_id", None)

        logger.info(
            "request_completed",
            request_id=get_request_id(),
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            organisation_id=str(org_id) if org_id else None,
            user_id=str(user_id) if user_id else None,
            client_host=request.client.host if request.client else None,
        )

        return response


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for JSON structured logging."""
    import logging

    level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
