"""
Health check endpoint.
Returns 200 if healthy, 503 if the database is unreachable.
"""

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

logger = structlog.get_logger("nexusapi.health")
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint. Verifies database connectivity.

    Returns:
        200: Application is healthy and database is reachable.
        503: Database is unreachable.
    """
    try:
        await db.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "database": "connected",
            },
        )
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "unreachable",
                "detail": "Database connection failed",
            },
        )
