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


@pytest.fixture(autouse=True)
def fresh_schema(test_database: str, request) -> str:
    """A scratch schema for every test, whether it asks for one or not.

    Autouse on purpose. A test that forgets to isolate itself is the kind of
    test that passes alone and fails in a suite, and under SQLite the isolation
    was a path each test had to remember to set. Here it is the default: the
    schema exists before the test body runs, `settings()` already points at it,
    and any `replace(settings(), ...)` a test does inherits it without knowing
    this fixture exists.

    Named after the test so a schema left behind by a crash says which one.
    """
    from moral_atlas.config import settings

    hint = re.sub(r"[^a-z0-9_]", "_", request.node.name.lower())[:24].strip("_")
    name = f"{hint or 'test'}_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(TEST_URL, autocommit=True) as con:
        con.execute(f'CREATE SCHEMA "{name}"')

    previous = os.environ.get("ATLAS_DB_SCHEMA")
    os.environ["ATLAS_DB_SCHEMA"] = name
    settings.cache_clear()
    try:
        yield name
    finally:
        if previous is None:
            os.environ.pop("ATLAS_DB_SCHEMA", None)
        else:
            os.environ["ATLAS_DB_SCHEMA"] = previous
        settings.cache_clear()
        with psycopg.connect(TEST_URL, autocommit=True) as con:
            con.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


@pytest.fixture
def empty_schema(test_database: str) -> str:
    """A schema with nothing in it — what a deployment looks like before init.

    `fresh_schema` gives every test a schema, but tests that check the
    empty-database path need one they can be sure stays empty even after the
    code under test has run `init_db` against the other one.
    """
    name = f"empty_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(TEST_URL, autocommit=True) as con:
        con.execute(f'CREATE SCHEMA "{name}"')
    try:
        yield name
    finally:
        with psycopg.connect(TEST_URL, autocommit=True) as con:
            con.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
