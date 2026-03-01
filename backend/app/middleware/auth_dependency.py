"""
JWT authentication dependency for FastAPI.
Validates JWT tokens and enforces tenant isolation.
"""

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.exceptions import AuthenticationError, AuthorizationError
from app.models.user import User, UserRole

logger = structlog.get_logger("nexusapi.auth")

# HTTP Bearer scheme — auto-extracts token from Authorization header
security = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """Represents the currently authenticated user within a request."""

    def __init__(self, user: User):
        self.id = user.id
        self.email = user.email
        self.name = user.name
        self.role = user.role
        self.organisation_id = user.organisation_id
        self._user = user

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedUser:
    """
    FastAPI dependency that validates the JWT token and returns the
    authenticated user. Enforces that the user still exists in the database.

    Raises:
        AuthenticationError: If token is missing, expired, or invalid.
    """
    if credentials is None:
        raise AuthenticationError("Authorization header is missing")

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as e:
        logger.warning("jwt_validation_failed", error=str(e))
        raise AuthenticationError("Token is invalid or expired")

    # Check expiry
    exp = payload.get("exp")
    if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
        raise AuthenticationError("Token has expired")

    user_id = payload.get("user_id")
    if not user_id:
        raise AuthenticationError("Invalid token payload")

    # Verify user still exists in the database
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise AuthenticationError("Invalid token payload")

    result = await db.execute(
        select(User)
        .options(selectinload(User.organisation))
        .where(User.id == user_uuid)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError(
            "User no longer exists. Token is no longer valid."
        )

    # Store org/user IDs in request state for logging middleware
    request.state.user_id = user.id
    request.state.organisation_id = user.organisation_id

    return AuthenticatedUser(user)


async def require_admin(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """
    FastAPI dependency that requires the user to have admin role.

    Raises:
        AuthorizationError: If the user is not an admin.
    """
    if not current_user.is_admin:
        raise AuthorizationError(
            "This action requires admin privileges"
        )
    return current_user
