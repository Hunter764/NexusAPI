"""
Authentication service — handles Google OAuth, JWT creation, and user/org management.
"""

import uuid
import re
from datetime import datetime, timezone, timedelta

import structlog
from authlib.integrations.starlette_client import OAuth
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.organisation import Organisation
from app.models.user import User, UserRole

logger = structlog.get_logger("nexusapi.auth_service")

# Configure Google OAuth via Authlib
oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def create_jwt_token(user: User) -> tuple[str, int]:
    """
    Create a signed JWT token for the given user.

    Returns:
        Tuple of (token_string, expires_in_seconds)
    """
    expires_in = settings.JWT_EXPIRY_HOURS * 3600  # Convert to seconds
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)

    payload = {
        "user_id": str(user.id),
        "organisation_id": str(user.organisation_id),
        "role": user.role.value,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),  # Unique token ID
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, expires_in


def extract_domain(email: str) -> str:
    """Extract the domain from an email address."""
    return email.split("@")[1].lower()


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text


async def find_or_create_user(
    db: AsyncSession, email: str, name: str, google_id: str
) -> User:
    """
    Find an existing user by Google ID, or create a new user.
    If no organisation exists for the email domain, create one and
    make the user an admin. Otherwise, add as a member.

    Args:
        db: Database session
        email: User's email from Google
        name: User's display name from Google
        google_id: Google's unique subject ID

    Returns:
        The User model instance
    """
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.google_id == google_id)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        logger.info("user_login", user_id=str(existing_user.id), email=email)
        return existing_user

    # Determine the organisation
    domain = extract_domain(email)
    slug = slugify(domain.split(".")[0])  # Use domain name as org slug base

    # Check if an organisation with this slug/domain already exists
    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug)
    )
    organisation = result.scalar_one_or_none()

    if organisation is None:
        # Create new organisation — user becomes admin
        organisation = Organisation(
            name=domain.split(".")[0].title(),
            slug=slug,
        )
        db.add(organisation)
        await db.flush()  # Get the org ID
        role = UserRole.ADMIN
        logger.info(
            "organisation_created",
            org_id=str(organisation.id),
            slug=slug,
        )
    else:
        # Existing organisation — user becomes member
        role = UserRole.MEMBER

    # Create the user
    user = User(
        email=email,
        name=name,
        google_id=google_id,
        organisation_id=organisation.id,
        role=role,
    )
    db.add(user)
    await db.flush()

    logger.info(
        "user_created",
        user_id=str(user.id),
        email=email,
        role=role.value,
        org_id=str(organisation.id),
    )

    return user
