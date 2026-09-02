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
from ..llm.schemas import MAX_STRENGTH

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


def _taste_adjusted(scorer: str, bank_version: str, variant: str):
    """{(film_id, dim_id): score} with the taste-predictable part removed.

    Returned empty when nothing has been derived, so a reading with no taste
    coverage — or a database built before this existed — still serves its raw
    positions rather than failing.
    """
    from .. import db

    out: dict[tuple[str, int], float] = {}
    explained: dict[int, float] = {}
    try:
        with db.connect(read_only=True) as con:
            for row in con.execute(
                    "SELECT film_id, dim_id, score, taste_explained "
                    "FROM film_moral_adjusted WHERE scorer=? AND variant=? "
                    "AND bank_version=?", [scorer, variant, bank_version]):
                out[(row["film_id"], row["dim_id"])] = row["score"]
                explained[row["dim_id"]] = row["taste_explained"]
    except Exception:
        return {}, {}
    return out, explained



def _stored_stances(scorer: str, variant: str, bank_version: str):
    """Film positions as the PRODUCT computes them, or {} if it cannot.

    Isolated and forgiving on purpose: the atlas can be pointed at a reading
    that was never stored, and a page that 500s because one model's solution is
    missing is worse than one that falls back to its own arithmetic.
    """
    try:
        from . import user_scores

        return user_scores.factor_stances(scorer, variant, bank_version)
    except Exception:
        return {}


def detail(
    scorer: str, bank_version: str, variant: str, groups: dict[str, int],
    texts: dict[str, str], per_pole: int = 10, per_factor_items: int = 40,
    distance: dict[str, float] | None = None, loadings: dict[str, float] | None = None,
    vectors: dict[str, list[float]] | None = None,
) -> dict[int, dict[str, Any]]:
    """Per factor: where the corpus sits, which films anchor each pole, and why."""
    rows = _verdicts(scorer, bank_version, variant)
    titles = _titles()
    vectors = vectors or {}
    # Both numbers travel together. The adjusted one is what the atlas plots,
    # and the raw one has to stay beside it or the page cannot show the reader
    # what adjusting did — which is most of the argument for adjusting.
    adjusted, taste_explained = _taste_adjusted(scorer, bank_version, variant)

    # THE SAME ARITHMETIC AS EVERYWHERE ELSE. This used to average the RAW
    # verdicts of the propositions filed under a factor: no flip for the ones
    # that read backwards, no weight for how much each speaks to the axis, and
    # only its own propositions counted. So a film strongly affirming
    # reverse-keyed propositions was pushed toward the pole it was arguing
    # against. Wonder Woman read +0.59 toward "predestined order" from 11
    # propositions while its own page read -0.44 toward self-determination from
    # 55, and every proposition listed underneath said self-determination.
    by_film: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
    per_item: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    factors_seen = sorted({f for f in groups.values()})
    for row in rows:
        item = row["item_id"]
        home = groups.get(item)
        if home is None:
            continue
        per_item[item][0 if row["value"] > 0 else 1] += 1
        vector = vectors.get(item)
        for factor in factors_seen:
            if vector is not None and factor < len(vector):
                strength = vector[factor]
            elif home == factor:
                strength = loadings.get(item) if loadings else 1.0
                strength = 1.0 if strength is None else strength
            else:
                continue
            if not strength:
                continue
            direction = -1.0 if strength < 0 else 1.0
            by_film[(row["film_id"], factor)].append(
                (row["value"] * direction / MAX_STRENGTH, abs(strength)))

    items_by_factor: dict[int, list[str]] = defaultdict(list)
    for item_id, factor in groups.items():
        items_by_factor[factor].append(item_id)

    out: dict[int, dict[str, Any]] = {}
    # THE STORED SOLUTION DECIDES A FILM'S POSITION, not the one re-derived for
    # this request.
    #
    # `vectors` arrives from the live report the route just computed. An
    # eigen-solution's component SIGNS are arbitrary, so a fresh derivation can
    # return the same axis pointing the other way — and then this page disagreed
    # with the compass, the film panel, the pole labels and every stored
    # analysis, all of which read `latent_factor_items`. Measured on the 2026-09
    # corpus: 434 of 662 films sat on the OPPOSITE side of the leading axis in
    # the plot from where the product put them. Life Is Beautiful plotted at
    # +0.505 toward determinism while its own bar read -0.615 toward redemption.
    #
    # So the position comes from `factor_stances`, the one implementation the
    # product itself scores people with. The local arithmetic above still backs
    # the per-item evidence, and still stands in when a reading has no stored
    # solution to read.
    stances = _stored_stances(scorer, variant, bank_version)

    for factor, item_ids in items_by_factor.items():
        positions = []
        for (film_id, cell_factor), values in by_film.items():
            if cell_factor != factor or len(values) < MIN_ITEMS_FOR_A_FILM:
                continue
            total = sum(w for _v, w in values)
            if total <= 0:
                continue
            stance = (stances.get(film_id) or {}).get(factor)
            score = (sum(stance) / len(stance)) if stance else (
                sum(v * w for v, w in values) / total)
            row = {
                "film_id": film_id,
                "title": titles.get(film_id, film_id),
                "score": round(score, 3),
                "items": len(values),
            }
            fixed = adjusted.get((film_id, factor))
            if fixed is not None:
                row["score_adjusted"] = round(fixed, 3)
            positions.append(row)
        positions.sort(key=lambda row: -row["score"])

        engaged = [row for item in item_ids for row in (per_item.get(item),) if row]
        affirms = sum(row[0] for row in engaged)
        denies = sum(row[1] for row in engaged)

        out[factor] = {
            # How much of this axis the taste dimensions accounted for. Stored
            # per axis because it is wildly uneven — a fifth of the first, a
            # thirtieth of the second — and a single figure would misdescribe both.
            "taste_explained": (round(taste_explained[factor], 3)
                                if factor in taste_explained else None),
            "corpus_score": round((affirms - denies) / (affirms + denies), 3)
            if affirms + denies else 0.0,
            "films_positioned": len(positions),
            "affirmations": affirms,
            "denials": denies,
            # Every positioned film, for a distribution the reader can look at.
            # Top-and-bottom lists flatter an axis: they always look decisive,
            # even when the middle is a shapeless pile and the axis is separating
            # almost nothing.
            #
            # The films are sent whole rather than as bare scores. A histogram of
            # anonymous numbers can be doubted but not checked — the reader who
            # thinks a bin looks wrong has no way to ask which films are in it.
            # Carrying the titles costs a few tens of KB and turns the shape into
            # something you can open.
            "distribution": positions,
            "high": positions[:per_pole],
            "low": list(reversed(positions[-per_pole:])) if positions else [],
            # Ordered by LOADING — how much each proposition defines this axis
            # — strongest first, which is also how `film_justification` and the
            # naming prompt order their evidence.
            #
            # Engagement order was wrong first: the most-answered proposition
            # is usually the one nearly every film affirms, which is the item
            # that separates films least, and a factor about self-sacrifice
            # opened with a line about technology.
            #
            # Distance from the group centroid was wrong next, and less
            # obviously so. Distance measures an item's position across EVERY
            # factor, so a proposition can sit near the centre while barely
            # loading on this axis at all. Measured on this reading it put the
            # defining proposition of all three axes LAST: "There is a right
            # order that precedes individual choice", loading 0.83 and the
            # largest in the solution, was 23rd of 23. It also decided the
            # truncation, so the eight propositions cut from the 48-item axis
            # were cut by a criterion unrelated to how much they matter.
            "propositions": sorted(
                ({
                    "item_id": item,
                    "text": texts.get(item, item),
                    "affirms": per_item.get(item, [0, 0])[0],
                    "denies": per_item.get(item, [0, 0])[1],
                    "distance": round((distance or {}).get(item, 0.0), 4),
                    "weight": (round(abs((loadings or {}).get(item)), 4)
                               if (loadings or {}).get(item) is not None else None),
                    # Signed, because the magnitude alone cannot say which end
                    # of the axis affirming this proposition puts a film on —
                    # and a factor holds propositions that point both ways, so
                    # a reader scanning the list needs the direction beside the
                    # size rather than having to infer it from the sentence.
                    "loading": (round((loadings or {}).get(item), 4)
                                if (loadings or {}).get(item) is not None else None),
                    "reverse_keyed": ((loadings or {}).get(item) or 0) < 0,
                } for item in item_ids),
                key=lambda row: (-(row["weight"] or 0.0),
                                 (distance or {}).get(row["item_id"], 0.0),
                                 -(row["affirms"] + row["denies"])),
            )[:per_factor_items],
        }
    return out


def film_justification(
    scorer: str, bank_version: str, variant: str, groups: dict[str, int],
    texts: dict[str, str], film_id: str, factor: int, limit: int | None = None,
    vectors: dict[str, list[float]] | None = None,
    loadings: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Every verdict that placed one film on one axis, with which way each points.

    The bottom of the drill-down, and it has to be complete: a reader checking a
    position against eight of the twenty propositions behind it is checking a
    sample somebody else chose. `limit` stays available and defaults to off.

    Each verdict carries its proposition's signed loading, which answers a
    question the page could not previously answer — whether a film is affirming
    a position or DENYING ITS OPPOSITE. Both happen, and they mean the same
    thing. A factor holds "selfishness is necessary for survival" alongside
    "altruism is morally superior"; a film that denies the first and one that
    affirms the second have taken the same side.

    `points_to` resolves that to the pole the verdict actually supports, and
    `weight` is how much the proposition counts toward this axis at all.
    Strongest contributors first, so the reader meets the evidence that decided
    the position rather than whatever was recorded first.

    `contribution` is the signed number this proposition added to the film's
    position on this axis, and the set of them SUMS TO THAT POSITION exactly.
    The position is a weighted mean, sum(v*w)/sum(w), so each term is
    v*w/sum(w) and the arithmetic closes. `weight` alone cannot be read that
    way: it says how much a proposition could have mattered, not which way or
    how much it did, and two propositions of equal weight pointing opposite
    ways cancel to nothing. A reader asking "why is this film HERE" needs the
    signed term, and needs the terms to add up, or the answer is a vibe.
    """
    loadings = loadings or {}
    # EVERY proposition that speaks to this axis, not only those filed under it.
    # The position is computed from all of them, weighted; listing only the
    # filed ones showed a reader a different set from the one that produced the
    # number — on The Lion King, twelve strongly affirmed propositions above a
    # score of +0.16, with the propositions pulling it down not on the page.
    vectors = vectors or {}
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, value, evidence FROM model_verdicts WHERE scorer=? "
            "AND bank_version=? AND variant=? AND film_id=?",
            [scorer, bank_version, variant, film_id],
        ).fetchall()

    # The denominator of the weighted mean, over exactly the propositions
    # listed below — computed first so each row can carry its own share of the
    # result rather than leaving the reader to normalise a column by hand.
    total_weight = 0.0
    for row in rows:
        vector = vectors.get(row["item_id"])
        if vector is not None and factor < len(vector):
            total_weight += abs(vector[factor])
        elif groups.get(row["item_id"]) == factor:
            weight = loadings.get(row["item_id"])
            total_weight += abs(weight) if weight is not None else 1.0

    out = []
    for row in rows:
        item = row["item_id"]
        vector = vectors.get(item)
        if vector is not None and factor < len(vector):
            loading = vector[factor]
            if not loading:
                continue
        elif groups.get(item) == factor:
            loading = loadings.get(item)
        else:
            continue
        # No loading recorded means the proposition is counted as written, which
        # is what every row did before the column existed.
        direction = -1 if (loading is not None and loading < 0) else 1
        affirmed = row["value"] > 0
        out.append({
            "item_id": item,
            "text": texts.get(item, item),
            "verdict": "affirms" if affirmed else "denies",
            # How much weight the film put there, as distinct from which way.
            "strength": abs(row["value"]),
            "emphatic": abs(row["value"]) >= MAX_STRENGTH,
            "reverse_keyed": direction < 0,
            # Whether this proposition is one of the axis's own, or one that
            # belongs elsewhere and still has something to say here. A reader
            # scanning for why a score is lower than it looks needs to see the
            # difference.
            "home": groups.get(item) == factor,
            "points_to": "high" if (affirmed == (direction > 0)) else "low",
            "weight": round(abs(loading), 4) if loading is not None else None,
            # This proposition's signed share of the film's position. These sum
            # to the position itself, so the drill-down is an account of the
            # number rather than a list of things near it.
            "contribution": round(
                (row["value"] / MAX_STRENGTH) * direction
                * (abs(loading) if loading is not None else 1.0) / total_weight, 5
            ) if total_weight else 0.0,
            "evidence": row["evidence"],
        })
    out.sort(key=lambda row: -(row["weight"] or 0))
    return out[:limit] if limit else out
