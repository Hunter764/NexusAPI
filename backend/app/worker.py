"""
ARQ background worker for processing async jobs.

Handles the summarise job, updates job status, and refunds credits on failure.
"""

import asyncio
import uuid

import structlog
from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.job import Job, JobStatus
from app.models.organisation import Organisation
from app.models.user import User
from app.services.analysis_service import summarise_text
from app.services import credit_service

logger = structlog.get_logger("nexusapi.worker")


async def process_summarise_job(ctx: dict, job_id: str) -> None:
    """
    Process a summarise job in the background.

    1. Mark job as RUNNING
    2. Perform summarisation
    3. Mark job as COMPLETED with result
    4. On failure: mark as FAILED and refund credits
    """
    logger.info("worker_job_started", job_id=job_id)

    async with async_session_factory() as db:
        try:
            # Fetch the job
            result = await db.execute(
                select(Job).where(Job.id == uuid.UUID(job_id))
            )
            job = result.scalar_one_or_none()

            if job is None:
                logger.error("worker_job_not_found", job_id=job_id)
                return

            # Mark as running
            job.status = JobStatus.RUNNING
            await db.commit()

            # Simulate async processing with a small delay
            await asyncio.sleep(2)

            # Perform the summarisation
            text = job.input_data.get("text", "")
            summary_result = summarise_text(text)

            # Mark as completed
            job.status = JobStatus.COMPLETED
            job.result = summary_result
            from datetime import datetime, timezone
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "worker_job_completed",
                job_id=job_id,
                org_id=str(job.organisation_id),
            )

        except Exception as e:
            logger.error(
                "worker_job_failed",
                job_id=job_id,
                error=str(e),
            )

            # Mark job as failed and refund credits
            try:
                result = await db.execute(
                    select(Job).where(Job.id == uuid.UUID(job_id))
                )
                job = result.scalar_one_or_none()

                if job and job.status != JobStatus.COMPLETED:
                    job.status = JobStatus.FAILED
                    job.error = f"Processing failed: {str(e)}"
                    from datetime import datetime, timezone
                    job.completed_at = datetime.now(timezone.utc)

                    # Refund credits for the failed job
                    if job.credits_deducted > 0:
                        await credit_service.refund_credits(
                            db=db,
                            organisation_id=job.organisation_id,
                            amount=job.credits_deducted,
                            reason=f"Refund: summarise job {job_id} failed",
                        )

                    await db.commit()
                    logger.info(
                        "worker_credits_refunded",
                        job_id=job_id,
                        amount=job.credits_deducted,
                    )
            except Exception as refund_error:
                logger.error(
                    "worker_refund_failed",
                    job_id=job_id,
                    error=str(refund_error),
                )
                await db.rollback()


async def startup(ctx: dict) -> None:
    """Worker startup — initialise resources."""
    logger.info("arq_worker_started")


async def shutdown(ctx: dict) -> None:
    """Worker shutdown — cleanup resources."""
    logger.info("arq_worker_stopped")


def get_redis_settings() -> RedisSettings:
    """Parse REDIS_URL into ARQ RedisSettings."""
    from urllib.parse import urlparse
    parsed = urlparse(settings.REDIS_URL)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


# ARQ worker configuration
class WorkerSettings:
    """ARQ worker settings."""
    functions = [process_summarise_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 300  # 5 minutes
    health_check_interval = 30
