"""One test database, a schema per test.

Every test used to get its own SQLite file, which is the cheapest isolation
there is: a path in a tmp directory and nothing to clean up. Postgres has no
files, so the equivalent is a schema — created before the test, dropped after,
and pointed at through `settings().db_schema`, which `db.connect` turns into a
`search_path`. A schema costs about a millisecond, where a database costs
hundreds, and 303 of them would have shown.

The database itself is created once if it is not already there. Nothing here
touches the development database: the name is deliberately distinct, and a run
that somehow pointed at the real one would still only build and drop schemas
beside `public` rather than in it.
"""
from __future__ import annotations

import os
import re
import uuid

import psycopg
import pytest

TEST_DATABASE = os.environ.get("ATLAS_TEST_DATABASE", "moral_atlas_test")
ADMIN_URL = os.environ.get("ATLAS_TEST_ADMIN_URL", "postgresql:///postgres")
TEST_URL = os.environ.get("ATLAS_TEST_URL", f"postgresql:///{TEST_DATABASE}")


def _ensure_database() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as con:
        exists = con.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", [TEST_DATABASE]).fetchone()
        if not exists:
            con.execute(f'CREATE DATABASE "{TEST_DATABASE}"')


@pytest.fixture(scope="session", autouse=True)
def test_database() -> str:
    """Point the whole session at the test database before anything reads it.

    `settings()` is cached, so the cache is cleared after the environment is
    set — otherwise the first import wins and every test runs against whatever
    database the developer happens to have configured, which is the one failure
    mode a test suite must not have.
    """
    from moral_atlas.config import settings

    _ensure_database()
    os.environ["DATABASE_URL"] = TEST_URL
    settings.cache_clear()
    yield TEST_URL
    settings.cache_clear()


@pytest.fixture
def fresh_schema(test_database: str):
    """A scratch schema, and the settings changes that point the app at it."""
    made: list[str] = []

    def make(hint: str = "t") -> str:
        name = f"{re.sub(r'[^a-z0-9_]', '_', hint.lower())[:20]}_{uuid.uuid4().hex[:8]}"
        with psycopg.connect(TEST_URL, autocommit=True) as con:
            con.execute(f'CREATE SCHEMA "{name}"')
        made.append(name)
        return name

    yield make

    with psycopg.connect(TEST_URL, autocommit=True) as con:
        for name in made:
            con.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
