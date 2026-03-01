"""
Authentication-related schemas.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class TokenResponse(BaseModel):
    """JWT token response returned after successful authentication."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserProfile(BaseModel):
    """User profile with organisation details — returned by GET /me."""
    id: uuid.UUID
    email: str
    name: str
    role: str
    organisation_id: uuid.UUID
    organisation_name: str
    organisation_slug: str
    created_at: datetime

    model_config = {"from_attributes": True}
