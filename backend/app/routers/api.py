"""
Product API router — analyse (synchronous) and summarise (async) endpoints.
Handles credit gating, idempotency, rate limiting, and failure recovery.
"""

import uuid
from datetime import datetime, timezone, timedelta

import structlog
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session_factory
from app.exceptions import InsufficientCreditsError, ResourceNotFoundError
from app.middleware.auth_dependency import AuthenticatedUser, get_current_user
from app.middleware.rate_limiter import RateLimiter
from app.middleware.request_id import get_request_id
from app.models.idempotency_record import IdempotencyRecord
from app.schemas.api import (
    AnalyseRequest,
    AnalyseResponse,
    SummariseRequest,
    SummariseResponse,
    JobStatusResponse,
)
from app.services import credit_service, job_service
from app.services.analysis_service import analyse_text

logger = structlog.get_logger("nexusapi.api_router")
router = APIRouter(prefix="/api", tags=["API"])

# Credit costs
ANALYSE_COST = 25
SUMMARISE_COST = 10


async def check_idempotency(
    db: AsyncSession,
    idempotency_key: str | None,
    organisation_id: uuid.UUID,
    endpoint: str,
) -> dict | None:
    """
    Check if an idempotency key was already used.
    Returns the cached response if found, None otherwise.
    """
    if not idempotency_key:
        return None

    result = await db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.key == idempotency_key,
            IdempotencyRecord.organisation_id == organisation_id,
            IdempotencyRecord.endpoint == endpoint,
            IdempotencyRecord.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
        )
    )
    record = result.scalar_one_or_none()

    if record:
        logger.info(
            "idempotency_hit",
            key=idempotency_key,
            endpoint=endpoint,
            org_id=str(organisation_id),
        )
        return {"status_code": record.status_code, "body": record.response_body}

    return None


async def save_idempotency_record(
    db: AsyncSession,
    idempotency_key: str,
    organisation_id: uuid.UUID,
    endpoint: str,
    status_code: int,
    response_body: dict,
) -> None:
    """Save a response for an idempotency key."""
    record = IdempotencyRecord(
        key=idempotency_key,
        organisation_id=organisation_id,
        endpoint=endpoint,
        status_code=status_code,
        response_body=response_body,
    )
    db.add(record)
    await db.flush()


@router.post("/analyse")
async def analyse(
    request: Request,
    body: AnalyseRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """
    Synchronous product endpoint — costs 25 credits.

    Performs text analysis (word count, unique words).
    Credits are deducted atomically before processing.
    If processing fails after deduction, credits are refunded.
    """
    # Rate limiting
    rate_limiter: RateLimiter = request.app.state.rate_limiter
    await rate_limiter.check_rate_limit(str(current_user.organisation_id))

    # Check idempotency
    cached = await check_idempotency(
        db, idempotency_key, current_user.organisation_id, "/api/analyse"
    )
    if cached:
        return JSONResponse(
            status_code=cached["status_code"],
            content=cached["body"],
        )

    # Deduct credits atomically
    try:
        _, remaining = await credit_service.deduct_credits(
            db=db,
            organisation_id=current_user.organisation_id,
            user_id=current_user.id,
            amount=ANALYSE_COST,
            reason="API call: /api/analyse",
            idempotency_key=idempotency_key,
        )
    except InsufficientCreditsError as e:
        balance = await credit_service.get_balance(db, current_user.organisation_id)
        error_body = {
            "error": "insufficient_credits",
            "balance": balance,
            "required": ANALYSE_COST,
            "request_id": get_request_id(),
        }
        return JSONResponse(status_code=402, content=error_body)

    # Process the analysis — if this fails, refund credits
    try:
        result = analyse_text(body.text)
    except Exception as e:
        logger.error(
            "analyse_processing_failed",
            error=str(e),
            org_id=str(current_user.organisation_id),
        )
        # Refund credits since processing failed
        await credit_service.refund_credits(
            db=db,
            organisation_id=current_user.organisation_id,
            amount=ANALYSE_COST,
            reason="Refund: /api/analyse processing failed",
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "processing_error",
                "message": "Analysis failed. Credits have been refunded.",
                "request_id": get_request_id(),
            },
        )

    response_body = {
        "result": f"Analysis complete. Sentiment: {result['sentiment']}. Word count: {result['word_count']}. Unique words: {result['unique_word_count']}.",
        "credits_remaining": remaining,
    }

    # Save idempotency record if key was provided
    if idempotency_key:
        await save_idempotency_record(
            db, idempotency_key, current_user.organisation_id,
            "/api/analyse", 200, response_body,
        )

    return response_body


@router.post("/summarise")
async def summarise(
    request: Request,
    body: SummariseRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """
    Async product endpoint — costs 10 credits.

    Returns a job_id immediately. Processing happens in the background via ARQ.
    Credits are deducted before queuing. If the worker fails, credits are refunded.
    """
    # Rate limiting
    rate_limiter: RateLimiter = request.app.state.rate_limiter
    await rate_limiter.check_rate_limit(str(current_user.organisation_id))

    # Check idempotency
    cached = await check_idempotency(
        db, idempotency_key, current_user.organisation_id, "/api/summarise"
    )
    if cached:
        return JSONResponse(
            status_code=cached["status_code"],
            content=cached["body"],
        )

    # Deduct credits atomically
    try:
        _, remaining = await credit_service.deduct_credits(
            db=db,
            organisation_id=current_user.organisation_id,
            user_id=current_user.id,
            amount=SUMMARISE_COST,
            reason="API call: /api/summarise",
            idempotency_key=idempotency_key,
        )
    except InsufficientCreditsError as e:
        balance = await credit_service.get_balance(db, current_user.organisation_id)
        error_body = {
            "error": "insufficient_credits",
            "balance": balance,
            "required": SUMMARISE_COST,
            "request_id": get_request_id(),
        }
        return JSONResponse(status_code=402, content=error_body)

    # Create job record
    job = await job_service.create_job(
        db=db,
        organisation_id=current_user.organisation_id,
        user_id=current_user.id,
        job_type="summarise",
        input_data={"text": body.text},
        credits_deducted=SUMMARISE_COST,
        idempotency_key=idempotency_key,
    )

    # Enqueue background task via ARQ
    arq_pool = request.app.state.arq_pool
    if arq_pool:
        try:
            await arq_pool.enqueue_job(
                "process_summarise_job",
                str(job.id),
            )
        except Exception as e:
            logger.error(
                "arq_enqueue_failed",
                error=str(e),
                job_id=str(job.id),
            )
            # Job is still created with PENDING status — the stale job
            # detector will handle it if it never gets processed.

    response_body = {
        "job_id": str(job.id),
        "status": "pending",
        "credits_remaining": remaining,
    }

    # Save idempotency record
    if idempotency_key:
        await save_idempotency_record(
            db, idempotency_key, current_user.organisation_id,
            "/api/summarise", 200, response_body,
        )

    return response_body


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Poll job status. Only the organisation that created the job can access it.

    Returns:
        Job status, result (if completed), or error (if failed).
    """
    job = await job_service.get_job(
        db=db,
        job_id=job_id,
        organisation_id=current_user.organisation_id,
    )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status.value,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )
