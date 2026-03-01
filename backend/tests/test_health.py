"""
Tests for the /health endpoint.
"""

import pytest


@pytest.mark.asyncio
async def test_health_returns_200_when_db_connected(client):
    """Health check should return 200 when the database is reachable."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
