"""
Job service — manages background job lifecycle.
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.exceptions import ResourceNotFoundError, OrganisationAccessDenied

logger = structlog.get_logger("nexusapi.job_service")


async def create_job(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    user_id: uuid.UUID,
    job_type: str,
    input_data: dict,
    credits_deducted: int,
    idempotency_key: str | None = None,
) -> Job:
    """
    Create a new background job record with PENDING status.
    """
    job = Job(
        organisation_id=organisation_id,
        user_id=user_id,
        type=job_type,
        input_data=input_data,
        status=JobStatus.PENDING,
        credits_deducted=credits_deducted,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    await db.flush()

    logger.info(
        "job_created",
        job_id=str(job.id),
        org_id=str(organisation_id),
        job_type=job_type,
    )

    return job


async def get_job(
    db: AsyncSession,
    job_id: uuid.UUID,
    organisation_id: uuid.UUID,
) -> Job:
    """
    Retrieve a job by ID, enforcing organisation-level access control.

    Raises:
        ResourceNotFoundError: If the job doesn't exist.
        OrganisationAccessDenied: If the job belongs to another organisation.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if job is None:
        raise ResourceNotFoundError("Job", str(job_id))

    if job.organisation_id != organisation_id:
        # Log the access attempt — this is a security event
        logger.warning(
            "cross_org_job_access_attempt",
            job_id=str(job_id),
            job_org_id=str(job.organisation_id),
            requesting_org_id=str(organisation_id),
        )
        raise ResourceNotFoundError("Job", str(job_id))

    return job


async def update_job_status(
    db: AsyncSession,
    job_id: uuid.UUID,
    status: JobStatus,
    result: dict | None = None,
    error: str | None = None,
) -> Job:
    """
    Update a job's status, result, or error.
    Sets completed_at when status is COMPLETED or FAILED.
    """
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()

    if job is None:
        raise ResourceNotFoundError("Job", str(job_id))

    job.status = status
    if result is not None:
        job.result = result
    if error is not None:
        job.error = error
    if status in (JobStatus.COMPLETED, JobStatus.FAILED):
        job.completed_at = datetime.now(timezone.utc)

    await db.flush()

    logger.info(
        "job_status_updated",
        job_id=str(job_id),
        status=status.value,
    )

    return job
