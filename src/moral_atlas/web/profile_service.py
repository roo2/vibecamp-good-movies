"""Turn one user's captured preferences into a score on each moral axis.

`analysis.user_scores` owns the arithmetic and knows nothing about users; this
module is the join between the product tables and that instrument. It exists so
the route stays a route: read what the person told us, hand it to the scorer,
and describe what came back.
"""
from __future__ import annotations

from ..analysis import user_scores
from .film_service import film_card
from .schemas import MoralProfile, MoralScore, ProfileEvidence
from .store import user_pair_answers, user_rating_inputs

# Below this, the profile is a shape drawn through too few points to trust. The
# API still returns it — a person mid-onboarding should see it filling in — but
# it says so, rather than presenting eight confident numbers built on one film.
MIN_FILMS_FOR_A_READ = 3


def moral_profile(
    user_id: str,
    dim_version: str = user_scores.DEFAULT_DIM_VERSION,
    bank_version: str = user_scores.DEFAULT_BANK_VERSION,
) -> MoralProfile:
    ratings = user_rating_inputs(user_id)
    pairs = user_pair_answers(user_id)
    dimensions = user_scores.load_dimensions(dim_version)
    if not dimensions:
        if dim_version != user_scores.DEFAULT_DIM_VERSION:
            raise LookupError(f"No dimension set {dim_version!r} has been derived.")
        return MoralProfile(
            user_id=user_id, dim_version=dim_version, bank_version=bank_version, scores=[],
            evidence=ProfileEvidence(
                films_rated=sum(1 for _film_id, reaction in ratings if reaction != "havent_seen"),
                films_not_seen=sum(1 for _film_id, reaction in ratings if reaction == "havent_seen"),
                pairs_answered=sum(1 for choice, _film_ids in pairs if choice in ("a", "b")),
                films_used=0, films_without_scores=[],
            ),
            is_provisional=True,
            summary="Your film choices are saved. The shared moral map is still being prepared.",
        )

    preferences = user_scores.rating_preferences(ratings)
    for choice, film_ids in pairs:
        preferences.extend(user_scores.pair_preferences(choice, film_ids))

    stances = user_scores.film_stances(dim_version, bank_version)
    scored = user_scores.score_preferences(preferences, dimensions, stances)

    unscored = sorted({p.film_id for p in preferences if p.film_id not in stances})
    return MoralProfile(
        user_id=user_id,
        dim_version=dim_version,
        bank_version=bank_version,
        scores=[MoralScore(**vars(score)) for score in scored],
        evidence=ProfileEvidence(
            films_rated=sum(1 for _f, reaction in ratings if reaction != "havent_seen"),
            films_not_seen=sum(1 for _f, reaction in ratings if reaction == "havent_seen"),
            pairs_answered=sum(1 for choice, _f in pairs if choice in ("a", "b")),
            films_used=len({p.film_id for p in preferences} - set(unscored)),
            films_without_scores=[_label(film_id) for film_id in unscored],
        ),
        is_provisional=len({p.film_id for p in preferences} - set(unscored)) < MIN_FILMS_FOR_A_READ,
        summary=_summary(scored),
    )


def _label(film_id: str) -> str:
    card = film_card(film_id)
    return card["title"] if card and card.get("title") else film_id


def _summary(scores: list[user_scores.DimensionScore]) -> str:
    """The axis the person committed to hardest, in that axis's own words.

    One axis rather than a ranked list: the pole texts are full sentences, and
    two of them stacked is a wall rather than a reading. The rest of the profile
    is right there underneath it.
    """
    committed = sorted(
        (s for s in scores if s.leaning != "balanced"),
        key=lambda s: -abs(s.score),
    )
    if not committed:
        return ("Nothing you have told us yet pushes hard on any one axis — "
                "rate a few more films and the shape will sharpen.")
    return f"{committed[0].name} — {committed[0].stance}"
