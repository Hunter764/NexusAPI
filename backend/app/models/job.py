"""
Job model — tracks async background job status and results.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Enum, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobStatus(str, enum.Enum):
    """Possible states of a background job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

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
    type: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    input_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", create_constraint=True),
        default=JobStatus.PENDING,
        nullable=False,
    )
    result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    error: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    credits_deducted: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organisation = relationship("Organisation", back_populates="jobs")
    user = relationship("User", lazy="selectin")

    __table_args__ = (
        Index("ix_jobs_organisation_id", "organisation_id"),
        Index("ix_jobs_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Job(id={self.id}, type='{self.type}', status={self.status})>"
        )
