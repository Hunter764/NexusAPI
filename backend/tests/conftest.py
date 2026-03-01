"""
Pytest configuration and shared fixtures.
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from jose import jwt


# Use an in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a test database engine with all tables."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    from app.database import Base
    # Import all models to ensure they are registered
    from app.models.organisation import Organisation  # noqa: F401
    from app.models.user import User  # noqa: F401
    from app.models.credit_transaction import CreditTransaction  # noqa: F401
    from app.models.job import Job  # noqa: F401
    from app.models.idempotency_record import IdempotencyRecord  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db(test_engine):
    """Create a test database session."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(test_engine):
    """Create an async test client with overridden DB dependency."""
    from app.main import app
    from app.database import get_db
    from app.middleware.rate_limiter import RateLimiter

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    # Use a no-op rate limiter for tests (no Redis)
    app.state.rate_limiter = RateLimiter(None)
    app.state.arq_pool = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


def create_test_jwt(
    user_id: str | None = None,
    organisation_id: str | None = None,
    role: str = "admin",
    expired: bool = False,
    tampered_key: str | None = None,
) -> str:
    """Create a JWT for testing purposes."""
    from app.config import settings

    if user_id is None:
        user_id = str(uuid.uuid4())
    if organisation_id is None:
        organisation_id = str(uuid.uuid4())

    exp = datetime.now(timezone.utc) + (
        timedelta(hours=-1) if expired else timedelta(hours=24)
    )

    payload = {
        "user_id": user_id,
        "organisation_id": organisation_id,
        "role": role,
        "exp": exp,
        "iat": datetime.now(timezone.utc),
    }

    secret = tampered_key or settings.JWT_SECRET_KEY
    return jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)


async def seed_test_org_and_user(db: AsyncSession):
    """Create a test organisation and admin user, commit, and return them."""
    from app.models.organisation import Organisation
    from app.models.user import User, UserRole

    org = Organisation(
        id=uuid.uuid4(),
        name="Test Org",
        slug="test-org",
    )
    db.add(org)
    await db.flush()

    user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        name="Test Admin",
        google_id="google_test_123",
        organisation_id=org.id,
        role=UserRole.ADMIN,
    )
    db.add(user)
    await db.flush()
    await db.commit()

    return org, user
