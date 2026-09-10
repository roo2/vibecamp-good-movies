"""Derived documents that are expensive to build and cheap to keep.

Two endpoints serve a page that is really the output of a statistical run: the
atlas document is a thousand-permutation null test, and a model's factors are
two hundred. Three seconds of arithmetic each on a laptop; on the machine that
serves them, forty and twelve.

Both used to hold their answer in a module-level dict, which is the right first
thought and has one flaw: a process is not where the answer belongs. Dynos
restart daily, so every morning the first person to open either page paid the
whole cost — and paid it competing with the startup build for the one CPU the
two of them share.

So there are three tiers, each about a thousand times the cost of the one above:

    memory      a dict lookup
    the store   one row, read back by key
    the build   the statistics

The key is a fingerprint of whatever the document was derived from — counts,
almost always, because there is no file to stat and a timestamp would have been
wrong even when there was one. A corpus push moves the counts, the key changes,
and the next request rebuilds. Nothing has to remember to invalidate anything.

Keeping this is safe in a way that caching usually is not: every document here
is derived, reproducible, and belongs to no one. The worst a stale row can do is
be ignored, because a key that no longer matches is never read.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable

from .. import db

log = logging.getLogger("uvicorn.error").getChild("documents")

# One build at a time, per document. Two requests arriving together on a cold
# cache would otherwise each run the same statistics, on one CPU, each making
# the other slower — to produce the identical answer.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_memory: dict[str, dict[str, Any]] = {}


def _lock(name: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(name, threading.Lock())


def key_of(*parts: Any) -> str:
    """A stable string for whatever the document was derived from."""
    return json.dumps(parts, sort_keys=True, default=str)


def _read(name: str, key: str) -> Any | None:
    with db.connect(read_only=True) as con:
        row = con.execute(
            "SELECT payload FROM documents WHERE name=%s AND cache_key=%s",
            [name, key]).fetchone()
    return json.loads(row["payload"]) if row else None


def _write(name: str, key: str, payload: Any) -> None:
    """Keep this document and drop the one it replaces.

    One row per name, not a history: a reading built against a corpus nobody
    holds any more is not evidence of anything, and these run to half a
    megabyte.
    """
    with db.connect() as con:
        con.execute(db.upsert("documents", ["name", "cache_key", "payload", "built_at"]),
                    [name, key, json.dumps(payload), db.now()])
        con.execute("DELETE FROM documents WHERE name=%s AND cache_key<>%s", [name, key])


def get(name: str, key: str, build: Callable[[], Any]) -> Any:
    """The document for `key`, from memory, then the store, then `build()`."""
    held = _memory.get(name)
    if held is not None and held["key"] == key:
        return held["payload"]

    with _lock(name):
        held = _memory.get(name)
        if held is not None and held["key"] == key:
            return held["payload"]

        payload = _read(name, key)
        if payload is None:
            payload = build()
            try:
                _write(name, key, payload)
            except db.Error as e:
                # A read-only replica, or a store mid-deploy. Serving the
                # document is the job; keeping it is an optimisation.
                log.info("%s not stored: %s", name, e)
        _memory[name] = {"key": key, "payload": payload}
    return payload


def forget(name: str) -> None:
    """Drop the in-memory copy. For tests, which share a process."""
    _memory.pop(name, None)
