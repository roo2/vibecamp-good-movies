"""Moral positions a person can choose, and where each one sits on the axes.

A stance is a reference set with a face on it. The face is what somebody
recognises; the coordinates are the set's centre of gravity on the three axes,
which is a different thing from the position of the film the face comes from and
usually a better one — Wonder Woman sits at -0.17 along self-determination where
her canon sits at -0.43, and Joker overshoots the red-pilled centre rather than
marking it.

The centroid is expressed in exactly the units `_alignment` compares a person
against: each film's mean verdict on an axis, centred on the corpus baseline. So
a chosen stance can be dropped in wherever an inferred profile would go, and
everything downstream — the ranking, and the note that says WHY a film was
picked — keeps working without knowing the difference.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from .. import db
from ..config import ROOT

SEEDS = ROOT / "seeds" / "moral-stances.yaml"
# A set needs enough films for its centre to mean anything. The smallest one in
# use has thirteen; this only catches a set emptied by a corpus change, which
# would otherwise put every chooser at the origin and look like working.
MIN_MEMBERS = 8


@lru_cache(maxsize=1)
def definitions() -> list[dict[str, Any]]:
    data = yaml.safe_load(SEEDS.read_text()) or {}
    return list(data.get("stances", []))


def catalogue() -> list[dict[str, Any]]:
    """What the picker shows: a face, a claim, and something to draw."""
    out = []
    for row in definitions():
        film = db.get_film(row["film_id"])
        # The character where there is one, the poster where there is not. The
        # screen asks which PERSON speaks to somebody and a poster is mostly
        # title treatment, so the fallback is a compromise rather than the plan.
        out.append({
            "stance_id": row["stance_id"],
            "character": row["character"],
            "line": row["line"],
            "film_id": row["film_id"],
            "film_title": (film or {}).get("title"),
            "artwork_url": row.get("image_url") or (film or {}).get("artwork_url"),
            "shows_character": bool(row.get("image_url")),
        })
    return out


def _members(sets: list[str]) -> set[str]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT film_id FROM film_set_members WHERE set_id IN "
            f"({','.join('?' * len(sets))})", list(sets)).fetchall()
    return {r["film_id"] for r in rows}


def centroid(stance_id: str, stances: dict[str, dict[int, Any]],
             baseline: dict[int, tuple[float, float]] | None) -> dict[int, float] | None:
    """Where a stance sits, as a profile the alignment can read.

    Returns None when the stance is unknown or its sets have too few films left
    in the corpus, so a caller falls back to not weighting morality at all
    rather than silently placing everyone at the origin.
    """
    row = next((r for r in definitions() if r["stance_id"] == stance_id), None)
    if row is None:
        return None
    members = _members(row["sets"]) & set(stances)
    if len(members) < MIN_MEMBERS:
        return None
    totals: dict[int, list[float]] = {}
    for film_id in members:
        for dim_id, verdicts in stances[film_id].items():
            if not verdicts:
                continue
            middle, _spread = (baseline or {}).get(dim_id, (0.0, 1.0))
            totals.setdefault(dim_id, []).append(sum(verdicts) / len(verdicts) - middle)
    return {dim: sum(v) / len(v) for dim, v in totals.items() if v}
