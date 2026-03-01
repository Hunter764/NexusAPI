"""
Credit service — manages credit balance, grants, and deductions.

Key design decisions:
- Balance is derived from SUM(amount) on the transaction ledger — no separate column.
- Deductions use PostgreSQL advisory locks (pg_advisory_xact_lock) for atomicity.
  This prevents double-spend when two concurrent requests target the same organisation.
- All operations record full audit trail via CreditTransaction rows.
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_transaction import CreditTransaction
from app.exceptions import InsufficientCreditsError

logger = structlog.get_logger("nexusapi.credit_service")


async def get_balance(db: AsyncSession, organisation_id: uuid.UUID) -> int:
    """
    Get the current credit balance for an organisation.
    Computed as SUM(amount) from the credit_transactions ledger.
    """
    result = await db.execute(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.organisation_id == organisation_id
        )
    )
    return result.scalar_one()


async def get_recent_transactions(
    db: AsyncSession, organisation_id: uuid.UUID, limit: int = 10
) -> list[CreditTransaction]:
    """Get the most recent transactions for an organisation."""
    result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.organisation_id == organisation_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def grant_credits(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
) -> CreditTransaction:
    """
    Add credits to an organisation's balance.
    Records a positive transaction in the ledger.
    """
    transaction = CreditTransaction(
        organisation_id=organisation_id,
        user_id=user_id,
        amount=amount,
        reason=reason,
    )
    db.add(transaction)
    await db.flush()

    new_balance = await get_balance(db, organisation_id)
    logger.info(
        "credits_granted",
        org_id=str(organisation_id),
        amount=amount,
        new_balance=new_balance,
        reason=reason,
    )

    return transaction


async def deduct_credits(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    idempotency_key: str | None = None,
) -> tuple[CreditTransaction, int]:
    """
    Atomically deduct credits from an organisation's balance.

    Uses PostgreSQL advisory locks to prevent race conditions:
    1. Acquire an advisory lock scoped to this organisation (using org UUID hash)
    2. Check current balance >= amount
    3. Insert negative transaction
    4. Release lock (automatic at transaction commit)

    Args:
        db: Database session (must be within a transaction)
        organisation_id: Target organisation UUID
        user_id: User performing the action
        amount: Credits to deduct (positive integer, stored as negative)
        reason: Reason for the deduction
        idempotency_key: Optional key to prevent duplicate deductions

    Returns:
        Tuple of (CreditTransaction, remaining_balance)

    Raises:
        InsufficientCreditsError: If balance < amount
    """
    if amount <= 0:
        raise ValueError("Deduction amount must be positive")

    # Acquire advisory lock based on org ID to serialize deductions per org.
    # pg_advisory_xact_lock is released automatically at the end of the transaction.
    # We use the hash of the UUID to get an int8 for the advisory lock.
    # Note: Advisory locks are PostgreSQL-specific; skipped for other dialects (e.g. SQLite in tests).
    dialect = db.bind.dialect.name if db.bind else "postgresql"
    if dialect == "postgresql":
        lock_id = hash(str(organisation_id)) & 0x7FFFFFFFFFFFFFFF  # Positive int64
        await db.execute(text(f"SELECT pg_advisory_xact_lock({lock_id})"))

    # Check current balance
    current_balance = await get_balance(db, organisation_id)
    if current_balance < amount:
        logger.warning(
            "insufficient_credits",
            org_id=str(organisation_id),
            balance=current_balance,
            required=amount,
        )
        raise InsufficientCreditsError(balance=current_balance, required=amount)

    # Insert negative transaction (deduction)
    transaction = CreditTransaction(
        organisation_id=organisation_id,
        user_id=user_id,
        amount=-amount,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    db.add(transaction)
    await db.flush()

    remaining = current_balance - amount
    logger.info(
        "credits_deducted",
        org_id=str(organisation_id),
        amount=amount,
        remaining=remaining,
        reason=reason,
        idempotency_key=idempotency_key,
    )

    return transaction, remaining


async def refund_credits(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    amount: int,
    reason: str,
) -> CreditTransaction:
    """
    Refund credits to an organisation (e.g., after a failed background job).
    Records a positive transaction with a refund reason.
    """
    transaction = CreditTransaction(
        organisation_id=organisation_id,
        user_id=None,  # System-initiated refund
        amount=amount,
        reason=reason,
    )
    db.add(transaction)
    await db.flush()

    new_balance = await get_balance(db, organisation_id)
    logger.info(
        "credits_refunded",
        org_id=str(organisation_id),
        amount=amount,
        new_balance=new_balance,
        reason=reason,
    )

    return transaction
