"""What a factor is made of, so a reader can disagree with it.

A named axis on its own is an assertion. These are the three things that make it
checkable, and each answers a different objection:

    SCORE          where the corpus as a whole sits on the axis, and how many
                   films took a position at all. An axis every film affirms is
                   not discriminating between films, whatever its eigenvalue —
                   it is a fact about the corpus, and worth seeing as one.

    JUSTIFICATION  the films at either pole, with the verdicts that put them
                   there. This is the answer to "why does it think that": the
                   axis says a film leans high because these specific
                   propositions were affirmed and those denied, and both lists
                   are shown rather than summarised.

    PROPOSITIONS   every item that loaded onto the factor, with how many films
                   affirmed and denied it. An item nobody denies carries no
                   information about differences between films even if it is
                   affirmed constantly, so the split is shown rather than a
                   single engagement count.

Sign convention: a film's position is the mean of its verdicts on the factor's
items, so +1 is a film that affirmed everything it engaged and -1 one that denied
everything. There is no polarity column here, unlike the LLM-derived axes — the
factor's direction is whatever its propositions say when read together, which is
exactly what the naming step was given.
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict
from typing import Any

from .. import db

# Below this a film has taken a position on too little of the axis for its
# score to mean much, and listing it as evidence would be misleading.
MIN_ITEMS_FOR_A_FILM = 3


def _verdicts(scorer: str, bank_version: str, variant: str) -> list[Any]:
    with db.connect(read_only=True) as con:
        return con.execute(
            "SELECT film_id, item_id, value FROM model_verdicts "
            "WHERE scorer=? AND bank_version=? AND variant=?",
            [scorer, bank_version, variant],
        ).fetchall()


def _titles() -> dict[str, str]:
    with db.connect(read_only=True) as con:
        return {r["film_id"]: r["title"] for r in
                con.execute("SELECT film_id, title FROM films")}


def detail(
    scorer: str, bank_version: str, variant: str, groups: dict[str, int],
    texts: dict[str, str], per_pole: int = 6, per_factor_items: int = 40,
) -> dict[int, dict[str, Any]]:
    """Per factor: where the corpus sits, which films anchor each pole, and why."""
    rows = _verdicts(scorer, bank_version, variant)
    titles = _titles()

    # (film, factor) -> the verdicts that film gave on that factor's items.
    by_film: dict[tuple[str, int], list[int]] = defaultdict(list)
    # item -> affirm/deny counts across the whole corpus.
    per_item: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        factor = groups.get(row["item_id"])
        if factor is None:
            continue
        by_film[(row["film_id"], factor)].append(row["value"])
        per_item[row["item_id"]][0 if row["value"] > 0 else 1] += 1

    items_by_factor: dict[int, list[str]] = defaultdict(list)
    for item_id, factor in groups.items():
        items_by_factor[factor].append(item_id)

    out: dict[int, dict[str, Any]] = {}
    for factor, item_ids in items_by_factor.items():
        positions = []
        for (film_id, cell_factor), values in by_film.items():
            if cell_factor != factor or len(values) < MIN_ITEMS_FOR_A_FILM:
                continue
            positions.append({
                "film_id": film_id,
                "title": titles.get(film_id, film_id),
                "score": round(st.mean(values), 3),
                "items": len(values),
            })
        positions.sort(key=lambda row: -row["score"])

        engaged = [row for item in item_ids for row in (per_item.get(item),) if row]
        affirms = sum(row[0] for row in engaged)
        denies = sum(row[1] for row in engaged)

        out[factor] = {
            "corpus_score": round((affirms - denies) / (affirms + denies), 3)
            if affirms + denies else 0.0,
            "films_positioned": len(positions),
            "affirmations": affirms,
            "denials": denies,
            # Every positioned film's score, for a distribution the reader can
            # look at. Top-and-bottom lists flatter an axis: they always look
            # decisive, even when the middle is a shapeless pile and the axis is
            # separating almost nothing.
            "distribution": [row["score"] for row in positions],
            "high": positions[:per_pole],
            "low": list(reversed(positions[-per_pole:])) if positions else [],
            "propositions": sorted(
                ({
                    "item_id": item,
                    "text": texts.get(item, item),
                    "affirms": per_item.get(item, [0, 0])[0],
                    "denies": per_item.get(item, [0, 0])[1],
                } for item in item_ids),
                key=lambda row: -(row["affirms"] + row["denies"]),
            )[:per_factor_items],
        }
    return out


def film_justification(
    scorer: str, bank_version: str, variant: str, groups: dict[str, int],
    texts: dict[str, str], film_id: str, factor: int, limit: int = 8,
) -> list[dict[str, Any]]:
    """The individual verdicts that placed one film on one axis.

    The bottom of the drill-down: a reader who doubts a film's position can read
    the propositions it was judged on and the direction of each judgement.
    """
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, value, evidence FROM model_verdicts WHERE scorer=? "
            "AND bank_version=? AND variant=? AND film_id=?",
            [scorer, bank_version, variant, film_id],
        ).fetchall()
    return [
        {"item_id": row["item_id"], "text": texts.get(row["item_id"], row["item_id"]),
         "verdict": "affirms" if row["value"] > 0 else "denies",
         "evidence": row["evidence"]}
        for row in rows if groups.get(row["item_id"]) == factor
    ][:limit]
