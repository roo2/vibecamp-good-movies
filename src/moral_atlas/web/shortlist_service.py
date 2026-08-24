"""Choose tonight's films from what the room actually believes.

Everything this needs already exists: `user_scores` puts each person on the eight
axes, and the same module puts every film there too. Ranking is the join — for
each candidate film, how well does what it argues for line up with what these
particular people came out believing?

    alignment(person, film) =  sum over axes  n(axis) * person(axis) * film(axis)
                               ------------------------------------------------
                                 sum over axes  n(axis) * |person(axis)|  + PRIOR

The numerator is a dot product with the signs doing the work: an axis where the
person leans high and the film argues high contributes positively, and an axis
where they pull apart subtracts. Weighting by `n(axis)` — the film's item count
on that axis — means a film is judged mostly on the axes it actually engages,
not on the ones it merely fails to contradict. Dividing by the person's own
commitment keeps the result in -1..1 and stops a strongly-opinionated person
from scoring every film higher than a mild one does.

The part worth arguing about is how a film gets from several people to one
number. It takes the WORST alignment in the room, not the average. A film that
one person loves and another finds obnoxious averages out looking reasonable,
which is exactly the recommendation two people should never be handed; the
question this product asks is what everyone can live with, so the deck is sorted
by the least-happy viewer. Where that ties, the mean breaks it.

Films anyone has already reported seeing — `loved_it` or `not_for_me` — are out.
`havent_seen` stays in: not having seen something is a qualification for tonight,
not a disqualification.
"""
from __future__ import annotations

import math
import random
import statistics as st
from typing import Any

from .. import db
from ..config import settings
from ..analysis import user_scores
from .film_service import _recency as _film_recency
from .store import user_pair_answers, user_rating_inputs


def _recency(year: int | None) -> float:
    """0 for an old film, rising to 1 for the newest — shared with the deck."""
    return _film_recency({"year": year})

# Damps films judged on very little: without it, a single engaged axis could
# hand back a perfect 1.0.
PRIOR = 2.0

# Below this the axis contributed too little to be worth naming on the card.
NOTE_FLOOR = 0.05

# How far the deck is allowed to wander from strict rank order.
#
# Sorting by agreement is correct and, for the same two people, gives the same
# film every single time — which is a strange thing for a product whose answer
# to "what should we watch" is a recommendation rather than a computation. The
# top of the list is usually several films that fit about equally well, and
# picking the same one forever makes the other equals invisible.
#
# So the order is SAMPLED rather than sorted: each film's key is its agreement
# plus Gumbel noise scaled by this, which is exactly Plackett-Luce sampling with
# weights exp(agreement / VARIATION). Two films a hundredth apart swap about
# half the time; a film 0.2 behind leads roughly one run in fifty; a film that
# genuinely pulls against the room effectively never leads. Variation among
# equals, not a lottery.
#
# Set to 0 for a deterministic deck, which is what the ranking tests want.
VARIATION = 0.05

# How much a film being recent is worth, on the same scale as the agreement it
# is added to.
#
# Two people testing this found the recommendations old, and nothing in the
# ranking had an opinion about that: a 1954 film that fits is scored exactly like
# a 2019 film that fits equally well, and there are decades more old films than
# new ones for it to draw from.
#
# The size is measured rather than guessed, across six real profiles and their
# top six recommendations each:
#
#     weight   median year   2010+   pre-2000   fit given up
#      0.15       2014        88%       0%         0.007
#      0.40       2014        91%       0%         0.007
#      0.40 with a straight-line curve — 2020, 88%, and two distinct leaders in
#      forty runs instead of four, because "newest" is a total order and a total
#      order has one winner.
#
# So 0.40 against the saturating curve: it costs seven thousandths of fit, it
# empties the top of the deck of films from before 2000, and it leaves the choice
# between modern films where it was — on how well they actually fit.
RECENCY_WEIGHT = 0.40


def _sampled_order(ranked: list[dict[str, Any]], variation: float) -> list[dict[str, Any]]:
    """Rank order when variation is 0, a Plackett-Luce sample of it otherwise.

    Recency is folded into the score either way, because preferring newer films
    is a stated part of what a good recommendation is here, not noise on top of
    one. With variation off, the order stays a deterministic function of fit and
    age together.
    """
    def merit(row: dict[str, Any]) -> float:
        return row["agreement"] + RECENCY_WEIGHT * _recency(row.get("year"))

    if variation <= 0:
        return sorted(ranked, key=lambda row: (-merit(row), -row["mean_alignment"], row["id"]))
    chooser = random.SystemRandom()

    def key(row: dict[str, Any]) -> float:
        # -log(-log(u)) is a standard Gumbel draw; adding it to a score and
        # taking the largest is the Gumbel-max trick, so the winner is drawn in
        # proportion to exp(merit / variation) rather than always being the
        # maximum.
        gumbel = -math.log(-math.log(chooser.random()))
        return merit(row) + variation * gumbel

    return sorted(ranked, key=key, reverse=True)


SEEN_REACTIONS = {"loved_it", "not_for_me"}


def _factor_bank() -> str:
    """The bank the product's scorer wrote for itself."""
    return f"{settings().product_scorer}-{settings().product_variant}"


def _alignment(scores: dict[int, float], stances: dict[int, list[float]]) -> tuple[float, dict[int, float]]:
    """One person against one film: the signed match, and the per-axis parts."""
    numerator = denominator = 0.0
    parts: dict[int, float] = {}
    for dim_id, verdicts in stances.items():
        person = scores.get(dim_id, 0.0)
        film = sum(verdicts) / len(verdicts)
        weight = len(verdicts)
        parts[dim_id] = weight * person * film
        numerator += parts[dim_id]
        denominator += weight * abs(person)
    return (numerator / (denominator + PRIOR) if denominator else 0.0), parts


def _member_profiles(user_ids: list[str], dimensions, stances) -> dict[str, dict[int, float]]:
    profiles = {}
    for user_id in user_ids:
        preferences = user_scores.rating_preferences(user_rating_inputs(user_id))
        for choice, film_ids in user_pair_answers(user_id):
            preferences.extend(user_scores.pair_preferences(choice, film_ids))
        profiles[user_id] = {
            score.dim_id: score.score
            for score in user_scores.score_preferences(preferences, dimensions, stances)
        }
    return profiles


def _already_seen(user_ids: list[str]) -> set[str]:
    seen = set()
    for user_id in user_ids:
        for film_id, reaction in user_rating_inputs(user_id):
            if reaction in SEEN_REACTIONS:
                seen.add(film_id)
    return seen


def session_member_ids(share_token: str, viewer_user_id: str) -> list[str] | None:
    """Everyone in the session, but only if the asker is one of them."""
    db.init_db()
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT m.user_id FROM session_members m "
            "JOIN group_sessions s ON s.session_id=m.session_id WHERE s.share_token=? "
            "ORDER BY m.joined_at", [share_token],
        ).fetchall()
    members = [row["user_id"] for row in rows]
    return members if viewer_user_id in members else None


def ranked_shortlist(
    user_ids: list[str], limit: int | None = 6,
    dim_version: str = user_scores.DEFAULT_DIM_VERSION,
    bank_version: str = user_scores.DEFAULT_BANK_VERSION,
    variation: float = VARIATION,
) -> list[dict[str, Any]]:
    dimensions = user_scores.factor_axes(
        settings().product_scorer, settings().product_variant, _factor_bank())
    if not dimensions or not user_ids:
        return []
    names = {d["dim_id"]: d["name"] for d in dimensions}
    stances = user_scores.factor_stances(
        settings().product_scorer, settings().product_variant, _factor_bank())
    profiles = _member_profiles(user_ids, dimensions, stances)
    seen = _already_seen(user_ids)

    ranked = []
    for film_id, film_stances in stances.items():
        if film_id in seen:
            continue
        film = db.get_film(film_id)
        if film is None:
            continue
        # A recommendation is a card with a poster on it. The research corpus is
        # ten times the size of the curated one and carries no artwork, so
        # without this the best-matching film is frequently one the deck can
        # only render as an empty rectangle — a worse answer than the
        # second-best film it can actually show.
        if not (film.get("artwork_url") or "").strip():
            continue
        per_member = {user_id: _alignment(profiles[user_id], film_stances) for user_id in user_ids}
        alignments = [value for value, _parts in per_member.values()]
        ranked.append({
            "id": film["film_id"],
            "title": film["title"],
            "year": film.get("year"),
            "description": film.get("description"),
            "artwork_url": film.get("artwork_url"),
            "agreement": round(min(alignments), 4),
            "mean_alignment": round(st.mean(alignments), 4),
            "note": _note(per_member, names, len(user_ids)),
        })

    ranked = _sampled_order(ranked, variation)
    return ranked[:limit] if limit is not None else ranked


def _note(per_member, names: dict[int, str], n_members: int) -> str | None:
    """Name the axis this film agrees with everyone on, if there is one.

    The per-axis contribution is taken at its WORST across the room for the same
    reason the ranking is: an axis only counts as shared ground if nobody in the
    room is pulling against it.
    """
    shared = {}
    for _value, parts in per_member.values():
        for dim_id, part in parts.items():
            shared[dim_id] = min(shared.get(dim_id, part), part)
    if not shared:
        return None
    dim_id, part = max(shared.items(), key=lambda item: item[1])
    if part <= NOTE_FLOOR:
        return None
    who = "you both" if n_members == 2 else "everyone" if n_members > 2 else "you"
    return f"Agrees with {who} on {names.get(dim_id, 'a shared axis')}"
