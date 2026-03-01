"""
Development-only routes — seed data, demo token generation.
These routes are ONLY available when APP_ENV=development.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.organisation import Organisation
from app.models.user import User, UserRole
from app.models.credit_transaction import CreditTransaction
from app.services.auth_service import create_jwt_token

router = APIRouter(prefix="/dev", tags=["Development"])


@router.post("/seed")
async def seed_demo_data(db: AsyncSession = Depends(get_db)):
    """
    Create a demo org + admin user + 500 credits.
    Returns a JWT token ready to paste into the dashboard.
    Idempotent — if demo data already exists, just returns the token.
    """
    if settings.APP_ENV != "development":
        return JSONResponse(
            status_code=403,
            content={"error": "This endpoint is only available in development mode."},
        )

    # Check if demo org already exists
    result = await db.execute(
        select(Organisation).where(Organisation.slug == "demo-org")
    )
    org = result.scalar_one_or_none()

    if org is None:
        org = Organisation(
            id=uuid.uuid4(),
            name="Demo Organisation",
            slug="demo-org",
        )
        db.add(org)
        await db.flush()

    # Check if demo user already exists
    result = await db.execute(
        select(User).where(User.email == "admin@demo-org.com")
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            email="admin@demo-org.com",
            name="Demo Admin",
            google_id="google_demo_admin",
            organisation_id=org.id,
            role=UserRole.ADMIN,
        )
        db.add(user)
        await db.flush()

    # Check current balance and top up to 500 if needed
    result = await db.execute(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.organisation_id == org.id
        )
    )
    current_balance = result.scalar_one()

    if current_balance < 500:
        top_up = 500 - current_balance
        txn = CreditTransaction(
            organisation_id=org.id,
            user_id=user.id,
            amount=top_up,
            reason=f"Dev seed: top-up to 500 credits",
        )
        db.add(txn)
        await db.flush()

    await db.commit()

    # Generate JWT
    # Need to reload user with org relationship
    user.organisation = org
    access_token, expires_in = create_jwt_token(user)

    return {
        "message": "Demo data seeded successfully",
        "organisation": org.name,
        "user": user.email,
        "role": user.role.value,
        "balance": 500,
        "access_token": access_token,
        "expires_in": expires_in,
        "instructions": "Copy the access_token and paste it into the dashboard login page.",
    }
