"""The dataset the explorer reads, served live.

The interface reads this endpoint rather than a file, so a pipeline run shows
up on reload rather than on rebuild.

Building the document costs a handful of full-table reads and — the expensive
part by far — a thousand-permutation null test, which is a research computation
rather than a request handler. It is cached against the store's own counts, and
it is built at startup so that nobody waits for it.

That startup build is not a nicety. On a laptop the build is 3 seconds; on a
dyno with a fraction of the CPU it was 28, against a platform that hangs up at
30 — so the first visitor after every daily restart was one slow day away from
a page that never loaded at all.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

from fastapi import APIRouter, HTTPException, status

from ... import db
from ...analysis import dataset as dataset_mod

router = APIRouter(prefix="/api", tags=["atlas"])

# Under uvicorn's own logger, because uvicorn configures that one and nothing
# configures ours — a module logger here writes to a handler that does not
# exist, which is how the startup build came to look as though it had never
# run. It had; the request that seemed to prove otherwise had simply arrived
# while it was still going.
log = logging.getLogger("uvicorn.error").getChild("atlas")

_cache: dict[str, Any] = {"key": None, "payload": None}

# One build at a time. Two requests arriving together on a cold cache would
# otherwise each run the permutation test, on one CPU, each making the other
# slower — and it is the same document both times.
_building = threading.Lock()


def _key(dim_version: str, bank_version: str) -> str:
    """What the document was built from, as a string that changes when it does.

    The store's own counts. `totals` is five indexed counts and costs about a
    millisecond. It cannot see an edit that changes no count — retitling a film,
    or re-scoring the same cells to the same values — which is a real gap and a
    far smaller one than the alternatives: there is no file to stat, and a
    timestamp would have been wrong under SQLite too.
    """
    totals = sorted(dataset_mod.totals(dim_version, bank_version).items())
    return json.dumps([dim_version, bank_version, totals], sort_keys=True)


def _stored(key: str) -> Any | None:
    with db.connect(read_only=True) as con:
        row = con.execute("SELECT payload FROM atlas_documents WHERE cache_key=%s",
                          [key]).fetchone()
    return json.loads(row["payload"]) if row else None


def _store(key: str, payload: Any) -> None:
    """Keep this document and drop the one it replaces.

    One row, not a history: an atlas built against a corpus nobody holds any
    more is not evidence of anything, and this is half a megabyte a time.
    """
    with db.connect() as con:
        con.execute(db.upsert("atlas_documents", ["cache_key", "payload", "built_at"]),
                    [key, json.dumps(payload), db.now()])
        con.execute("DELETE FROM atlas_documents WHERE cache_key <> %s", [key])


def _payload(dim_version: str, bank_version: str) -> Any:
    """The document — from memory, then from the store, then built.

    Three tiers because each is roughly a thousand times the cost of the last:
    a dictionary lookup, a single-row read, and a thousand-permutation null
    test.
    """
    key = _key(dim_version, bank_version)
    if _cache["key"] == key:
        return _cache["payload"]

    with _building:
        # Somebody may have built it while this call waited for the lock.
        if _cache["key"] == key:
            return _cache["payload"]
        payload = _stored(key)
        if payload is None:
            payload = dataset_mod.build(dim_version, bank_version)
            try:
                _store(key, payload)
            except db.Error as e:
                # A read-only replica, or a store mid-deploy. Serving the
                # document matters; keeping it is an optimisation.
                log.info("atlas document not stored: %s", e)
        _cache["payload"], _cache["key"] = payload, key
    return payload


def warm(dim_version: str = "d1", bank_version: str = "b1") -> None:
    """Build the document now, off the request path. Never raises.

    A store that is not ready yet is the normal state of a fresh deployment, and
    a warmer that took the process down with it would be a worse bargain than
    the slow first request it exists to prevent.
    """
    try:
        _payload(dim_version, bank_version)
        log.info("atlas document built and cached")
    except Exception as e:                      # a half-run pipeline, not a fault
        log.info("atlas document not built at startup: %s", e)


@router.get("/atlas")
def get_atlas(dim_version: str = "d1", bank_version: str = "b1") -> dict[str, Any]:
    """Everything the dataset explorer draws, from the current store."""
    # Through `db`, not `config`, so this asks the same question the store
    # itself does — and so a test that redirects the store redirects this too.
    # "Is there a store yet?" used to be "does the file exist". A database is
    # always there; what can be missing is the schema inside it, which is what
    # an empty deployment actually looks like.
    with db.connect(read_only=True) as con:
        ready = con.execute(
            "SELECT to_regclass('films') IS NOT NULL AS ready").fetchone()["ready"]
    if not ready:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No store yet — run `atlas init` and ingest before reading the dataset.",
        )

    # Counts, and there is nothing else left to key on: the store is a database
    # on another host now, with no file to stat. Under SQLite the file was
    # right there and still the wrong answer — a write landed in the WAL
    # without necessarily moving the main file's mtime OR its size, measured
    # rather than assumed, so an mtime key served a stale document indefinitely
    # after a pipeline run. That is the exact failure this endpoint exists to
    # avoid, and counts are what notice it.
    #
    # `totals` is five indexed counts and costs about a millisecond. It cannot
    # see an edit that changes no count — retitling a film, or re-scoring the
    # same cells to the same values — which is a real gap and a far smaller one.
    return _payload(dim_version, bank_version)


@router.get("/atlas/films/{film_id}")
def get_film_evidence(film_id: str) -> dict[str, Any]:
    """One film's source text — what every claim about it was read from.

    Its own endpoint rather than part of the index because it is large and only
    wanted for the film somebody opened. Not cached: it is one indexed read,
    and it is served far less often than the index.
    """
    document = dataset_mod.film_evidence(film_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No film {film_id!r}.")
    return document
