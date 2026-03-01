"""
Organisation model — the top-level tenant entity.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    users = relationship("User", back_populates="organisation", lazy="selectin")
    credit_transactions = relationship(
        "CreditTransaction", back_populates="organisation", lazy="noload"
    )
    jobs = relationship("Job", back_populates="organisation", lazy="noload")

    def __repr__(self) -> str:
        return f"<Organisation(id={self.id}, name='{self.name}', slug='{self.slug}')>"
