"""SQLite store.

Design rule: nothing derived is ever overwritten in place without a version
stamp. Every skeleton, proposition and score carries the run_id, model and
prompt_version that produced it, so re-cutting the item bank or swapping models
produces a new layer you can diff rather than a silent mutation of the old one.

Two consequences of SQLite worth knowing:

* **No array type.** The list-valued film columns — genres, keywords, directors,
  writers, cast, origin_country — are stored as JSON text and decoded on read.
  `LIST_COLUMNS` is the single place that mapping lives, so a column added to
  the schema must be added there too or it comes back as a raw string.

* **One writer at a time.** WAL mode plus a busy timeout keeps concurrent
  readers working and makes a brief write collision wait rather than raise.
  Writes are already serialised — the LLM stages fan out over threads but
  persist from the collecting thread — so this is belt and braces.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import settings

# Columns held as JSON text because SQLite has no array type.
LIST_COLUMNS = {
    "origin_country", "genres", "keywords", "directors", "writers", "billed_cast",
}

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS films (
    film_id           TEXT PRIMARY KEY,
    tmdb_id           INTEGER,
    imdb_id           TEXT,
    title             TEXT NOT NULL,
    year              INTEGER,
    runtime           INTEGER,
    origin_country    TEXT,   -- JSON array
    original_language TEXT,
    genres            TEXT,   -- JSON array
    keywords          TEXT,   -- JSON array
    directors         TEXT,   -- JSON array
    writers           TEXT,   -- JSON array
    billed_cast       TEXT,   -- JSON array
    collection        TEXT,
    based_on          TEXT,
    budget            INTEGER,
    revenue           INTEGER,
    wikipedia_title   TEXT,
    seed_note         TEXT,
    description       TEXT,
    fetched_at        TEXT
);

-- One row per (film, evidence layer). Layers: plot, themes, reception,
-- subtitles, script.
CREATE TABLE IF NOT EXISTS evidence (
    film_id     TEXT,
    layer       TEXT,
    content     TEXT,
    source_url  TEXT,
    word_count  INTEGER,
    meta        TEXT,   -- JSON
    fetched_at  TEXT,
    PRIMARY KEY (film_id, layer)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    stage             TEXT,
    model             TEXT,
    prompt_version    TEXT,
    params            TEXT,   -- JSON
    started_at        TEXT,
    finished_at       TEXT,
    n_calls           INTEGER,
    input_tokens      INTEGER,
    output_tokens     INTEGER,
    cache_read_tokens INTEGER,
    cost_usd          REAL
);

CREATE TABLE IF NOT EXISTS skeletons (
    film_id        TEXT,
    variant        TEXT,
    run_id         TEXT,
    data           TEXT,   -- JSON
    model          TEXT,
    prompt_version TEXT,
    created_at     TEXT,
    PRIMARY KEY (film_id, variant, run_id)
);

CREATE TABLE IF NOT EXISTS propositions_raw (
    prop_id    TEXT PRIMARY KEY,
    film_id    TEXT,
    variant    TEXT,
    run_id     TEXT,
    text       TEXT,
    stance     TEXT,
    evidence   TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS item_bank (
    item_id      TEXT,
    bank_version TEXT,
    text         TEXT,
    cluster_id   INTEGER,
    support      INTEGER,
    reversed_of  TEXT,
    active       INTEGER,
    note         TEXT,
    PRIMARY KEY (item_id, bank_version)
);

-- value: +1 affirms, -1 denies, 0 does not address.
CREATE TABLE IF NOT EXISTS scores (
    film_id      TEXT,
    item_id      TEXT,
    bank_version TEXT,
    variant      TEXT,
    run_id       TEXT,
    value        INTEGER,
    confidence   REAL,
    evidence     TEXT,
    PRIMARY KEY (film_id, item_id, bank_version, variant, run_id)
);

CREATE INDEX IF NOT EXISTS idx_scores_lookup
    ON scores (bank_version, variant, film_id);
CREATE INDEX IF NOT EXISTS idx_skeletons_film ON skeletons (film_id, variant);
CREATE INDEX IF NOT EXISTS idx_props_film ON propositions_raw (film_id);

-- Product-facing data is deliberately separate from the atlas research tables.
-- User identity is intentionally minimal until an SSO provider replaces it.
CREATE TABLE IF NOT EXISTS users (
    user_id    TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    token      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(user_id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS movie_ratings (
    rating_id    TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(user_id),
    film_id      TEXT NOT NULL REFERENCES films(film_id),
    reaction     TEXT NOT NULL,
    submitted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_results (
    result_id      TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    answers        TEXT NOT NULL, -- JSON object
    answered_count INTEGER NOT NULL,
    submitted_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_movie_ratings_user ON movie_ratings (user_id, submitted_at);
CREATE INDEX IF NOT EXISTS idx_test_results_user ON test_results (user_id, submitted_at);

-- The item bank measures; these name what it is measuring. A dimension set is
-- versioned exactly like a bank, because deriving one is an LLM judgement and a
-- later derivation must be diffable against the earlier one rather than silently
-- replacing it.
CREATE TABLE IF NOT EXISTS dimensions (
    dim_version    TEXT,
    dim_id         INTEGER,
    name           TEXT,
    question       TEXT,
    pole_high      TEXT,
    pole_low       TEXT,
    n_dims         INTEGER,
    source         TEXT,   -- what the axes were derived FROM
    run_id         TEXT,
    model          TEXT,
    prompt_version TEXT,
    created_at     TEXT,
    PRIMARY KEY (dim_version, dim_id)
);

-- One row per (item, pass). `pass_name` is what makes the audit repeatable:
-- 'main' is the assignment in use, and the replicate / cross-model passes sit
-- beside it under their own names instead of overwriting it, so agreement
-- between passes is a query rather than a memory of a run someone once did.
CREATE TABLE IF NOT EXISTS item_dimensions (
    dim_version  TEXT,
    bank_version TEXT,
    item_id      TEXT,
    dim_id       INTEGER,
    polarity     INTEGER,  -- +1 affirming points to pole_high, -1 to pole_low
    fit          REAL,
    pass_name    TEXT,
    run_id       TEXT,
    model        TEXT,
    created_at   TEXT,
    PRIMARY KEY (dim_version, bank_version, item_id, pass_name)
);

CREATE INDEX IF NOT EXISTS idx_item_dimensions_lookup
    ON item_dimensions (dim_version, bank_version, pass_name);

CREATE TABLE IF NOT EXISTS group_sessions (
    session_id         TEXT PRIMARY KEY,
    share_token        TEXT NOT NULL UNIQUE,
    host_user_id       TEXT NOT NULL REFERENCES users(user_id),
    status             TEXT NOT NULL DEFAULT 'lobby',
    created_at         TEXT NOT NULL,
    started_at         TEXT,
    waiting_started_at TEXT,
    continued_at       TEXT
    deck_json          TEXT
);

CREATE TABLE IF NOT EXISTS session_members (
    session_id   TEXT NOT NULL REFERENCES group_sessions(session_id),
    user_id      TEXT NOT NULL REFERENCES users(user_id),
    joined_at    TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (session_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_session_members_user ON session_members (user_id);
"""


def now() -> str:
    """ISO-8601 UTC. Stored as text: Python 3.12 deprecated the implicit
    datetime adapters, and an explicit string is unambiguous in every client."""
    return datetime.now(timezone.utc).isoformat()


def new_run_id(stage: str) -> str:
    return f"{stage}-{uuid.uuid4().hex[:10]}"


@contextmanager
def connect(read_only: bool = False) -> Iterator[sqlite3.Connection]:
    s = settings()
    s.ensure_dirs()
    if read_only and s.db_path.exists():
        con = sqlite3.connect(f"file:{s.db_path}?mode=ro", uri=True, timeout=30)
    else:
        con = sqlite3.connect(s.db_path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    if not read_only:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
    try:
        yield con
        if not read_only:
            con.commit()
    finally:
        con.close()


def init_db() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
        _add_column_if_missing(con, "films", "description", "TEXT")
        _add_column_if_missing(con, "group_sessions", "deck_json", "TEXT")


def _add_column_if_missing(con: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _encode(column: str, value: Any) -> Any:
    if column in LIST_COLUMNS:
        return json.dumps(list(value)) if value is not None else None
    return value


def _decode_film(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    for column in LIST_COLUMNS:
        raw = out.get(column)
        if isinstance(raw, str):
            try:
                out[column] = json.loads(raw)
            except json.JSONDecodeError:
                out[column] = [raw]
        elif raw is None:
            out[column] = []
    return out


def start_run(stage: str, model: str, prompt_version: str, params: dict[str, Any]) -> str:
    run_id = new_run_id(stage)
    with connect() as con:
        con.execute(
            "INSERT INTO runs (run_id, stage, model, prompt_version, params, started_at, "
            "n_calls, input_tokens, output_tokens, cache_read_tokens, cost_usd) "
            "VALUES (?,?,?,?,?,?,0,0,0,0,0.0)",
            [run_id, stage, model, prompt_version, json.dumps(params), now()],
        )
    return run_id


def finish_run(run_id: str, usage: dict[str, Any]) -> None:
    with connect() as con:
        con.execute(
            "UPDATE runs SET finished_at=?, n_calls=?, input_tokens=?, output_tokens=?, "
            "cache_read_tokens=?, cost_usd=? WHERE run_id=?",
            [
                now(),
                usage.get("n_calls", 0),
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                usage.get("cache_read_tokens", 0),
                usage.get("cost_usd", 0.0),
                run_id,
            ],
        )


FILM_COLUMNS = [
    "film_id", "tmdb_id", "imdb_id", "title", "year", "runtime",
    "origin_country", "original_language", "genres", "keywords",
    "directors", "writers", "billed_cast", "collection", "based_on",
    "budget", "revenue", "wikipedia_title", "seed_note", "description", "fetched_at",
]


def upsert_film(row: dict[str, Any]) -> None:
    # Metadata refreshes should not erase the curated blind-story description.
    if row.get("description") is None:
        existing = get_film(row["film_id"])
        if existing and existing.get("description"):
            row = {**row, "description": existing["description"]}
    values = [_encode(c, row.get(c)) for c in FILM_COLUMNS]
    with connect() as con:
        con.execute(
            f"INSERT OR REPLACE INTO films ({','.join(FILM_COLUMNS)}) "
            f"VALUES ({','.join('?' * len(FILM_COLUMNS))})",
            values,
        )


def set_film_description(film_id: str, description: str) -> None:
    with connect() as con:
        con.execute("UPDATE films SET description=? WHERE film_id=?", [description, film_id])


def upsert_evidence(
    film_id: str, layer: str, content: str, source_url: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO evidence "
            "(film_id, layer, content, source_url, word_count, meta, fetched_at) "
            "VALUES (?,?,?,?,?,?,?)",
            [film_id, layer, content, source_url, len(content.split()),
             json.dumps(meta or {}), now()],
        )


def get_evidence(film_id: str) -> dict[str, str]:
    with connect(read_only=True) as con:
        rows = con.execute(
            "SELECT layer, content FROM evidence WHERE film_id=?", [film_id]
        ).fetchall()
    return {r["layer"]: r["content"] for r in rows}


def get_film(film_id: str) -> dict[str, Any] | None:
    with connect(read_only=True) as con:
        row = con.execute("SELECT * FROM films WHERE film_id=?", [film_id]).fetchone()
    return _decode_film(row) if row is not None else None


def list_films() -> list[dict[str, Any]]:
    with connect(read_only=True) as con:
        rows = con.execute("SELECT * FROM films ORDER BY year, title").fetchall()
    return [_decode_film(r) for r in rows]
