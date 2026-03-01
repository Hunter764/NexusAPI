"""
Tests for product endpoints — /api/analyse and /api/summarise.
"""

import uuid
import pytest

from tests.conftest import create_test_jwt, seed_test_org_and_user


# --- Input Validation Tests ---

@pytest.mark.asyncio
async def test_analyse_text_too_short(client, test_db):
    """Text shorter than 10 characters should fail validation."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    response = await client.post(
        "/api/analyse",
        json={"text": "short"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "validation_error"


@pytest.mark.asyncio
async def test_analyse_text_too_long(client, test_db):
    """Text longer than 2000 characters should fail validation."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    response = await client.post(
        "/api/analyse",
        json={"text": "x" * 2001},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analyse_missing_text_field(client, test_db):
    """Missing 'text' field should fail validation."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    response = await client.post(
        "/api/analyse",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


# --- Summarise Endpoint Tests ---

@pytest.mark.asyncio
async def test_summarise_returns_job_id(client, test_db):
    """Summarise should return a job_id immediately."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    # Grant credits
    await client.post(
        "/credits/grant",
        json={"amount": 50, "reason": "Test"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.post(
        "/api/summarise",
        json={"text": "This is a test text for summarisation with enough words."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    assert data["credits_remaining"] == 40


# --- Job Polling Tests ---

@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(client, test_db):
    """Polling a job that doesn't exist should return 404."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    fake_job_id = str(uuid.uuid4())
    response = await client.get(
        f"/api/jobs/{fake_job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cross_org_job_access_denied(client, test_db):
    """Jobs from one org should not be accessible by another org."""
    from app.models.organisation import Organisation
    from app.models.user import User, UserRole

    # Create org A and user
    org_a, user_a = await seed_test_org_and_user(test_db)

    # Create org B and user
    org_b = Organisation(name="Org B", slug="org-b")
    test_db.add(org_b)
    await test_db.flush()

    user_b = User(
        email="user@org-b.com",
        name="User B",
        google_id="google_b_123",
        organisation_id=org_b.id,
        role=UserRole.ADMIN,
    )
    test_db.add(user_b)
    await test_db.flush()
    await test_db.commit()

    # Create a job as org A
    token_a = create_test_jwt(
        user_id=str(user_a.id), organisation_id=str(org_a.id)
    )
    await client.post(
        "/credits/grant",
        json={"amount": 50, "reason": "Test"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    response = await client.post(
        "/api/summarise",
        json={"text": "This is org A's text for summarisation."},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    job_id = response.json()["job_id"]

    # Try to access the job as org B — should get 404 (not 403, to not leak info)
    token_b = create_test_jwt(
        user_id=str(user_b.id), organisation_id=str(org_b.id)
    )
    response = await client.get(
        f"/api/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404


# --- Error Response Shape Tests ---

@pytest.mark.asyncio
async def test_error_response_has_consistent_shape(client, test_db):
    """All errors should include error, message, and request_id."""
    response = await client.get("/me")
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert "message" in data
    assert "request_id" in data
