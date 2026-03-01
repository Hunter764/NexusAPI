"""
Credit management router — grant credits and check balance.
"""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_dependency import AuthenticatedUser, get_current_user, require_admin
from app.schemas.credits import CreditGrantRequest, CreditBalanceResponse, TransactionItem
from app.services import credit_service

logger = structlog.get_logger("nexusapi.credits_router")
router = APIRouter(prefix="/credits", tags=["Credits"])


@router.post("/grant")
async def grant_credits(
    request: CreditGrantRequest,
    current_user: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Grant credits to the organisation (admin only).

    Adds credits to the organisation's ledger. Only admins can perform this action.
    """
    transaction = await credit_service.grant_credits(
        db=db,
        organisation_id=current_user.organisation_id,
        user_id=current_user.id,
        amount=request.amount,
        reason=request.reason,
    )

    balance = await credit_service.get_balance(db, current_user.organisation_id)

    return {
        "message": f"Granted {request.amount} credits",
        "transaction_id": str(transaction.id),
        "new_balance": balance,
    }


@router.get("/balance", response_model=CreditBalanceResponse)
async def get_balance(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the organisation's current credit balance and last 10 transactions.
    """
    balance = await credit_service.get_balance(db, current_user.organisation_id)
    transactions = await credit_service.get_recent_transactions(
        db, current_user.organisation_id, limit=10
    )

    return CreditBalanceResponse(
        organisation_id=current_user.organisation_id,
        balance=balance,
        recent_transactions=[
            TransactionItem(
                id=t.id,
                amount=t.amount,
                reason=t.reason,
                user_id=t.user_id,
                idempotency_key=t.idempotency_key,
                created_at=t.created_at,
            )
            for t in transactions
        ],
    )
