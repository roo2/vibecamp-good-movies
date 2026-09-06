"""Taking a film out of the corpus, and every row that still names it.

A film gets removed when it should never have been here — Carlos (2010) carried
Marmaduke's IMDb id, so its dialogue, its verdicts and its position on every
axis described a different film. Deleting the `films` row alone would leave that
film's verdicts in the atlas, its similarity edges in other films' neighbour
lists, and a rating pointing at nothing.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from moral_atlas import db
from moral_atlas.config import settings


@pytest.fixture
def store(monkeypatch, tmp_path):
    test_settings = replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "atlas.sqlite",
    )
    monkeypatch.setattr(db, "settings", lambda: test_settings)
    db.init_db()


def _populate() -> None:
    for film_id, title in (("carlos-2010", "Carlos"), ("the-birds-1963", "The Birds")):
        db.upsert_film({"film_id": film_id, "title": title, "year": 2010})
    db.upsert_evidence("carlos-2010", "plot", "A dog in Kansas.")
    db.upsert_evidence("the-birds-1963", "plot", "Birds attack a coastal town.")
    with db.connect() as con:
        con.execute("INSERT INTO film_taste (film_id, dim_id, position) VALUES (?,?,?)",
                    ["carlos-2010", 1, 0.4])
        con.executemany(
            "INSERT INTO film_neighbours (film_id, neighbour_id, similarity) VALUES (?,?,?)",
            [("carlos-2010", "the-birds-1963", 0.7),
             ("the-birds-1963", "carlos-2010", 0.7)])
        con.execute("INSERT INTO users (user_id, name, created_at) VALUES (?,?,?)",
                    ["u1", "A rater", db.now()])
        con.executemany(
            "INSERT INTO movie_ratings (rating_id, user_id, film_id, reaction, submitted_at) "
            "VALUES (?,?,?,?,?)",
            [("r1", "u1", "carlos-2010", "liked", db.now()),
             ("r2", "u1", "the-birds-1963", "liked", db.now())])


def test_removal_reaches_the_edges_pointing_at_the_film_not_only_its_own_rows(store):
    _populate()

    removed = db.remove_films(["carlos-2010"])

    assert db.get_film("carlos-2010") is None
    assert db.get_film("the-birds-1963") is not None, "only the named film goes"
    with db.connect(read_only=True) as con:
        edges = con.execute("SELECT film_id, neighbour_id FROM film_neighbours").fetchall()
        ratings = con.execute("SELECT film_id FROM movie_ratings").fetchall()
    assert edges == [], (
        "the edge INTO the removed film is the one a hand-written delete forgets"
    )
    assert [r["film_id"] for r in ratings] == ["the-birds-1963"]
    assert removed["film_neighbours.neighbour_id"] == 1, (
        "the second reference is counted under its own name, so the cost is legible"
    )
    assert removed["movie_ratings"] == 1, "user rows are counted, never quietly dropped"


def test_a_session_that_ended_on_the_film_survives_it(store):
    _populate()
    with db.connect() as con:
        con.execute("INSERT INTO users (user_id, name, created_at) VALUES (?,?,?)",
                    ["host", "A host", db.now()])
        con.execute(
            "INSERT INTO group_sessions (session_id, share_token, host_user_id, status, "
            "created_at, selected_film_id) VALUES (?,?,?,?,?,?)",
            ["s1", "tok", "host", "done", db.now(), "carlos-2010"])

    db.remove_films(["carlos-2010"])

    with db.connect(read_only=True) as con:
        row = con.execute("SELECT session_id, selected_film_id FROM group_sessions").fetchone()
    assert row["session_id"] == "s1", "the evening happened; only its film stops being true"
    assert row["selected_film_id"] is None


def test_every_table_naming_a_film_is_found_from_the_schema(store):
    references = dict(db.film_references())
    for table in ("films", "evidence", "scores", "skeletons", "model_verdicts",
                  "film_taste", "film_neighbours", "movie_ratings",
                  "session_shortlist_films", "shortlist_reactions"):
        assert table in references, f"{table} names a film and must be swept"
    assert ("film_neighbours", "neighbour_id") in db.film_references()
    assert ("group_sessions", "selected_film_id") in db.film_references()
