"""
IdempotencyRecord model — caches responses for idempotent requests.
Records are valid for 24 hours.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    status_code: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    response_body: Mapped[dict] = mapped_column(
        JSON, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        # Unique constraint: one key per org per endpoint
        Index(
            "ix_idempotency_records_key_org_endpoint",
            "key",
            "organisation_id",
            "endpoint",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<IdempotencyRecord(key='{self.key}', org={self.organisation_id}, "
            f"endpoint='{self.endpoint}')>"
        )
