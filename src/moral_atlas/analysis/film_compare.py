"""Two readers, one film, one bank of propositions.

The model comparison elsewhere in this package asks whether different scorers
recover the same AXES, which is a question about a whole corpus and needs
hundreds of films to answer. This asks something smaller and more legible: given
the same film and the same questions, where do two readers actually differ?

It exists because the corpus-level answer was hiding something. Dolphin cannot
write a usable bank of propositions — 188 of its 213 items are claims no film
disagrees with — so on the axis question it looks simply worse. But handed
deepseek's propositions it engages MORE of them than deepseek does, and where
the two split they split systematically rather than randomly. That is invisible
in an aggregate and obvious in a side-by-side.

Nothing here computes a factor. It is a reading aid, and the disagreements are
the point: two competent readers taking opposite sides of the same proposition
about the same film is the most direct evidence available that a verdict is a
judgement rather than a lookup.
"""
from __future__ import annotations

from typing import Any

from .. import db


def _verdicts(scorer: str, bank_version: str, variant: str,
              film_id: str) -> dict[str, dict[str, Any]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, value, confidence, evidence FROM model_verdicts "
            "WHERE scorer=? AND bank_version=? AND variant=? AND film_id=?",
            [scorer, bank_version, variant, film_id],
        ).fetchall()
    return {r["item_id"]: {"value": r["value"], "confidence": r["confidence"],
                           "evidence": r["evidence"] or ""} for r in rows}


def compare(film_id: str, scorers: list[str], bank_version: str,
            variant: str = "subs") -> dict[str, Any]:
    """Side by side on the items both readers answered.

    Agreement is reported on DIRECTION rather than on strength. Whether a film
    affirms a proposition firmly or in passing is a judgement the graded scale
    invites and the two readers calibrate differently; whether it affirms or
    denies is the claim the instrument is actually making.
    """
    with db.connect(read_only=True) as con:
        texts = {r["item_id"]: r["text"] for r in con.execute(
            "SELECT item_id, text FROM item_bank WHERE bank_version=? AND active=1",
            [bank_version])}
        title_row = con.execute("SELECT title, year FROM films WHERE film_id=?",
                                [film_id]).fetchone()

    read = {s: _verdicts(s, bank_version, variant, film_id) for s in scorers}
    engaged = {s: set(v) for s, v in read.items()}
    shared = set.intersection(*engaged.values()) if engaged else set()

    agreed, split = [], []
    for item in sorted(shared):
        sides = {s: read[s][item]["value"] > 0 for s in scorers}
        row = {"item_id": item, "text": texts.get(item, item),
               "by": {s: read[s][item] for s in scorers}}
        (agreed if len(set(sides.values())) == 1 else split).append(row)

    return {
        "film_id": film_id,
        "title": f"{title_row['title']} ({title_row['year']})" if title_row else film_id,
        "bank_version": bank_version,
        "bank_size": len(texts),
        "scorers": scorers,
        "engaged": {s: len(v) for s, v in engaged.items()},
        # Only-one-reader-answered is as informative as a disagreement: it says
        # one of them found a question in the film that the other did not.
        "only": {s: len(engaged[s] - set.union(*(engaged[o] for o in scorers if o != s)))
                 for s in scorers} if len(scorers) > 1 else {},
        "shared": len(shared),
        "agreed": len(agreed),
        "split": split,
        "affirm_rate": {s: (sum(1 for x in v.values() if x["value"] > 0) / len(v))
                        if v else 0.0 for s, v in read.items()},
    }


def films_scored_by_all(scorers: list[str], bank_version: str,
                        variant: str = "subs") -> list[str]:
    """Films every one of these scorers has read against this bank."""
    if not scorers:
        return []
    with db.connect(read_only=True) as con:
        sets = []
        for scorer in scorers:
            sets.append({r["film_id"] for r in con.execute(
                "SELECT DISTINCT film_id FROM model_verdicts WHERE scorer=? "
                "AND bank_version=? AND variant=?", [scorer, bank_version, variant])})
    return sorted(set.intersection(*sets))
