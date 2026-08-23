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

import statistics as st
from typing import Any

from .. import db
from ..config import settings
from ..analysis import user_scores
from .store import user_pair_answers, user_rating_inputs

# Damps films judged on very little: without it, a single engaged axis could
# hand back a perfect 1.0.
PRIOR = 2.0

# Below this the axis contributed too little to be worth naming on the card.
NOTE_FLOOR = 0.05

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

    ranked.sort(key=lambda row: (-row["agreement"], -row["mean_alignment"], row["id"]))
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
