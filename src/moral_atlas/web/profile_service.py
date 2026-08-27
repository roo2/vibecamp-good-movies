"""Turn one user's captured preferences into a score on each moral axis.

`analysis.user_scores` owns the arithmetic and knows nothing about users; this
module is the join between the product tables and that instrument. It exists so
the route stays a route: read what the person told us, hand it to the scorer,
and describe what came back.
"""
from __future__ import annotations

from ..config import settings
from ..analysis import user_scores
from .film_service import film_card
from .schemas import MoralProfile, MoralScore, ProfileEvidence
from .store import user_pair_answers, user_rating_inputs

# Below this, the profile is a shape drawn through too few points to trust. The
# API still returns it — a person mid-onboarding should see it filling in — but
# it says so, rather than presenting eight confident numbers built on one film.
MIN_FILMS_FOR_A_READ = 3


def moral_profile(user_id: str) -> MoralProfile:
    """One person against the axes the films produced.

    No version arguments: they used to choose between LLM-derived dimension
    sets, and there is only one source now — the axes the configured scorer
    discovered from its own verdicts. `dim_version` and `bank_version` survive
    in the RESPONSE because the interface displays them as provenance, and are
    reported as what was actually read.
    """
    ratings = user_rating_inputs(user_id)
    pairs = user_pair_answers(user_id)
    # The product reads ONE model's discovered axes. The old eight were a model's
    # answer to "give me eight moral dimensions", never checked against how films
    # actually behave; these are groups of propositions that films answer
    # together, with the count decided by a permutation null. The response shape
    # is unchanged on purpose — the compass screen renders whatever axes it is
    # handed, so swapping the source is a server-side change.
    scorer = settings().product_scorer
    variant = settings().product_variant
    factor_bank = settings().factor_bank
    dimensions = user_scores.factor_axes(scorer, variant, factor_bank)
    if not dimensions:
        return MoralProfile(
            user_id=user_id, dim_version=scorer, bank_version=factor_bank, scores=[],
            evidence=ProfileEvidence(
                films_rated=sum(1 for _film_id, reaction in ratings if reaction in user_scores.SEEN_REACTIONS),
                films_not_seen=sum(1 for _film_id, reaction in ratings if reaction == "havent_seen"),
                pairs_answered=sum(1 for choice, _film_ids in pairs if choice in ("a", "b")),
                films_used=0, films_without_scores=[],
            ),
            is_provisional=True,
            summary="Your film choices are saved. The moral axes are still being "
                    "derived from how films answer them.",
        )

    preferences = user_scores.rating_preferences(ratings)
    for choice, film_ids in pairs:
        preferences.extend(user_scores.pair_preferences(choice, film_ids))

    stances = user_scores.factor_stances(scorer, variant, factor_bank)
    scored = user_scores.score_preferences(preferences, dimensions, stances)

    unscored = sorted({p.film_id for p in preferences if p.film_id not in stances})
    return MoralProfile(
        user_id=user_id,
        dim_version=scorer,
        bank_version=factor_bank,
        scores=[MoralScore(**vars(score)) for score in scored],
        evidence=ProfileEvidence(
            films_rated=sum(1 for _f, reaction in ratings if reaction in user_scores.SEEN_REACTIONS),
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

    The axis NAME is deliberately not included. It used to lead — "Redemption
    and family vs judgment and individualism — A person's past defines their
    character..." — which made the reader parse a label before reaching the
    sentence that actually says something about them. The sentence stands on its
    own, and the name is on the axis a few lines below.
    """
    committed = sorted(
        (s for s in scores if s.leaning != "balanced"),
        key=lambda s: -abs(s.score),
    )
    if not committed:
        return ("Nothing you have told us yet pushes hard on any one axis — "
                "rate a few more films and the shape will sharpen.")
    return committed[0].stance
