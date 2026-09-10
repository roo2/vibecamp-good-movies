"""Tests for the data deploy: what crosses to the deployed store, and what must not.

The corpus is rebuilt on a laptop and sent to a server, so this path writes to
production by design. The properties worth pinning are all about restraint —
user rows are never touched, a film somebody rated is never deleted underneath
them, and a push that would break either of those does nothing at all.
"""
from __future__ import annotations

import uuid

import psycopg
import pytest

from moral_atlas import db, transfer

from conftest import TEST_URL


@pytest.fixture
def target(test_database):
    """A second schema, standing in for the deployed database.

    A schema rather than another database: `push_corpus` reaches the target
    through a URL, and a URL can carry a `search_path`, so the test gets a
    genuinely separate store for the price of a schema.
    """
    name = f"target_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(TEST_URL, autocommit=True) as con:
        con.execute(f'CREATE SCHEMA "{name}"')
    url = f"{TEST_URL}?options=-c%20search_path%3D{name}"
    try:
        yield url
    finally:
        with psycopg.connect(TEST_URL, autocommit=True) as con:
            con.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


def _connect(url):
    return psycopg.connect(url, row_factory=db._row_factory, autocommit=True)


@pytest.fixture
def source():
    """This machine's store, with a small corpus in it."""
    db.init_db()
    for index in range(3):
        db.upsert_film({"film_id": f"film-{index}", "title": f"Film {index}",
                        "year": 2000 + index})
    with db.connect() as con:
        con.execute("INSERT INTO taste_dimensions (dim_id, variance, replication, "
                    "evidence, status) VALUES (1, 0.2, 0.9, 0.5, 'unnamed')")
        con.execute("INSERT INTO film_taste (film_id, dim_id, position) "
                    "VALUES ('film-0', 1, 12.5)")
    return db


def _seed_user(url, film_id: str) -> None:
    """Somebody used the deployed site and rated a film."""
    with _connect(url) as con:
        con.execute("INSERT INTO users (user_id, name, created_at) "
                    "VALUES ('u1', 'A rater', %s)", [db.now()])
        con.execute("INSERT INTO movie_ratings (rating_id, user_id, film_id, "
                    "reaction, submitted_at) VALUES ('r1','u1',%s,'liked',%s)",
                    [film_id, db.now()])


def test_the_corpus_arrives(source, target):
    transfer.push_corpus(target, report=lambda _: None)
    with _connect(target) as con:
        assert con.execute("SELECT COUNT(*) AS n FROM films").fetchone()["n"] == 3
        assert con.execute("SELECT COUNT(*) AS n FROM film_taste").fetchone()["n"] == 1


def test_user_rows_are_left_alone(source, target):
    """The one property this whole path exists to keep."""
    transfer.push_corpus(target, report=lambda _: None)
    _seed_user(target, "film-1")

    transfer.push_corpus(target, report=lambda _: None)
    with _connect(target) as con:
        assert con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 1
        assert con.execute("SELECT COUNT(*) AS n FROM movie_ratings").fetchone()["n"] == 1


def test_a_film_someone_rated_is_kept_even_when_the_corpus_drops_it(source, target):
    """The rule the foreign keys now enforce, made deliberate.

    SQLite let a load delete a rated film and leave the rating pointing at
    nothing; the site then rendered a blank card. Postgres refuses, so the
    choice has to be made explicitly — the film stays, and the deploy says so.
    Removing it for real is `atlas remove-film`, which takes the rating too.
    """
    transfer.push_corpus(target, report=lambda _: None)
    _seed_user(target, "film-2")
    db.remove_films(["film-2"])           # gone from the corpus on this machine

    result = transfer.push_corpus(target, report=lambda _: None)
    assert result["held"] == ["film-2"]
    with _connect(target) as con:
        assert con.execute("SELECT COUNT(*) AS n FROM movie_ratings").fetchone()["n"] == 1
        titles = [r["film_id"] for r in con.execute("SELECT film_id FROM films")]
    assert "film-2" in titles


def test_a_film_nobody_touched_is_dropped_when_the_corpus_drops_it(source, target):
    """The other half: restraint about rated films is not a refusal to delete."""
    transfer.push_corpus(target, report=lambda _: None)
    db.remove_films(["film-2"])

    result = transfer.push_corpus(target, report=lambda _: None)
    assert result["held"] == []
    with _connect(target) as con:
        ids = {r["film_id"] for r in con.execute("SELECT film_id FROM films")}
    assert ids == {"film-0", "film-1"}


def test_a_push_that_fails_leaves_the_target_as_it_was(source, target, monkeypatch):
    """One transaction, so a half-swapped atlas is not a state the site can be in."""
    transfer.push_corpus(target, report=lambda _: None)
    db.upsert_film({"film_id": "film-9", "title": "Late Arrival", "year": 2024})

    real = transfer.copy_into

    def explode(con, table, columns, rows, types):
        if table == "film_taste":
            raise RuntimeError("network died mid-deploy")
        return real(con, table, columns, rows, types)

    monkeypatch.setattr(transfer, "copy_into", explode)
    with pytest.raises(RuntimeError):
        transfer.push_corpus(target, report=lambda _: None)

    with _connect(target) as con:
        ids = {r["film_id"] for r in con.execute("SELECT film_id FROM films")}
        taste = con.execute("SELECT COUNT(*) AS n FROM film_taste").fetchone()["n"]
    assert "film-9" not in ids, "the failed push must not have half-landed"
    assert taste == 1, "and must not have emptied what it could not refill"


def test_parents_are_ordered_before_the_tables_that_reference_them(source):
    """Insert order is load-bearing now — `films` before anything naming a film."""
    with db.connect() as con:
        order = transfer.dependency_order(con, ["film_taste", "films", "taste_dimensions"])
    assert order.index("films") < order.index("film_taste")
    assert order.index("taste_dimensions") < order.index("film_taste")


def test_every_user_table_named_still_exists(source):
    """A renamed user table would silently become corpus, and be replaced."""
    with db.connect() as con:
        present = db.table_names(con)
    assert transfer.USER_TABLES <= present


def test_a_push_leaves_the_derived_documents_built(source, target):
    """Otherwise the first visitor after a data deploy pays for them.

    The push moves the counts, which is what every stored document is keyed on,
    so they all become unreadable at the moment the corpus lands. Rebuilding
    them takes about a minute on the machine that serves them and the router in
    front of it gives up at thirty seconds — so they are built from the machine
    doing the pushing, which is both faster and not answering anyone.
    """
    import psycopg

    from moral_atlas.web import documents

    transfer.push_corpus(target, report=lambda _: None)
    with db.using(target):
        documents.forget("thing")
        documents.get("thing", "k1", lambda: {"built": "there"})

    with _connect(target) as con:
        rows = con.execute("SELECT name, payload FROM documents").fetchall()
    assert [r["name"] for r in rows] == ["thing"], "written to the target, not to here"

    # And nothing leaked into the store this process was pointed at before.
    with db.connect(read_only=True) as con:
        here = con.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
    assert here == 0, "db.using must not have written the local store"
