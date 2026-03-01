"""
Authentication router — Google OAuth flow, JWT issuance, and user profile.
"""

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import AuthenticationError
from app.middleware.auth_dependency import AuthenticatedUser, get_current_user
from app.middleware.request_id import get_request_id
from app.schemas.auth import TokenResponse, UserProfile
from app.services.auth_service import (
    create_jwt_token,
    find_or_create_user,
    oauth,
)

logger = structlog.get_logger("nexusapi.auth_router")
router = APIRouter(prefix="/auth", tags=["Authentication"])
me_router = APIRouter(tags=["User"])


@router.get("/google")
async def google_login(request: Request):
    """
    Initiate Google OAuth flow.
    Redirects the user to Google's consent screen.
    """
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, str(redirect_uri))


@router.get("/callback")
async def google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Google OAuth callback.
    Exchanges the authorization code for user info, creates/finds the user
    and organisation, and returns a signed JWT.
    """
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        logger.error("google_oauth_failed", error=str(e))
        return JSONResponse(
            status_code=401,
            content={
                "error": "authentication_error",
                "message": "Google authentication failed. Please try again.",
                "request_id": get_request_id(),
            },
        )

    user_info = token.get("userinfo")
    if not user_info:
        return JSONResponse(
            status_code=401,
            content={
                "error": "authentication_error",
                "message": "Could not retrieve user information from Google.",
                "request_id": get_request_id(),
            },
        )

    email = user_info.get("email")
    name = user_info.get("name", email.split("@")[0])
    google_id = user_info.get("sub")

    if not email or not google_id:
        return JSONResponse(
            status_code=401,
            content={
                "error": "authentication_error",
                "message": "Invalid user information from Google.",
                "request_id": get_request_id(),
            },
        )

    # Find or create user + organisation
    user = await find_or_create_user(db, email, name, google_id)
    await db.commit()

    # Issue JWT
    access_token, expires_in = create_jwt_token(user)

    # Redirect to Next.js frontend with the token
    frontend_callback = f"http://localhost:3000/auth/callback?token={access_token}"
    return RedirectResponse(frontend_callback)


@me_router.get("/me", response_model=UserProfile, name="get_current_user_profile")
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the authenticated user's profile and organisation details.
    """
    user = current_user._user

    return UserProfile(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        organisation_id=user.organisation_id,
        organisation_name=user.organisation.name if user.organisation else "",
        organisation_slug=user.organisation.slug if user.organisation else "",
        created_at=user.created_at,
    )
