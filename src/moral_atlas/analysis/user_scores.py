"""Put a person on the same axes the films are scored against.

A film's position on an axis is already a settled question: `dimensions.py`
assigns every bank item to one of the eight axes with a polarity, and `scores`
records whether each film affirms or denies each item. What a viewer tells us is
much thinner — a few reactions to named films and a few blind choices between
story descriptions — so the whole job here is turning a handful of preferences
into a defensible position on eight axes without inventing precision.

The move is to score the person in the FILM's units. A preference is a signed
weight on a film, and the person's stance on an axis is the weighted mean of the
item-level verdicts of the films they were drawn to:

    score(axis) =  sum over items  w(film) * polarity(item) * value(film, item)
                   -----------------------------------------------------------
                        sum over items  |w(film)|   +   PRIOR_ITEMS

Three things are doing work in that fraction.

*Signs.* Loving a film pulls you toward what it asserts; `not_for_me` pushes you
away from it, which is a real signal and not a missing one. `havent_seen` is
dropped: it says something about exposure, nothing about morals. A blind pair is
a forced contrast, so the chosen story pulls and the rejected one pushes, each
at half weight — the pair as a whole then carries the same mass as one rating.

*Items, not films, are the unit of evidence.* Summing over items rather than
averaging per film means a film that engages an axis across twenty propositions
counts for more on that axis than one that brushes it in two. It also makes the
denominator a count of evidence, which is what the last term needs.

*PRIOR_ITEMS shrinks toward the middle.* Without it, one film with three items
on an axis and no disagreement among them would report a perfect ±1.0. The
constant is expressed in items, so it says plainly: until roughly eight items'
worth of evidence has accumulated, we are still closer to "we don't know" than
to a pole. `confidence` reports exactly how much of the score that term is
still holding back.

Nothing here is persisted. These numbers are a pure function of the ratings, the
dimension set and the bank, all of which are versioned already; recomputing is
cheap and cannot go stale the way a cached copy would.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from .. import db

DEFAULT_DIM_VERSION = "d1"
DEFAULT_BANK_VERSION = "b1"
MAIN_PASS = "main"

# Reaction -> pull on the film's asserted positions.
REACTION_WEIGHTS = {"loved_it": 1.0, "not_for_me": -1.0, "havent_seen": 0.0}

# A pair is one contrast, so its two halves together weigh the same as one rating.
PAIR_WEIGHT = 0.5

# Evidence, in items, that a score must accumulate before it stops being pulled
# toward the middle. See the module docstring.
PRIOR_ITEMS = 8.0

# Below this the axis is reported as balanced rather than as a pole. A person who
# has genuinely not committed should be told so, not rounded to the nearer side.
LEAN_THRESHOLD = 0.12

BALANCED_STANCE = "The films you were drawn to pull both ways on this one."


@dataclass(frozen=True)
class Preference:
    """One signed pull toward or away from what a film asserts."""
    film_id: str
    weight: float
    source: str          # "rating" or "pair"
    detail: str = ""     # the reaction, or the pair it came from


@dataclass(frozen=True)
class DimensionScore:
    dim_id: int
    name: str
    question: str
    pole_high: str
    pole_low: str
    score: float           # -1..+1, signed toward pole_high
    leaning: str           # "high" | "low" | "balanced"
    stance: str            # what that leaning asserts, in the axis's own words
    evidence_items: float  # weighted item mass behind the score
    films: int             # films that engaged this axis at all
    confidence: float      # 0..1, share of full weight the shrinkage leaves


def load_dimensions(dim_version: str = DEFAULT_DIM_VERSION) -> list[dict[str, Any]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT dim_id, name, question, pole_high, pole_low FROM dimensions "
            "WHERE dim_version=? ORDER BY dim_id", [dim_version],
        ).fetchall()
    return [dict(row) for row in rows]


def film_stances(
    dim_version: str = DEFAULT_DIM_VERSION,
    bank_version: str = DEFAULT_BANK_VERSION,
    variants: Iterable[str] | None = None,
) -> dict[str, dict[int, list[float]]]:
    """{film_id: {dim_id: [polarity-adjusted verdict per item]}}.

    Verdicts are averaged across variants and runs before they are collected, so
    a film scored under four evidence conditions is not four times the evidence,
    and an item those conditions disagree about lands near zero on its own.
    """
    with db.connect(read_only=True) as con:
        assignments = {
            row["item_id"]: (row["dim_id"], row["polarity"])
            for row in con.execute(
                "SELECT item_id, dim_id, polarity FROM item_dimensions "
                "WHERE dim_version=? AND bank_version=? AND pass_name=?",
                [dim_version, bank_version, MAIN_PASS],
            )
        }
        score_rows = con.execute(
            "SELECT film_id, item_id, variant, value FROM scores WHERE bank_version=?",
            [bank_version],
        ).fetchall()

    keep = set(variants) if variants else None
    per_item: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in score_rows:
        if row["item_id"] not in assignments:
            continue
        if keep and row["variant"] not in keep:
            continue
        per_item[(row["film_id"], row["item_id"])].append(row["value"])

    stances: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (film_id, item_id), values in per_item.items():
        dim_id, polarity = assignments[item_id]
        stances[film_id][dim_id].append(polarity * sum(values) / len(values))
    return {film: dict(by_dim) for film, by_dim in stances.items()}


def rating_preferences(ratings: Iterable[tuple[str, str]]) -> list[Preference]:
    """(film_id, reaction) pairs, newest first, one preference per film."""
    seen: set[str] = set()
    out = []
    for film_id, reaction in ratings:
        if film_id in seen:
            continue
        seen.add(film_id)
        weight = REACTION_WEIGHTS.get(reaction, 0.0)
        if weight:
            out.append(Preference(film_id, weight, "rating", reaction))
    return out


def pair_preferences(choice: str, film_ids: list[str], pair_id: str = "") -> list[Preference]:
    """A blind A/B answer, as a pull toward the chosen story and away from the other.

    `neither` is a real answer and not an absent one, but it is a statement about
    both stories at once, and the only honest reading of it is no pull either way.
    """
    if choice not in ("a", "b") or len(film_ids) != 2:
        return []
    chosen, rejected = (film_ids[0], film_ids[1]) if choice == "a" else (film_ids[1], film_ids[0])
    return [
        Preference(chosen, PAIR_WEIGHT, "pair", pair_id),
        Preference(rejected, -PAIR_WEIGHT, "pair", pair_id),
    ]


def score_preferences(
    preferences: Iterable[Preference],
    dimensions: list[dict[str, Any]],
    stances: dict[str, dict[int, list[float]]],
) -> list[DimensionScore]:
    """Weighted mean of the film verdicts, one row per axis, always all of them.

    Axes nobody's films engaged still come back — at zero, with no evidence and
    no confidence. An axis silently missing from a profile reads as neutrality;
    an axis reported with `evidence_items` of 0 reads as the ignorance it is.
    """
    numerator: dict[int, float] = defaultdict(float)
    mass: dict[int, float] = defaultdict(float)
    films_seen: dict[int, set[str]] = defaultdict(set)

    for preference in preferences:
        if not preference.weight:
            continue
        for dim_id, verdicts in stances.get(preference.film_id, {}).items():
            numerator[dim_id] += preference.weight * sum(verdicts)
            mass[dim_id] += abs(preference.weight) * len(verdicts)
            films_seen[dim_id].add(preference.film_id)

    out = []
    for dimension in sorted(dimensions, key=lambda d: d["dim_id"]):
        dim_id = dimension["dim_id"]
        evidence = mass[dim_id]
        score = numerator[dim_id] / (evidence + PRIOR_ITEMS) if evidence else 0.0
        leaning = ("high" if score >= LEAN_THRESHOLD else
                   "low" if score <= -LEAN_THRESHOLD else "balanced")
        out.append(DimensionScore(
            dim_id=dim_id,
            name=dimension["name"],
            question=dimension["question"],
            pole_high=dimension["pole_high"],
            pole_low=dimension["pole_low"],
            score=round(score, 4),
            leaning=leaning,
            stance=(dimension["pole_high"] if leaning == "high" else
                    dimension["pole_low"] if leaning == "low" else BALANCED_STANCE),
            evidence_items=round(evidence, 2),
            films=len(films_seen[dim_id]),
            confidence=round(evidence / (evidence + PRIOR_ITEMS), 4),
        ))
    return out
