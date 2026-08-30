"""Named groups of films, so the atlas can ask where a worldview sits.

A set is somebody's claim that these films belong together. The claim comes
from outside the project — a magazine's picks, a church's own list, a reader
thread — which is the whole point: the axes were derived without reference to
any of them, so agreement between a set and a region of the space is evidence
rather than construction. That is why `source` is a column and not a comment.

Two kinds of set:

    TITLES   a published list, resolved against the corpus by title. Coverage is
             reported rather than silently dropped, because coverage IS the
             caveat: the Church of Satan list matched 4 of 86, and a reader
             shown "the Satanic set" without that number would take it for a
             measurement of Satanism rather than of four films.

    RULE     assembled from corpus metadata — country, year — where no outside
             list is needed and inventing one would be worse than deriving it.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from .. import db

SEEDS = Path(__file__).resolve().parents[3] / "seeds" / "film-sets.yaml"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\b(the|a|an|of|or)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _corpus() -> list[dict[str, Any]]:
    with db.connect(read_only=True) as con:
        return [dict(r) for r in con.execute(
            "SELECT film_id, title, year, origin_country, original_language "
            "FROM films")]


def _by_rule(films: list[dict[str, Any]], rule: dict[str, Any]) -> list[str]:
    out = []
    for f in films:
        if (c := rule.get("country")) and c.lower() not in (f.get("origin_country") or "").lower():
            continue
        # Language as well as country, because "American film" without it also
        # catches US-produced films shot in another language, which are exactly
        # the ones least like the rest of the group being described.
        if (l := rule.get("language")) and l.lower() not in (f.get("original_language") or "").lower():
            continue
        if (y := rule.get("year_min")) is not None and (f.get("year") or 0) < y:
            continue
        if (y := rule.get("year_max")) is not None and (f.get("year") or 9999) > y:
            continue
        out.append(f["film_id"])
    return out


def resolve(spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(film_ids found, titles that are not in the corpus)."""
    films = _corpus()
    if spec.get("rule"):
        return _by_rule(films, spec["rule"]), []
    index: dict[str, str] = {}
    for f in films:
        index.setdefault(_norm(f["title"]), f["film_id"])
    found, missing = [], []
    for title in spec.get("titles") or []:
        hit = index.get(_norm(title))
        if hit:
            found.append(hit)
        else:
            missing.append(title)
    return sorted(set(found)), missing


def load(path: Path | None = None, progress=None) -> dict[str, Any]:
    """Rebuild every set from the seed file. Idempotent."""
    import yaml

    text = (path or SEEDS).read_text(encoding="utf-8")
    spec = yaml.safe_load(text) or {}
    sets = spec.get("sets") or []
    report = {"sets": 0, "members": 0, "missing": {}}

    db.init_db()
    with db.connect() as con:
        con.execute("DELETE FROM film_set_members")
        con.execute("DELETE FROM film_sets")
        for order, entry in enumerate(sets):
            ids, missing = resolve(entry)
            con.execute(
                "INSERT INTO film_sets (set_id, name, description, source, url, "
                "colour, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?)",
                [entry["id"], entry.get("name") or entry["id"], entry.get("description"),
                 entry.get("source"), entry.get("url"), entry.get("colour"),
                 order, db.now()])
            con.executemany(
                "INSERT OR IGNORE INTO film_set_members (set_id, film_id) VALUES (?,?)",
                [(entry["id"], f) for f in ids])
            report["sets"] += 1
            report["members"] += len(ids)
            if missing:
                report["missing"][entry["id"]] = missing
            if progress:
                asked = len(entry.get("titles") or []) or len(ids)
                progress(f"  {entry['id']:20} {len(ids):4} of {asked} films"
                         + (f"   [{len(missing)} not in the corpus]" if missing else ""))
    return report


def all_sets() -> list[dict[str, Any]]:
    """Every set with its members, ordered as the seed file lists them."""
    with db.connect(read_only=True) as con:
        rows = [dict(r) for r in con.execute(
            "SELECT set_id, name, description, source, url, colour FROM film_sets "
            "ORDER BY sort_order, set_id")]
        members: dict[str, list[str]] = {}
        for r in con.execute("SELECT set_id, film_id FROM film_set_members"):
            members.setdefault(r["set_id"], []).append(r["film_id"])
    for row in rows:
        row["films"] = sorted(members.get(row["set_id"], []))
        row["n"] = len(row["films"])
    return [r for r in rows if r["n"]]
