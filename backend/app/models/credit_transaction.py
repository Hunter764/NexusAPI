"""
CreditTransaction model — append-only ledger for credit tracking.

The current balance is always derived from SUM(amount) for an organisation.
No separate balance column exists. This ensures:
- Full auditability of every credit change
- No lost updates from concurrent modifications
- Easy reconciliation and dispute resolution
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organisation = relationship("Organisation", back_populates="credit_transactions")
    user = relationship("User", lazy="selectin")

    __table_args__ = (
        Index("ix_credit_transactions_org_id", "organisation_id"),
        Index(
            "ix_credit_transactions_org_created",
            "organisation_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CreditTransaction(id={self.id}, org={self.organisation_id}, "
            f"amount={self.amount}, reason='{self.reason}')>"
        )
