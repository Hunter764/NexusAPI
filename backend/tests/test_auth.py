"""
Tests for JWT authentication and authorization.
"""

import uuid
import pytest

from tests.conftest import create_test_jwt, seed_test_org_and_user


@pytest.mark.asyncio
async def test_missing_token_returns_401(client):
    """Requests without Authorization header should return 401."""
    response = await client.get("/me")
    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "authentication_error"
    assert "request_id" in data


@pytest.mark.asyncio
async def test_expired_token_returns_401(client, test_db):
    """Expired JWT tokens should return 401."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(
        user_id=str(user.id),
        organisation_id=str(org.id),
        expired=True,
    )
    response = await client.get(
        "/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tampered_token_returns_401(client, test_db):
    """JWT signed with wrong secret should return 401."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(
        user_id=str(user.id),
        organisation_id=str(org.id),
        tampered_key="wrong-secret-key",
    )
    response = await client.get(
        "/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_deleted_user_returns_401(client, test_db):
    """Valid JWT but user no longer in database should return 401."""
    # Create a token for a user that doesn't exist in DB
    fake_user_id = str(uuid.uuid4())
    fake_org_id = str(uuid.uuid4())
    token = create_test_jwt(user_id=fake_user_id, organisation_id=fake_org_id)
    response = await client.get(
        "/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_returns_user_profile(client, test_db):
    """Valid JWT with existing user should return user profile."""
    org, user = await seed_test_org_and_user(test_db)
    token = create_test_jwt(
        user_id=str(user.id),
        organisation_id=str(org.id),
        role="admin",
    )
    response = await client.get(
        "/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "admin@test.com"
    assert data["organisation_slug"] == "test-org"


@pytest.mark.asyncio
async def test_non_admin_cannot_grant_credits(client, test_db):
    """Members (non-admin) should get 403 when trying to grant credits."""
    from app.models.organisation import Organisation
    from app.models.user import User, UserRole

    org = Organisation(name="Member Org", slug="member-org")
    test_db.add(org)
    await test_db.flush()

    member = User(
        email="member@member-org.com",
        name="Member",
        google_id="google_member_001",
        organisation_id=org.id,
        role=UserRole.MEMBER,
    )
    test_db.add(member)
    await test_db.flush()
    await test_db.commit()

    token = create_test_jwt(
        user_id=str(member.id),
        organisation_id=str(org.id),
        role="member",
    )
    response = await client.post(
        "/credits/grant",
        json={"amount": 100, "reason": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
