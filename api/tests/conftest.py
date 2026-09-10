"""Integration tests run against the live Postgres from docker-compose
(`docker compose exec api pytest`) — Alembic has already migrated it via
the api service's startup command. Each test runs inside a SAVEPOINT that
is rolled back afterward, so tests never pollute the seeded dataset and
never need their own schema setup."""

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy.orm import sessionmaker

from app.database import engine
from app.domain.auth.security import create_access_token, hash_password
from app.models.user import User


@contextmanager
def isolated_session():
    connection = engine.connect()
    trans = connection.begin()
    TestingSession = sessionmaker(bind=connection, future=True)
    session = TestingSession()
    session.begin_nested()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture()
def db_session():
    with isolated_session() as session:
        yield session


@pytest.fixture()
def session_factory():
    """The `isolated_session` context manager itself, for tests that need
    more than one independent session (own connection/transaction) within
    a single test.

    IMPORTANT: if the two sessions might write colliding unique keys (e.g.
    a determinism check that deliberately reproduces the same refs twice),
    use them SEQUENTIALLY — `with session_factory() as s: ...` fully exited
    before opening the next one. Two such sessions held open concurrently
    will deadlock: Postgres blocks the second INSERT of an uncommitted
    duplicate key until the first transaction resolves, but that first
    transaction only rolls back at fixture teardown, after the test
    function — which is itself stuck waiting on the second session — would
    have returned. (This is exactly how test_generator_is_deterministic
    used to hang.)
    """
    return isolated_session


@pytest.fixture()
def make_user(db_session):
    """Creates and flushes a real User row — password 'test-password-123' —
    so API tests exercise real bcrypt hashing and real JWTs (Part 8a),
    never a get_current_user bypass."""

    def _make(role: str = "analyst", email: str | None = None, is_active: bool = True) -> User:
        user = User(
            email=email or f"{role}-{uuid.uuid4().hex[:8]}@test.local",
            hashed_password=hash_password("test-password-123"),
            full_name=f"Test {role.title()}",
            role=role,
            is_active=is_active,
        )
        db_session.add(user)
        db_session.flush()
        return user

    return _make


@pytest.fixture()
def make_auth_headers(make_user):
    """Real `Authorization: Bearer <jwt>` headers backed by a real user and
    a real access token — the fixture every API test should use instead of
    relying on any kind of auth bypass."""

    def _make(role: str = "analyst", user: User | None = None) -> dict[str, str]:
        u = user or make_user(role=role)
        token = create_access_token(str(u.id), u.role)
        return {"Authorization": f"Bearer {token}"}

    return _make
