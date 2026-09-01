"""Recommend by co-preference: which films are liked by the same people.

This is a different kind of claim from the rest of the package. Everything else
here measures what a film ARGUES, read from its own dialogue. This measures only
that the same people tend to like two films, and offers no account of why. It
carries no moral content and cannot explain itself.

It is here because it predicts far better. On 162,265 outside raters, ordering
a film someone liked above one they disliked:

    neighbour films (this module)   83%
    ideological set membership      63%
    the moral axes                  57%     (50 is chance)

and with the weights learned rather than assumed, adding the moral score on top
of this one does not improve a held-out prediction at all. So the axes stop
being the ranking and become the explanation, which is the job they are good at:
a neighbour similarity can tell you that people like you liked this film, and
never why.

The similarities live in `film_neighbours`, derived from an outside ratings
corpus. Nothing here reads that corpus at runtime — only the aggregate table.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from .. import db

# A pair correlated over a handful of shared raters is noise with a decimal
# point on it. The stored table already applies a floor; this is the runtime
# guard for tables built elsewhere or by an older build.
MIN_SUPPORT = 50

# Thin evidence should not produce a confident score. A film whose neighbours
# the person has barely touched divides by almost nothing without this, and
# lands at the top of the shortlist on the strength of one weak similarity.
PRIOR = 0.5


def load(min_support: int = MIN_SUPPORT) -> dict[str, list[tuple[str, float]]]:
    """{film_id: [(neighbour_id, similarity)]}, strongest first."""
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with db.connect(read_only=True) as con:
        try:
            rows = con.execute(
                "SELECT film_id, neighbour_id, similarity FROM film_neighbours "
                "WHERE support IS NULL OR support >= ? "
                "ORDER BY film_id, similarity DESC", [min_support],
            ).fetchall()
        except Exception:
            # No table yet. Callers fall back to the moral ranking rather than
            # failing, so a database built before this existed still serves.
            return {}
    for row in rows:
        out[row["film_id"]].append((row["neighbour_id"], row["similarity"]))
    return dict(out)


def score(
    weights: Mapping[str, float],
    neighbours: Mapping[str, Iterable[tuple[str, float]]],
    film_ids: Iterable[str] | None = None,
) -> dict[str, float]:
    """How much each film looks like the ones this person liked.

    `weights` is the person's own verdicts — positive for liked, negative for
    rejected — which are used as-is rather than as a set of favourites. A
    rejection is evidence, and a film that resembles what somebody turned down
    should be pushed DOWN rather than merely left alone.

    The denominator is the total similarity actually consulted, so a film
    judged against one neighbour and one judged against forty are on the same
    scale before PRIOR discounts the first for thinness.
    """
    targets = list(film_ids) if film_ids is not None else list(neighbours)
    out: dict[str, float] = {}
    for film_id in targets:
        numerator = denominator = 0.0
        for neighbour_id, similarity in neighbours.get(film_id, ()):
            weight = weights.get(neighbour_id)
            if weight:
                numerator += similarity * weight
                denominator += abs(similarity)
        out[film_id] = numerator / (denominator + PRIOR) if denominator else 0.0
    return out


def preference_weights(preferences: Iterable[Any]) -> dict[str, float]:
    """Collapse a person's preferences to one signed weight per film.

    A film can arrive more than once — rated in the deck and again in a pairwise
    question — and the two can disagree. The later, stronger statement wins by
    magnitude rather than by order, so a firm rejection is not overwritten by an
    incidental mention.
    """
    weights: dict[str, float] = {}
    for pref in preferences:
        weight = getattr(pref, "weight", 0.0)
        if not weight:
            continue
        film_id = getattr(pref, "film_id")
        if abs(weight) >= abs(weights.get(film_id, 0.0)):
            weights[film_id] = weight
    return weights
