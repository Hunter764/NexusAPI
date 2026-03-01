"""
Request ID middleware — generates a unique UUID for every request.
The request_id is stored in request.state and added to response headers.
"""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Context variable for accessing request_id anywhere in the async call chain
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Adds a unique request_id to every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rid = str(uuid.uuid4())
        request.state.request_id = rid
        token = request_id_ctx.set(rid)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_ctx.reset(token)


def get_request_id() -> str:
    """Retrieve the current request_id from context."""
    return request_id_ctx.get()
