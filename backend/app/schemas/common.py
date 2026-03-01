"""
Shared schema types used across multiple modules.
"""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Consistent error response shape for all endpoints."""
    error: str
    message: str
    request_id: str
