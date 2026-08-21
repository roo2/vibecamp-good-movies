"""DuckDB store.

Design rule: nothing derived is ever overwritten in place without a version
stamp. Every skeleton, proposition and score carries the run_id, model and
prompt_version that produced it, so re-cutting the item bank or swapping models
produces a new layer you can diff rather than a silent mutation of the old one.
"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import duckdb

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS films (
    film_id           VARCHAR PRIMARY KEY,
    tmdb_id           INTEGER,
    imdb_id           VARCHAR,
    title             VARCHAR NOT NULL,
    year              INTEGER,
    runtime           INTEGER,
    origin_country    VARCHAR[],
    original_language VARCHAR,
    genres            VARCHAR[],
    keywords          VARCHAR[],
    directors         VARCHAR[],
    writers           VARCHAR[],
    billed_cast       VARCHAR[],
    collection        VARCHAR,
    based_on          VARCHAR,
    budget            BIGINT,
    revenue           BIGINT,
    wikipedia_title   VARCHAR,
    seed_note         VARCHAR,
    fetched_at        TIMESTAMP
);

-- One row per (film, evidence layer). Layers: plot, themes, reception,
-- subtitles, subtitles_open, subtitles_close, script.
CREATE TABLE IF NOT EXISTS evidence (
    film_id     VARCHAR,
    layer       VARCHAR,
    content     TEXT,
    source_url  VARCHAR,
    word_count  INTEGER,
    meta        JSON,
    fetched_at  TIMESTAMP,
    PRIMARY KEY (film_id, layer)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id            VARCHAR PRIMARY KEY,
    stage             VARCHAR,
    model             VARCHAR,
    prompt_version    VARCHAR,
    params            JSON,
    started_at        TIMESTAMP,
    finished_at       TIMESTAMP,
    n_calls           INTEGER,
    input_tokens      BIGINT,
    output_tokens     BIGINT,
    cache_read_tokens BIGINT,
    cost_usd          DOUBLE
);

CREATE TABLE IF NOT EXISTS skeletons (
    film_id        VARCHAR,
    variant        VARCHAR,
    run_id         VARCHAR,
    data           JSON,
    model          VARCHAR,
    prompt_version VARCHAR,
    created_at     TIMESTAMP,
    PRIMARY KEY (film_id, variant, run_id)
);

CREATE TABLE IF NOT EXISTS propositions_raw (
    prop_id    VARCHAR PRIMARY KEY,
    film_id    VARCHAR,
    variant    VARCHAR,
    run_id     VARCHAR,
    text       TEXT,
    stance     VARCHAR,
    evidence   TEXT,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS item_bank (
    item_id      VARCHAR,
    bank_version VARCHAR,
    text         TEXT,
    cluster_id   INTEGER,
    support      INTEGER,
    reversed_of  VARCHAR,
    active       BOOLEAN,
    note         VARCHAR,
    PRIMARY KEY (item_id, bank_version)
);

-- value: +1 affirms, -1 denies, 0 does not address.
CREATE TABLE IF NOT EXISTS scores (
    film_id      VARCHAR,
    item_id      VARCHAR,
    bank_version VARCHAR,
    variant      VARCHAR,
    run_id       VARCHAR,
    value        TINYINT,
    confidence   DOUBLE,
    evidence     TEXT,
    PRIMARY KEY (film_id, item_id, bank_version, variant, run_id)
);
"""


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_run_id(stage: str) -> str:
    return f"{stage}-{uuid.uuid4().hex[:10]}"


@contextmanager
def connect(read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    s = settings()
    s.ensure_dirs()
    con = duckdb.connect(str(s.db_path), read_only=read_only)
    try:
        yield con
    finally:
        con.close()


def init_db() -> None:
    with connect() as con:
        con.execute(SCHEMA)


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


def upsert_film(row: dict[str, Any]) -> None:
    cols = [
        "film_id", "tmdb_id", "imdb_id", "title", "year", "runtime",
        "origin_country", "original_language", "genres", "keywords",
        "directors", "writers", "billed_cast", "collection", "based_on",
        "budget", "revenue", "wikipedia_title", "seed_note", "fetched_at",
    ]
    values = [row.get(c) for c in cols]
    with connect() as con:
        con.execute(
            f"INSERT OR REPLACE INTO films ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})",
            values,
        )


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
    return {layer: content for layer, content in rows}


def get_film(film_id: str) -> dict[str, Any] | None:
    with connect(read_only=True) as con:
        con.execute("SELECT * FROM films WHERE film_id=?", [film_id])
        row = con.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in con.description]
    return dict(zip(cols, row))


def list_films() -> list[dict[str, Any]]:
    with connect(read_only=True) as con:
        con.execute("SELECT * FROM films ORDER BY year, title")
        rows = con.fetchall()
        cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]
