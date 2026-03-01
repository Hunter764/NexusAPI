"""
Credit-related schemas.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreditGrantRequest(BaseModel):
    """Request body for granting credits to an organisation."""
    amount: int = Field(..., gt=0, description="Number of credits to grant (positive integer)")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for the credit grant")


class TransactionItem(BaseModel):
    """A single credit transaction record."""
    id: uuid.UUID
    amount: int
    reason: str
    user_id: uuid.UUID | None
    idempotency_key: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreditBalanceResponse(BaseModel):
    """Response for GET /credits/balance with current balance and recent transactions."""
    organisation_id: uuid.UUID
    balance: int
    recent_transactions: list[TransactionItem]
