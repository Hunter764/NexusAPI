"""
API endpoint schemas for product endpoints and jobs.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AnalyseRequest(BaseModel):
    """Request body for POST /api/analyse."""
    text: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Text to analyse (10–2000 characters)",
    )


class AnalyseResponse(BaseModel):
    """Response for POST /api/analyse."""
    result: str
    credits_remaining: int


class SummariseRequest(BaseModel):
    """Request body for POST /api/summarise."""
    text: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Text to summarise (10–2000 characters)",
    )


class SummariseResponse(BaseModel):
    """Response for POST /api/summarise."""
    job_id: uuid.UUID
    status: str
    credits_remaining: int


class JobStatusResponse(BaseModel):
    """Response for GET /api/jobs/{job_id}."""
    job_id: uuid.UUID
    status: str
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
