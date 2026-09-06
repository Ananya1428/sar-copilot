"""Integration tests run against the live Postgres from docker-compose
(`docker compose exec api pytest`) — Alembic has already migrated it via
the api service's startup command. Each test runs inside a SAVEPOINT that
is rolled back afterward, so tests never pollute the seeded dataset and
never need their own schema setup."""

from contextlib import contextmanager

import pytest
from sqlalchemy.orm import sessionmaker

from app.database import engine


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
