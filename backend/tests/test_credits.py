"""
Tests for the credit system — granting, balance, deduction, and edge cases.
"""

import pytest

from tests.conftest import create_test_jwt, seed_test_org_and_user


@pytest.mark.asyncio
async def test_grant_credits_success(client, test_db):
    """Admin should be able to grant credits."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    response = await client.post(
        "/credits/grant",
        json={"amount": 100, "reason": "Initial test grant"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["new_balance"] == 100


@pytest.mark.asyncio
async def test_get_balance(client, test_db):
    """Balance should reflect granted credits."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    # Grant credits first
    await client.post(
        "/credits/grant",
        json={"amount": 200, "reason": "Setup"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(
        "/credits/balance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["balance"] == 200
    assert len(data["recent_transactions"]) == 1
    assert data["recent_transactions"][0]["amount"] == 200


@pytest.mark.asyncio
async def test_grant_invalid_amount_returns_422(client, test_db):
    """Granting zero or negative credits should fail validation."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    response = await client.post(
        "/credits/grant",
        json={"amount": -10, "reason": "bad grant"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analyse_insufficient_credits_returns_402(client, test_db):
    """Calling /api/analyse with 0 credits should return 402."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    response = await client.post(
        "/api/analyse",
        json={"text": "This is a test text with enough characters to pass validation."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 402
    data = response.json()
    assert data["error"] == "insufficient_credits"
    assert data["balance"] == 0
    assert data["required"] == 25


@pytest.mark.asyncio
async def test_analyse_with_24_credits_returns_402(client, test_db):
    """Calling /api/analyse with 24 credits (one less than needed) should return 402."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    # Grant 24 credits
    await client.post(
        "/credits/grant",
        json={"amount": 24, "reason": "Almost enough"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.post(
        "/api/analyse",
        json={"text": "This is a test text with enough characters to pass validation."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 402
    data = response.json()
    assert data["balance"] == 24
    assert data["required"] == 25


@pytest.mark.asyncio
async def test_analyse_success_deducts_credits(client, test_db):
    """Successful /api/analyse should deduct 25 credits and return result."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(user_id=str(user.id), organisation_id=str(org.id))

    # Grant enough credits
    await client.post(
        "/credits/grant",
        json={"amount": 100, "reason": "Test grant"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.post(
        "/api/analyse",
        json={"text": "This is a test text with enough characters to pass validation."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "Word count:" in data["result"]
    assert "Unique words:" in data["result"]
    assert data["credits_remaining"] == 75
