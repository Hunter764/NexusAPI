"""
Custom exceptions for NexusAPI.
All exceptions are mapped to structured error responses in the global handlers.
"""


class NexusAPIError(Exception):
    """Base exception for all NexusAPI errors."""

    def __init__(self, message: str, error_code: str, status_code: int = 500):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(self.message)


class InsufficientCreditsError(NexusAPIError):
    """Raised when an organisation doesn't have enough credits."""

    def __init__(self, balance: int, required: int):
        self.balance = balance
        self.required = required
        super().__init__(
            message=f"Insufficient credits. Balance: {balance}, required: {required}",
            error_code="insufficient_credits",
            status_code=402,
        )


class OrganisationAccessDenied(NexusAPIError):
    """Raised when accessing another organisation's data."""

    def __init__(self):
        super().__init__(
            message="Access to this resource is denied",
            error_code="access_denied",
            status_code=403,
        )


class ResourceNotFoundError(NexusAPIError):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} with id '{resource_id}' not found",
            error_code="not_found",
            status_code=404,
        )


class AuthenticationError(NexusAPIError):
    """Raised for authentication failures."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            error_code="authentication_error",
            status_code=401,
        )


class AuthorizationError(NexusAPIError):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            error_code="forbidden",
            status_code=403,
        )


class RateLimitExceededError(NexusAPIError):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(
            message=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            error_code="rate_limit_exceeded",
            status_code=429,
        )


class ValidationError(NexusAPIError):
    """Raised for input validation failures."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="validation_error",
            status_code=422,
        )
