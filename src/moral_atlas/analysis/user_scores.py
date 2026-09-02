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

That count has to be a count of evidence ON THIS AXIS, and for a while it was
not. Once every proposition began counting on every axis in proportion to its
loading, every axis drew on the same propositions, so `len()` of a film's
stance became identical across axes — measured across 565 films, the spread
between a film's busiest and emptiest axis was exactly zero. The number still
varied between films and so still looked like it was working. `Stance.mass`
is the fix: the loading weight actually behind the position, divided by the
solution's mean loading so it stays denominated in propositions and
PRIOR_ITEMS keeps its meaning. A film answering twenty propositions that barely touch an
axis now counts as the little evidence it is.

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

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from .. import db
from ..llm.schemas import MAX_STRENGTH
from . import axis_placement, factor_names

class Stance(list):
    """A film's verdicts on one axis, plus how much evidence they amount to.

    A plain list of floats, pre-scaled so `sum(x)/len(x)` is the weighted mean
    — every existing caller and test keeps working unchanged. `mass` rides
    alongside for the callers that need to know how much the position is worth
    rather than merely which way it points.

    The unweighted stances built by `film_stances` and by tests are plain
    lists, where every proposition counts once and the mass IS the count.
    `evidence()` reads either.
    """

    __slots__ = ("mass",)

    def __init__(self, values, mass: float | None = None):
        super().__init__(values)
        self.mass = float(len(self)) if mass is None else float(mass)


def evidence(values) -> float:
    """How many propositions' worth of evidence a stance represents."""
    return float(getattr(values, "mass", len(values)))


DEFAULT_DIM_VERSION = "d1"
DEFAULT_BANK_VERSION = "b1"
MAIN_PASS = "main"

# Reaction -> pull on the film's asserted positions.
#
# `neutral` pushes AWAY, gently. A film that argues hard for something and left
# you unmoved is evidence about you: indifference to a conviction is a mild form
# of not sharing it. Not the same evidence as disliking it, which is why the
# weight is roughly a third — a shrug should be able to be outvoted by a single
# film you loved.
#
# `havent_seen` is the one reaction that stays at zero, and the distinction
# matters: one is an answer, the other is the absence of one. Only the second
# means we should deal more films.
REACTION_WEIGHTS = {"loved_it": 1.0, "not_for_me": -1.0, "neutral": -0.35, "havent_seen": 0.0}

# Reactions that mean the person actually watched the film.
SEEN_REACTIONS = {"loved_it", "not_for_me", "neutral"}

# A pair is one contrast, so its two halves together weigh the same as one rating.
PAIR_WEIGHT = 0.5

# Evidence, in items, that a score must accumulate before it stops being pulled
# toward the middle. See the module docstring.
PRIOR_ITEMS = 8.0

# Below this the axis is reported as balanced rather than as a pole. A person who
# has genuinely not committed should be told so, not rounded to the nearer side.
#
# IN UNITS OF HOW WIDE THE AXIS RUNS, not in raw score. A fixed distance means
# different things on different axes and drifts as the corpus grows: the axes of
# the current reading spread 0.28, 0.14 and 0.18, so one number sets a bar three
# tenths of the way out on the first and eight tenths on the second, for no reason
# but that the first happens to be wider. Expressed against the axis's own
# spread it means the same thing everywhere and keeps meaning it as films are
# added. 0.6 is where the old fixed 0.12 sat against the average axis, so this
# changes the shape of the rule without moving its overall strictness.
LEAN_THRESHOLD = 0.6

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
    pole_high_label: str   # the same two ends in two or three words, for a scale
    pole_low_label: str
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
    """(film_id, reaction) pairs, newest first, one preference per film.

    Newest wins, because changing your mind should count. But `havent_seen`
    cannot win, because it is not a change of mind — it is the absence of an
    answer, and the absence of an answer must not erase one. Anything at zero
    weight is skipped WITHOUT claiming the film, so an older real reaction
    behind it still counts.

    This is not hypothetical. A live user answered `not_for_me` on nineteen
    films and `loved_it` on one, and the deck then wrote `havent_seen` over
    all twenty — three times each, within minutes, without them acting. Every
    one of their answers was masked, their moral profile came back empty on
    all three axes, and their recommendations were the corpus in alphabetical
    order at zero agreement. The deck writing those rows is a separate defect
    and is the frontend's to fix; this makes the scoring robust to it either
    way, because a reaction the module already documents as saying "nothing
    about morals" should never be able to overwrite one that does.
    """
    seen: set[str] = set()
    out = []
    for film_id, reaction in ratings:
        if film_id in seen:
            continue
        weight = REACTION_WEIGHTS.get(reaction, 0.0)
        if not weight:
            continue
        seen.add(film_id)
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


def corpus_baseline(
    stances: dict[str, dict[int, Any]],
) -> dict[int, tuple[float, float]]:
    """Where the middle of each axis actually is, and how wide the axis runs.

    ZERO IS NOT THE MIDDLE. Films average +0.202 on the strongest
    axis of the current reading and +0.117 on the next, because the corpus is
    not symmetric about the origin and nothing says it should be. A person at
    0.00 on an axis whose films average +0.117 is not undecided about it — they
    sit nearly a full standard deviation below the typical film, which is a
    position, and a strong one.

    Measured consequence, on a template built from two independent lists of
    Catholic films: read from zero, the axis those lists are most displaced on
    carried 2% of the profile's weight and the top recommendation was Zootopia.
    Read from the corpus, the same axis carries 41% and the recommendations
    become The Exorcist, Narnia, Noah — one of which is on both lists.

    Returns, per axis, the mean and standard deviation of every film's position
    — a plain description of where the axis sits and how far it runs. Callers
    decide what to do with the spread, because they want different things from
    it: `score_preferences` scales its lean threshold by the ABSOLUTE spread, so
    "distinctive" means the same fraction of an axis wherever you stand;
    `_alignment` scales by the spread RELATIVE to the average axis, which
    equalises them without moving the size of the number it returns.

    Nothing here is a constant. It is measured from the films in the store on
    every request, so it tracks the corpus as films are added.
    """
    per_axis: dict[int, list[float]] = defaultdict(list)
    for by_axis in stances.values():
        for dim_id, values in by_axis.items():
            if values:
                per_axis[dim_id].append(sum(values) / len(values))
    spread: dict[int, float] = {}
    mean_of: dict[int, float] = {}
    for dim_id, xs in per_axis.items():
        mean = sum(xs) / len(xs)
        var = sum((x - mean) ** 2 for x in xs) / max(len(xs) - 1, 1)
        mean_of[dim_id] = mean
        spread[dim_id] = var ** 0.5
    return {dim_id: (mean_of[dim_id], spread[dim_id] or 1.0) for dim_id in per_axis}


def score_preferences(
    preferences: Iterable[Preference],
    dimensions: list[dict[str, Any]],
    stances: dict[str, dict[int, list[float]]],
    baseline: dict[int, tuple[float, float]] | None = None,
) -> list[DimensionScore]:
    """Weighted mean of the film verdicts, one row per axis, always all of them.

    Axes nobody's films engaged still come back — at zero, with no evidence and
    no confidence. An axis silently missing from a profile reads as neutrality;
    an axis reported with `evidence_items` of 0 reads as the ignorance it is.

    `baseline` moves the origin of each axis to the average film — see
    `corpus_baseline`, which explains why that is the honest reference. It also
    fixes what the shrinkage prior means: with it, somebody who has told us
    nothing sits at the average film rather than at an arbitrary zero that may
    itself be an extreme position. Omitted, the scores are raw, which is what
    the legacy dimension set and the hand-built fixtures in the tests want.
    """
    numerator: dict[int, float] = defaultdict(float)
    mass: dict[int, float] = defaultdict(float)
    films_seen: dict[int, set[str]] = defaultdict(set)

    for preference in preferences:
        if not preference.weight:
            continue
        for dim_id, verdicts in stances.get(preference.film_id, {}).items():
            if not verdicts:
                continue
            # Position and evidence, multiplied back together. Both halves of
            # the fraction have to be denominated the same way: weighting the
            # denominator by loading mass while the numerator still counted
            # propositions would inflate every score whose propositions load
            # weakly, which is precisely the case the mass exists to discount.
            weight = evidence(verdicts)
            middle = (baseline or {}).get(dim_id, (0.0, 1.0))[0]
            numerator[dim_id] += (preference.weight * weight
                                  * (sum(verdicts) / len(verdicts) - middle))
            mass[dim_id] += abs(preference.weight) * weight
            films_seen[dim_id].add(preference.film_id)

    out = []
    # Caller order, deliberately. Re-sorting by dim_id here threw away the
    # support order factor_axes had just applied, so a person's compass listed
    # the axes by an internal id while the atlas and the film cards listed them
    # by how well supported they are. Both loaders order their own rows — the
    # legacy dimensions query by dim_id, factor_axes by factor_names.by_support
    # — so preserving what arrives is right for either.
    for dimension in dimensions:
        dim_id = dimension["dim_id"]
        accumulated = mass[dim_id]
        score = (numerator[dim_id] / (accumulated + PRIOR_ITEMS)
                 if accumulated else 0.0)
        # Scaled by this axis's own width when we know it. Without a baseline
        # the widths are unknown and the threshold stays the raw distance it
        # has always been, which is what the legacy dimension set expects.
        width = (baseline or {}).get(dim_id, (0.0, None))[1]
        bar = LEAN_THRESHOLD * width if width else 0.12
        leaning = ("high" if score >= bar else
                   "low" if score <= -bar else "balanced")
        out.append(DimensionScore(
            dim_id=dim_id,
            name=dimension["name"],
            question=dimension["question"],
            pole_high=dimension["pole_high"],
            pole_low=dimension["pole_low"],
            # The LLM-derived dimension set has no labels; falling back to the
            # axis name keeps both ends readable rather than blank.
            pole_high_label=dimension.get("pole_high_label") or dimension["name"],
            pole_low_label=dimension.get("pole_low_label") or dimension["name"],
            score=round(score, 4),
            leaning=leaning,
            stance=(dimension["pole_high"] if leaning == "high" else
                    dimension["pole_low"] if leaning == "low" else BALANCED_STANCE),
            evidence_items=round(accumulated, 2),
            films=len(films_seen[dim_id]),
            confidence=round(accumulated / (accumulated + PRIOR_ITEMS), 4),
        ))
    return out


# --------------------------------------------------------------------------
# The discovered axes, in the shape the scoring above already expects
# --------------------------------------------------------------------------
#
# `film_stances` above reads the LLM-derived dimension set: a model was asked
# for eight axes, and `item_dimensions` records which axis each bank item was
# assigned to AND a polarity, because the model was also asked which pole
# affirming the item points to.
#
# The discovered factors carry no polarity, and the omission is not an
# oversight. An axis produced by asking a model for one has a direction because
# the model declared one; a factor produced by grouping items that films answer
# together has whatever direction its propositions have when read as a set,
# which is precisely what the naming step was shown. Inventing a polarity here
# would be re-imposing the judgement this whole route exists to remove — so a
# film's position on a factor is simply the mean of its verdicts on that
# factor's items.


# How many axes a person is shown.
#
# Three, and the number has moved twice for reasons worth keeping. It was two
# under principal components because the third of three failed three validity
# tests of four. It went to three under common factors, where all three placed a
# person above their own noise ceiling. It went back to two when those three
# were rotated into orthogonal composites — and that is what was undone.
#
# The composites were tidier and measured less. They cost little on separating
# the lists that ought to be distinct (0.911 to 0.906, inside the noise) and a
# great deal on reading a PERSON: the axis that placed somebody best of the
# three, at 0.616 against a 0.248 ceiling, became a composite that managed 0.192
# against 0.178. Half the compass went marginal to buy a squarer plane. They
# also took away the only axis on which the feminist list parts company with the
# devotional ones, which was the largest single separation in the corpus.
#
# `settings().max_axes` caps every reading at this same number so the models can
# be compared; the null still decides what each bank supports and `n_supported`
# records it.
PRODUCT_AXES = 3

# A factor needs items before it is a factor. Three of the twenty axes the last
# rebuild produced were built from a SINGLE proposition, and one of those was
# strong enough by eigenvalue to reach the product — so a person was being read
# on "collective science vs individual conscience" from one sentence that
# happened to correlate with nothing else. That is not a dimension of moral
# disagreement, it is an orphan item with a name on it. The atlas still shows
# them, because seeing that they exist is the point of an audit page.
MIN_AXIS_ITEMS = 3


def factor_axes(scorer: str, variant: str, bank_version: str,
                limit: int | None = PRODUCT_AXES) -> list[dict[str, Any]]:
    """The best-supported named factors, shaped like `dimensions` rows.

    Ordered by `factor_names.by_support` — margin over the permutation null
    first, then eigenvalue — the same function the atlas and the film pages
    sort through, so an axis holds its position wherever a reader meets it.
    Margin leads because every one of these already beat the null, so the
    question is no longer whether they are real but how certainly.
    """
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT factor_id, name, question, pole_high, pole_low, pole_high_label, "
            # n_items is selected because by_support ties on it. Leaving it out
            # made the tie-break silently inert and the order fell through to
            # the axis name, which is alphabetical and means nothing.
            # margin is selected because by_support orders on it. n_items was
            # left out of this list once already and the tie-break it feeds went
            # silently inert; the same omission here would put the axes in a
            # different order from every other screen.
            "pole_low_label, eigenvalue, n_items, margin FROM latent_factors "
            "WHERE scorer=? AND variant=? AND bank_version=? "
            "AND n_items>=? "
            # An axis the namer would not call coherent should not be handed to
            # somebody as a reading of what they believe. It stays in the atlas,
            # where the warning beside it is the point.
            "AND (coherent IS NULL OR coherent=1) "
            # Ordered in Python by factor_names.by_support, not here: the atlas
            # and the film reading sort through that same function, and a
            # second ORDER BY kept in step by hand is one that eventually is
            # not.
            "",
            [scorer, variant, bank_version, MIN_AXIS_ITEMS],
        ).fetchall()
    # The short labels ride along with the sentences: a score is a point on a
    # line, and a line needs a word at each end before the number means anything.
    #
    # ONE AXIS PER FACTOR, and no longer enforced here. Several groups used to
    # be able to load on the same factor — eight of the twenty loaded on the
    # first — so this deduplicated them by shared eigenvalue, because showing
    # six axes in a row implies six independent readings of a person when five
    # may be one reading rephrased. `item_groups` now assigns groups to factors
    # one-to-one, so two groups cannot share a factor and there is nothing left
    # to remove; the guarantee is pinned by
    # `test_two_groups_never_claim_the_same_factor`. Keeping the filter meant
    # keeping a rule that could only ever fire on a coincidence of two distinct
    # factors rounding to the same eigenvalue — silently dropping a real axis.
    rows = sorted((dict(r) for r in rows), key=factor_names.by_support)
    axes = [{"dim_id": r["factor_id"], "name": r["name"], "question": r["question"],
             "pole_high": r["pole_high"], "pole_low": r["pole_low"],
             "pole_high_label": r["pole_high_label"] or r["name"],
             "pole_low_label": r["pole_low_label"] or r["name"]}
            for r in rows]
    if limit:
        axes = _placeable_first(scorer, variant, bank_version, axes)
    return axes[:limit] if limit else axes


def _placeable_first(scorer: str, variant: str, bank_version: str,
                     axes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Axes that can place a PERSON, ahead of ones that only order films.

    Margin says an axis is really there in the corpus. It says nothing about
    whether a person's position on it can be told from their film choices, and
    the compass needs the second thing — a marker placed by noise looks exactly
    like a marker placed by conviction.

    The two questions came apart on the 2026-09 corpus. "Intrinsic vs
    Utilitarian" took the second slot by clearing the null 22% to 20%, a
    two-point gap that is a tie, and it places people at 0.142 against its own
    noise ceiling of 0.210 — it cannot place them at all. It is the same axis
    dropped the round before for the same failure, readmitted by two points of
    margin. The axis it displaced places people better than any other (0.604).

    So the gate is applied only to the ORDER, never to the membership: axes that
    place people rise, the rest keep their relative order behind them, and
    nothing is deleted. An axis with no verdict is treated as passing, so a
    corpus that has never been measured this way behaves exactly as before.

    Deliberately NOT ideological separation, though that would also promote the
    right axis here. This project reports that its axes separate ideological
    lists; selecting them for doing so would turn that finding into a
    restatement of the selection rule.
    """
    verdicts = axis_placement.load(scorer, variant, bank_version)
    if not verdicts:
        return axes
    # Stable: `sorted` keeps by_support order within each group.
    return sorted(axes, key=lambda a: not verdicts.get(a["dim_id"], True))


def factor_stances(
    scorer: str, variant: str, bank_version: str,
) -> dict[str, dict[int, Stance]]:
    """{film_id: {factor_id: [verdict per item]}}, each verdict pointed the right way.

    A verdict is flipped when its proposition is reverse-keyed. A factor can
    hold both "selfishness is necessary for survival" and "altruism is morally
    superior" — they belong together because films answer them together, and
    they point in opposite directions. Averaging the raw verdicts treats a film
    that DENIES the first as leaning the same way as one that DENIES the second,
    when they are saying opposite things.

    Measured on the corpus before this was fixed: 85 of 298 propositions loaded
    against their own factor's majority, the mean film position moved by 0.367
    on a scale of -1..1, and 4.4% of positions sat on the wrong side of the
    axis entirely. Apollo 13 read +1.00 on absurdity-versus-order and belongs at
    -1.00.

    Items with no recorded loading are counted as written, which is what they
    were before the column existed.
    """
    with db.connect(read_only=True) as con:
        assignments = {}
        for r in con.execute(
                "SELECT item_id, factor_id, loading, loadings FROM latent_factor_items "
                "WHERE scorer=? AND variant=? AND bank_version=?",
                [scorer, variant, bank_version]):
            every = json.loads(r["loadings"]) if r["loadings"] else None
            assignments[r["item_id"]] = (r["factor_id"], r["loading"], every)
        rows = con.execute(
            "SELECT film_id, item_id, value FROM model_verdicts WHERE scorer=? "
            "AND variant=? AND bank_version=?", [scorer, variant, bank_version],
        ).fetchall()

    # EVERY PROPOSITION COUNTS ON EVERY AXIS IT SPEAKS TO, in proportion to how
    # much it speaks to each. Filing a proposition under one factor and scoring
    # films from that group alone discards its loading on the others — 22% of
    # the total loading mass on the current reading, with 29% of propositions
    # carrying a second loading at least 60% as strong as their first.
    #
    # Measured by splitting the propositions in half and asking whether the two
    # halves place films in the same order, weighting by every loading is better
    # or equal on all three axes and roughly doubles agreement on the second.
    #
    # Emitted pre-scaled rather than as (value, weight) pairs so that callers
    # taking a plain mean get the weighted one: dividing each weight by the mean
    # weight leaves sum/len equal to the weighted average, and leaves len() still
    # counting how many propositions contributed.
    #
    # HOW MUCH the position is worth travels separately, as `Stance.mass`,
    # because the pre-scaling destroys it — the scaled weights sum to len() by
    # construction. That is why `len()` stopped meaning anything per-axis once
    # every proposition began counting on every axis: the busiest and emptiest
    # axis of a film came out identical, to the proposition. Mass is the real
    # loading weight behind the position, divided by the solution's mean
    # loading so it is still denominated in propositions.
    per_film: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        per_film[row["film_id"]][row["item_id"]] = float(row["value"]) / MAX_STRENGTH

    # The loading vector is stored in factor_id order, so a factor indexes it
    # directly and nothing has to look up which eigen-factor a group sits on.
    factors = sorted({home for home, _l, _e in assignments.values()})

    # What one proposition's worth of evidence weighs. ONE constant for the
    # whole solution, not one per axis and not one per film. Anything that
    # varies with the film cancels out of the comparison between that film's
    # own axes, which is how `len()` came to weight nothing. A per-AXIS
    # divisor is subtler and just as wrong: it measures a film against what
    # that axis had to offer, so an axis whose propositions all load at 0.1
    # would count a film answering all of them as heavily as an axis loading
    # at 0.9, when the weak axis's verdicts are barely about it.
    #
    # Dividing by the mean loading keeps mass denominated in propositions, so
    # PRIOR_ITEMS still means what its docstring says it means.
    def strength_of(assignment, factor: int) -> float:
        home, loading, every = assignment
        if every and factor < len(every):
            return abs(every[factor])
        if home == factor:
            return abs(loading) if loading is not None else 1.0
        return 0.0

    all_weights = [w for a in assignments.values() for factor in factors
                   if (w := strength_of(a, factor))]
    unit = (sum(all_weights) / len(all_weights)) if all_weights else 1.0

    stances: dict[str, dict[int, Stance]] = defaultdict(dict)
    for film, verdicts in per_film.items():
        for factor in factors:
            weighted: list[tuple[float, float]] = []
            for item_id, value in verdicts.items():
                assignment = assignments.get(item_id)
                if assignment is None:
                    continue
                home, loading, every = assignment
                if every and factor < len(every):
                    strength = every[factor]
                elif home == factor:
                    strength = loading if loading is not None else 1.0
                else:
                    continue                     # older rows: assigned factor only
                if not strength:
                    continue
                direction = -1.0 if strength < 0 else 1.0
                weighted.append((value * direction, abs(strength)))
            if not weighted:
                continue
            total_weight = sum(w for _v, w in weighted)
            mean_weight = total_weight / len(weighted)
            if not mean_weight:
                continue
            stances[film][factor] = Stance(
                (v * (w / mean_weight) for v, w in weighted),
                mass=total_weight / (unit or 1.0))
    return {film: dict(by_factor) for film, by_factor in stances.items()}
