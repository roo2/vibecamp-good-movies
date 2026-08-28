"""The three pieces that widen the instrument: sampling, semantic cutting, batching.

Each test here pins a specific failure that was measured on the real corpus, so
a regression reads as the bug returning rather than as an assertion moving.
"""
from __future__ import annotations

import pytest

from moral_atlas.analysis import model_bias, sampling, semantic_bank
from moral_atlas.sources import wikidata


# --------------------------------------------------------------------------
# Choosing which films write the propositions
# --------------------------------------------------------------------------

def _film(fid, lang, country, year, genres=("drama film",)):
    import json
    return {"film_id": fid, "title": fid, "year": year,
            "original_language": lang, "origin_country": json.dumps([country]),
            "genres": json.dumps(list(genres))}


LOPSIDED = (
    [_film(f"us{i}", "English", "United States", 2000 + i % 5) for i in range(20)]
    + [_film("kr1", "Korean", "South Korea", 2019),
       _film("ir1", "Persian", "Iran", 2011),
       _film("jp1", "Japanese", "Japan", 1988)]
)


ENGLISH_ALREADY = {f"us{i}" for i in range(20)}


def test_sampling_reaches_the_rare_languages_first_once_english_is_covered():
    """The situation this exists for: 135 films harvested, 122 of them English.

    With English already saturated its marginal worth has collapsed, so every
    remaining pick should go to a language the set does not have. Note that on
    an EMPTY set every film here ties, and correctly so — with nothing chosen,
    no film is more informative than another.
    """
    picks = sampling.select(LOPSIDED, 3, already=ENGLISH_ALREADY)
    languages = [p["original_language"] for p in picks]
    assert set(languages) == {"Korean", "Persian", "Japanese"}, (
        f"expected the three unrepresented languages, got {languages}")


def test_sampling_never_returns_a_film_already_harvested():
    """Re-harvesting a film buys no coverage and costs a full scoring pass."""
    picks = sampling.select(LOPSIDED, 10, already=ENGLISH_ALREADY)
    assert not ({p["film_id"] for p in picks} & ENGLISH_ALREADY)


def test_sampling_stops_when_the_pool_runs_out():
    """Asking for more films than exist returns what there is, not an error."""
    picks = sampling.select(LOPSIDED, 500, already=ENGLISH_ALREADY)
    assert len(picks) == len(LOPSIDED) - len(ENGLISH_ALREADY)


def test_coverage_reports_how_lopsided_a_set_is():
    report = sampling.coverage(LOPSIDED)
    assert report["n_films"] == 23
    assert report["distinct"]["original_language"] == 4
    assert report["dominance"]["original_language"] == pytest.approx(20 / 23)


# --------------------------------------------------------------------------
# Cutting the harvest by meaning
# --------------------------------------------------------------------------

def test_polarity_blocking_keeps_a_negation_out_of_its_own_assertion():
    """Embeddings score these two at 0.59 — higher than the same claim reworded.

    Nothing is allowed to depend on the geometry getting that right, so the
    blocking has to separate them before any clustering happens.
    """
    from moral_atlas.analysis import bank as lexical

    assert lexical.polarity_class("The ends justify the means.") != \
        lexical.polarity_class("The ends do not justify the means.")


def test_a_single_member_neighbourhood_needs_no_model():
    """One sentence cannot contain two claims, so it must not cost a call."""
    class Exploding:
        def parse(self, **kwargs):
            raise AssertionError("a lone proposition was sent to the model")

    group = {"polarity": "plain",
             "members": [{"text": "Mercy is owed to the defeated.", "film_id": "f1"}]}
    out = semantic_bank.distinct_claims(group, Exploding())
    assert [c["text"] for c in out] == ["Mercy is owed to the defeated."]
    assert out[0]["films"] == {"f1"}


def test_support_counts_films_rather_than_sentences():
    """Two propositions from one film are one film's opinion, however worded.

    Counting sentences is what let a single talkative film look like agreement.
    """
    class Splitter:
        def parse(self, **kwargs):
            from moral_atlas.analysis.semantic_bank import Claim, ClaimSet
            return ClaimSet(claims=[Claim(text="Revenge is justified.", members=[1, 2, 3])])

    group = {"polarity": "plain", "members": [
        {"text": "Revenge is just.", "film_id": "f1"},
        {"text": "Vengeance is warranted.", "film_id": "f1"},
        {"text": "Payback is deserved.", "film_id": "f2"},
    ]}
    claim = semantic_bank.distinct_claims(group, Splitter())[0]
    assert claim["support"] == 2, "three sentences from two films is support 2"
    assert claim["films"] == {"f1", "f2"}


def test_consolidation_carries_film_support_across_the_second_pass():
    """The second pass reads claims, not propositions, so support must survive it.

    Losing it here would silently reset every item to support 1 and undo the
    only evidence the bank keeps about how widely a claim is raised.
    """
    claims = [{"text": "Revenge is justified.", "films": {"f1", "f2"}},
              {"text": "Vengeance is warranted.", "films": {"f3"}}]
    assert semantic_bank._films_of(claims[0]) == {"f1", "f2"}
    assert semantic_bank._films_of({"film_id": "f9"}) == {"f9"}
    assert semantic_bank._films_of({"text": "orphan"}) == set()


# --------------------------------------------------------------------------
# Batching the scoring
# --------------------------------------------------------------------------

def test_slices_cover_every_item_exactly_once():
    items = [{"item_id": f"I{n:03d}"} for n in range(97)]
    parts = list(model_bias._slices(items, 40))
    assert [len(p) for p in parts] == [40, 40, 17]
    assert [i["item_id"] for p in parts for i in p] == [i["item_id"] for i in items]


def test_the_batched_prompt_carries_the_film_and_not_the_bank():
    """The whole point of the arrangement: the film is the cacheable prefix.

    If the bank ever ends up in here, every slice resends the evidence and the
    dominant cost is multiplied by the number of slices.
    """
    from moral_atlas.llm import prompts

    system = prompts.scoring_batched_system("SUBTITLES: a line of dialogue")
    assert "SUBTITLES: a line of dialogue" in system
    assert "not_addressed" in system, "the silence instruction must survive batching"
    assert "slice" in system.lower(), "the model must know it is seeing part of a bank"


# --------------------------------------------------------------------------
# Metadata backfill
# --------------------------------------------------------------------------

def test_wikidata_folds_one_row_per_value_into_lists():
    """SPARQL returns the cross product, so three genres arrive as three rows."""
    rows = [
        {"imdb": {"value": "tt1"}, "genresLabel": {"value": "drama film"},
         "directorsLabel": {"value": "Some Director"}},
        {"imdb": {"value": "tt1"}, "genresLabel": {"value": "trial film"},
         "directorsLabel": {"value": "Some Director"}},
    ]
    folded = wikidata._fold(rows)
    assert folded["tt1"]["genres"] == ["drama film", "trial film"]
    assert folded["tt1"]["directors"] == ["Some Director"]


def test_wikidata_drops_unresolved_q_numbers():
    """A bare Q-number in a genre filter is worse than an empty one."""
    rows = [{"imdb": {"value": "tt2"}, "genresLabel": {"value": "Q12345"}},
            {"imdb": {"value": "tt2"}, "genresLabel": {"value": "epic film"}}]
    assert wikidata._fold(rows)["tt2"]["genres"] == ["epic film"]


# --------------------------------------------------------------------------
# Does the instrument reproduce itself?
# --------------------------------------------------------------------------

def _planted(n_films, n_items, k, engagement, rng, noise):
    """Films x items where each item is driven by exactly one of k factors."""
    import numpy as np

    scores = rng.normal(size=(n_films, k))
    owner = np.arange(n_items) % k
    signal = scores[:, owner] + rng.normal(scale=noise, size=(n_films, n_items))
    values = np.where(signal >= 0, 1.0, -1.0)
    # Zero is the missing marker for this estimator, so silence is punched in
    # rather than being a value the signal could take.
    return np.where(rng.random((n_films, n_items)) < engagement, values, 0.0)


def test_split_half_overlap_is_near_chance_on_noise():
    """Two halves of structureless data must not look like they agree."""
    import numpy as np
    from moral_atlas.analysis import latent

    rng = np.random.default_rng(3)
    values = np.where(rng.random((300, 60)) < 0.6,
                      rng.choice([-1.0, 1.0], size=(300, 60)), 0.0)
    result = latent.split_half_overlap(values, k=5, reps=6)
    assert result["overlap"] < 4 * result["chance"], (
        f"noise reproduced itself at {result['overlap']:.2f}")


def test_split_half_overlap_recovers_planted_structure():
    """And real structure must come back from both halves, or the measure is useless."""
    import numpy as np
    from moral_atlas.analysis import latent

    rng = np.random.default_rng(3)
    planted = _planted(400, 60, k=4, engagement=0.85, rng=rng, noise=0.35)
    result = latent.split_half_overlap(planted, k=4, reps=6)
    # The threshold is set where the measure DISCRIMINATES rather than at some
    # ideal: planted structure lands near 0.74 here and noise near 0.08. For
    # scale, the real deepseek corpus scores 0.21 at k=5 against a chance floor
    # of 0.02 — above chance, nowhere near reproducible.
    assert result["overlap"] > 0.6, (
        f"planted factors only reproduced at {result['overlap']:.2f}")


def test_each_group_is_signed_by_the_factor_it_actually_loads_on():
    """k-means labels are arbitrary integers, not factor indices.

    The code used to read `loadings[members, factor]` — cluster 3's loading on
    eigenvector 3 — as though a cluster's label named a factor. On the real
    corpus none of the twenty clusters had a label matching the eigenvector its
    members load on, and the column being read held a median 20% of the group's
    signal. That sign decides which propositions are reverse-keyed, and the
    matching eigenvalue decides which axes the product calls strongest.
    """
    import numpy as np
    from moral_atlas.analysis import latent

    rng = np.random.default_rng(11)
    # Three well-separated factors; which label k-means gives each is arbitrary.
    planted = _planted(300, 45, k=3, engagement=0.9, rng=rng, noise=0.25)
    items = [f"I{n:03d}" for n in range(45)]
    groups, _distance, loading, dominant, _all = latent.item_groups(planted, items, 3)

    assert set(dominant) == {0, 1, 2}, "every non-empty group needs a factor"
    corr = latent._pairwise_correlation(latent._film_centred(planted))
    values, vectors = np.linalg.eigh(corr)
    order = np.argsort(values)[::-1][:3]
    loadings = vectors[:, order] * np.sqrt(np.clip(values[order], 0, None))

    # One group, one factor. Two groups taking the same argmax forces whatever
    # reads them as axes to treat one as a facet of the other and drop it, which
    # cost a real axis the first time it happened.
    assert len(set(dominant.values())) == len(dominant), (
        f"two groups were assigned the same factor: {dominant}")

    # Claims are settled strongest-first, so the group with the most to lose
    # gets its actual preference; the others take the best factor still free.
    strengths = {}
    for label in dominant:
        members = [i for i, item in enumerate(items) if groups[item] == label]
        strengths[label] = np.abs(loadings[members].mean(axis=0))
    first = max(dominant, key=lambda g: strengths[g].max())
    assert dominant[first] == int(np.argmax(strengths[first])), (
        "the strongest claim should get the factor it actually loads on")

    for label, factor in dominant.items():
        members = [i for i, item in enumerate(items) if groups[item] == label]
        # whichever factor it was given, the signed value is that column
        assert np.allclose(sorted(abs(loading[items[i]]) for i in members),
                           sorted(abs(loadings[members, factor])))


def test_two_groups_never_claim_the_same_factor():
    """The product must not show two facets of one factor as two axes.

    Eight of the twenty groups once loaded on the first factor alone. Listing
    several side by side implies several independent readings of a person when
    they are one reading rephrased, and nothing on the screen lets a reader
    tell. `factor_axes` used to strip the duplicates afterwards, by shared
    eigenvalue — a repair applied downstream of the thing that was broken.

    The assignment itself is now one-to-one, so there is nothing to strip. This
    pins that, because the moment it stops being true the product silently
    starts showing facets again with no filter left to catch them.
    """
    import numpy as np

    from moral_atlas.analysis.latent import item_groups

    # Three real factors, deliberately unequal in size so the claims are
    # contested rather than settled by symmetry.
    rng = np.random.default_rng(17)
    films = 90
    drivers = [rng.normal(size=films) for _ in range(3)]
    columns, owners = [], []
    for factor, driver in enumerate(drivers):
        for i in range(6 - factor):                # 6, 5, 4 propositions
            sign = 1 if i % 2 == 0 else -1         # both poles of each
            columns.append(np.sign(driver * sign + rng.normal(0, .35, films)))
            owners.append(factor)
    matrix = np.column_stack(columns)
    items = [f"I{i}" for i in range(len(columns))]

    _groups, _distance, _signed, dominant, _all = item_groups(matrix, items, 3)

    assert len(set(dominant.values())) == len(dominant), (
        f"two groups claimed one factor: {dominant}")


def test_a_proposition_every_film_agrees_with_is_not_a_dimension():
    """And it is worse than useless, which is why it must be removed by hand.

    Film-centring subtracts each film's own affirm rate, so a unanimously
    affirmed item's centred value becomes `constant - film_mean` — a negated
    copy of how agreeable the film is. On the real corpus those items correlate
    -1.00 with the film's affirm rate and carried a mean absolute loading of
    1.00 against 0.34 for everything else: the correction for acquiescence was
    building an acquiescence factor out of them.
    """
    import numpy as np

    from moral_atlas.analysis import latent

    rng = np.random.default_rng(5)
    contested = np.where(rng.random((80, 6)) < 0.5, 1.0, -1.0)
    unanimous = np.ones((80, 4))                      # every film affirms
    matrix = np.hstack([contested, unanimous])
    items = [f"I{n:03d}" for n in range(matrix.shape[1])]

    # Rebuilt through the same rule response_matrix applies.
    def kept(min_disagreement):
        out = []
        for j, item in enumerate(items):
            v = matrix[:, j][matrix[:, j] != 0]
            share = (v > 0).mean()
            if min(share, 1 - share) >= min_disagreement:
                out.append(item)
        return out

    assert len(kept(latent.MIN_DISAGREEMENT)) == 6, "the four unanimous items must go"
    assert len(kept(0.0)) == 10, "and the rule must be what removes them, not chance"
    assert 0 < latent.MIN_DISAGREEMENT < 0.5, "a share of the minority side, not a count"


def test_every_screen_orders_the_axes_the_same_way():
    """Three screens show these groups; they used to sort differently.

    The atlas, a person's compass and a film's own reading each listed the axes
    in their own order, so which axis a reader met first depended on where they
    met it and nothing explained why. They now share one key, and the product's
    shortlist must be a SUBSEQUENCE of the atlas order — same sequence, fewer
    entries — rather than merely overlapping with it.
    """
    from moral_atlas.analysis import factor_names

    # Margin leads, and it is not a restatement of eigenvalue: on the live
    # reading the axis clearing chance by 262% accounts for LESS variation than
    # one clearing it by 24%. Size and certainty are different questions and the
    # order promises certainty.
    by_margin = [
        {"factor_id": 1, "name": "big but unsure", "margin": 0.20, "eigenvalue": 15.7, "n_items": 28},
        {"factor_id": 2, "name": "small but certain", "margin": 2.62, "eigenvalue": 4.5, "n_items": 22},
    ]
    assert [f["factor_id"] for f in sorted(by_margin, key=factor_names.by_support)] == [2, 1]

    factors = [
        {"factor_id": 1, "name": "b axis", "margin": 0.5, "eigenvalue": 11.6, "n_items": 8},
        {"factor_id": 2, "name": "a axis", "margin": 0.5, "eigenvalue": 11.6, "n_items": 20},
        {"factor_id": 3, "name": "c axis", "margin": 0.5, "eigenvalue": 6.0, "n_items": 14},
        {"factor_id": 4, "name": "d axis", "margin": 0.5, "eigenvalue": 6.0, "n_items": 7},
        {"factor_id": 5, "name": "e axis", "margin": None, "eigenvalue": None, "n_items": 3},
    ]
    ordered = sorted(factors, key=factor_names.by_support)
    assert [f["factor_id"] for f in ordered] == [2, 1, 3, 4, 5], (
        "then eigenvalue, then propositions behind it, then the name")

    # A missing eigenvalue must sort last rather than first, which is what a
    # bare `-(None or 0)` would do if the fallback were ever removed.
    assert ordered[-1]["factor_id"] == 5

    # The key must be TOTAL, or the order depends on which query fed it. Two
    # axes identical on every visible field still have to come out the same way
    # whichever order they arrived in.
    same = [{"factor_id": 9, "name": "x", "margin": 1.0, "eigenvalue": 1.0, "n_items": 2},
            {"factor_id": 8, "name": "x", "margin": 1.0, "eigenvalue": 1.0, "n_items": 2}]
    forwards = [f["factor_id"] for f in sorted(same, key=factor_names.by_support)]
    backwards = [f["factor_id"] for f in sorted(reversed(same), key=factor_names.by_support)]
    assert forwards == backwards == [8, 9]


def test_the_product_shortlist_is_a_subsequence_of_the_atlas_order():
    """Taking one axis per factor must not resequence what is left."""
    from moral_atlas.analysis import factor_names

    factors = [
        {"factor_id": 1, "name": "a", "eigenvalue": 11.6, "n_items": 20},
        {"factor_id": 2, "name": "b", "eigenvalue": 11.6, "n_items": 8},
        {"factor_id": 3, "name": "c", "eigenvalue": 6.7, "n_items": 11},
        {"factor_id": 4, "name": "d", "eigenvalue": 6.0, "n_items": 14},
    ]
    atlas = [f["factor_id"] for f in sorted(factors, key=factor_names.by_support)]

    seen, product = set(), []
    for f in sorted(factors, key=factor_names.by_support):
        if f["eigenvalue"] in seen:
            continue
        seen.add(f["eigenvalue"])
        product.append(f["factor_id"])

    positions = [atlas.index(fid) for fid in product]
    assert positions == sorted(positions), (
        f"product order {product} is not a subsequence of atlas order {atlas}")


def test_comparing_two_readers_counts_only_what_both_answered():
    """Agreement over items only one reader engaged would be meaningless.

    And it is direction that is compared, not strength: whether a film holds a
    position firmly or in passing is a judgement the graded scale invites and
    two readers calibrate differently, while affirm-versus-deny is the claim the
    instrument actually makes.
    """
    import contextlib

    from moral_atlas import db as db_mod
    from moral_atlas.analysis import film_compare

    bank = [{"item_id": "I1", "text": "one"}, {"item_id": "I2", "text": "two"},
            {"item_id": "I3", "text": "three"}]
    verdicts = {
        "a": [{"item_id": "I1", "value": 2, "confidence": 0.9, "evidence": "x"},
              {"item_id": "I2", "value": -1, "confidence": 0.9, "evidence": "y"}],
        "b": [{"item_id": "I1", "value": 1, "confidence": 0.9, "evidence": "z"},
              {"item_id": "I2", "value": 1, "confidence": 0.9, "evidence": "w"},
              {"item_id": "I3", "value": 1, "confidence": 0.9, "evidence": "v"}],
    }

    class Cursor:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows
        def fetchone(self): return self.rows[0] if self.rows else None
        def __iter__(self): return iter(self.rows)

    class Con:
        def execute(self, sql, args=None):
            if "item_bank" in sql: return Cursor(bank)
            if "FROM films" in sql: return Cursor([{"title": "F", "year": 2000}])
            return Cursor(verdicts[args[0]])

    original = db_mod.connect
    db_mod.connect = lambda *a, **k: contextlib.nullcontext(Con())
    try:
        out = film_compare.compare("f1", ["a", "b"], "bank")
    finally:
        db_mod.connect = original

    assert out["engaged"] == {"a": 2, "b": 3}
    assert out["shared"] == 2, "I3 was answered by one reader only"
    assert out["only"] == {"a": 0, "b": 1}
    # I1: +2 vs +1 is the SAME side despite differing strength.
    assert out["agreed"] == 1
    assert [r["item_id"] for r in out["split"]] == ["I2"]


def test_a_proposition_counts_on_every_axis_it_speaks_to():
    """Filing it under one and scoring from that group alone throws the rest away.

    On the live reading 22% of all loading mass sat outside the factor an item
    was assigned to, and 29% of propositions carried a second loading at least
    60% as strong as their first. Splitting the propositions in half and asking
    whether the halves place films in the same order, weighting by every loading
    is better or equal on all three axes.
    """
    import contextlib
    import json

    from moral_atlas import db as db_mod
    from moral_atlas.analysis import user_scores

    # A speaks almost entirely to axis 0. B is filed under axis 1 but still
    # says a little about axis 0. A film affirms A and denies B.
    items = [
        {"item_id": "A", "factor_id": 0, "loading": 0.9, "loadings": json.dumps([0.9, 0.1])},
        {"item_id": "B", "factor_id": 1, "loading": 0.6, "loadings": json.dumps([0.1, 0.6])},
    ]
    verdicts = [{"film_id": "f", "item_id": "A", "value": 2},
                {"film_id": "f", "item_id": "B", "value": -2}]

    class Cursor:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows
        def __iter__(self): return iter(self.rows)

    class Con:
        def execute(self, sql, args=None):
            return Cursor(items if "latent_factor_items" in sql else verdicts)

    original = db_mod.connect
    db_mod.connect = lambda *a, **k: contextlib.nullcontext(Con())
    try:
        stances = user_scores.factor_stances("s", "v", "b")
    finally:
        db_mod.connect = original

    # B is filed under axis 1, but it loads 0.1 on axis 0 — so it must appear
    # there too, not only on its own axis.
    assert set(stances["f"]) == {0, 1}
    assert len(stances["f"][0]) == 2, "both propositions speak to axis 0"
    assert len(stances["f"][1]) == 2, "and both to axis 1"

    # Axis 0: A affirmed at loading 0.9 against B denied at 0.1, so the weighted
    # mean is (0.9 - 0.1) / 1.0 = +0.8. Unweighted it would have been 0.0 — the
    # two verdicts cancelling as though they spoke to the axis equally.
    assert sum(stances["f"][0]) / len(stances["f"][0]) == pytest.approx(0.8)

    # Axis 1: B denied at 0.6 against A affirmed at 0.1, so it goes the other
    # way — (0.1 - 0.6) / 0.7.
    assert sum(stances["f"][1]) / len(stances["f"][1]) == pytest.approx(-5 / 7)


def test_a_factor_orientation_reaches_every_place_that_reads_direction():
    """One orientation, applied everywhere, or the two disagree and films invert.

    Each factor is flipped so its majority loads positive. That flip was applied
    to the signed loading stored per item and NOT to the full per-factor vector
    written beside it, so on the real reading 65 of 87 propositions carried
    opposite signs depending on which column was read — and every film's
    position on two of the three axes came out backwards.

    Caught by a reader: The Passion of the Christ denies "revenge can be a valid
    motivation for action", which should point away from instrumentalism, and
    the page said it pointed toward it.
    """
    import numpy as np

    from moral_atlas.analysis import latent

    rng = np.random.default_rng(11)
    planted = _planted(300, 45, k=3, engagement=0.9, rng=rng, noise=0.25)
    items = [f"I{n:03d}" for n in range(45)]
    _groups, _distance, loading, dominant, every = latent.item_groups(planted, items, 3)

    assert every and set(every) == set(items)
    for item, factor in ((i, f) for i, f in _groups.items()):
        vector = every[item]
        assert len(vector) == 3, "one loading per factor, indexed by factor_id"
        assert (loading[item] >= 0) == (vector[factor] >= 0), (
            f"{item}: signed loading {loading[item]:+.3f} disagrees with "
            f"vector[{factor}] = {vector[factor]:+.3f}")


def test_the_namer_is_not_asked_which_end_is_high():
    """Which end is "high" is this code's convention, not something to delegate.

    Asked to place its labels on high and low itself, the model swapped them
    onto the wrong descriptions: an axis whose LOW end was labelled "Cynical
    realism" and captioned "humans are capable of selfless virtue, redemption".
    It failed only on the factor where one end was unobserved and it had to
    reason about a side it could not see — the other two were fine, which is
    what makes the failure easy to miss.

    And the name it wrote disagreed with its own labels in 24 of 25 factors: it
    consistently wrote "<high> vs <low>" where the prompt asked for the reverse.

    So it names the two LISTS, which it can see, and the code maps lists to
    poles and builds the name.
    """
    from moral_atlas.analysis.factor_names import SYSTEM, FactorName

    fields = set(FactorName.model_fields)
    assert {"first_label", "second_label", "first", "second"} <= fields
    for gone in ("pole_high_label", "pole_low_label", "pole_high", "pole_low", "name"):
        assert gone not in fields, (
            f"{gone} is decided from the statistics; asking for it invites the swap back")
    assert "not asked which end is high or low" in SYSTEM.lower()


def test_a_factor_name_always_agrees_with_its_own_poles():
    """Built from the labels rather than taken from the model."""
    from moral_atlas.analysis import factor_names

    class Named:
        first_label, second_label = "Cynical fatalism", "Hopeful agency"
        first, second = "one end", "the other"
        question, coherent = "?", True

    report = {"scorer": "s", "groups": {}, "eigenvalues": [], "margins": []}
    built = f"{Named.second_label.strip()} vs {Named.first_label.strip()}"
    assert built == "Hopeful agency vs Cynical fatalism"
    # the low pole is the SECOND list, so the name reads low-then-high, in the
    # same order as the line a reader is shown
    assert built.split(" vs ")[0] == Named.second_label
    assert factor_names.by_support({"margin": 1.0}) < factor_names.by_support({"margin": 0.5})


def test_every_screen_computes_a_film_s_position_the_same_way():
    """Three places compute it, and one of them used different arithmetic.

    The per-axis distribution averaged the RAW verdicts of the propositions
    filed under a factor: no flip for the ones that read backwards, no weight
    for how much each speaks to the axis, and only that factor's own
    propositions counted. So a film strongly affirming reverse-keyed
    propositions was pushed toward the pole it was arguing against.

    Wonder Woman read +0.59 toward "predestined order" from 11 propositions in
    the distribution, while its own page read -0.44 toward self-determination
    from 55 — with every proposition listed underneath saying
    self-determination. Reported by a reader.
    """
    import contextlib
    import json

    from moral_atlas import db as db_mod
    from moral_atlas.analysis import factor_detail

    # One proposition points with the axis, one against it. The film affirms
    # both, so the flip decides which way it lands.
    verdicts = [{"film_id": "f", "item_id": "A", "value": 2, "evidence": ""},
                {"film_id": "f", "item_id": "B", "value": 2, "evidence": ""},
                {"film_id": "f", "item_id": "C", "value": 2, "evidence": ""}]
    groups = {"A": 0, "B": 0, "C": 0}
    loadings = {"A": 0.5, "B": -0.9, "C": -0.9}
    vectors = {"A": [0.5], "B": [-0.9], "C": [-0.9]}

    class Cursor:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows
        def __iter__(self): return iter(self.rows)

    class Con:
        def execute(self, sql, args=None):
            if "FROM films" in sql or "from films" in sql:
                return Cursor([{"film_id": "f", "title": "F", "year": 2000}])
            return Cursor(verdicts)

    original = db_mod.connect
    db_mod.connect = lambda *a, **k: contextlib.nullcontext(Con())
    try:
        out = factor_detail.detail("s", "b", "v", groups,
                                   {"A": "a", "B": "b", "C": "c"},
                                   loadings=loadings, vectors=vectors)
    finally:
        db_mod.connect = original

    rows = {r["film_id"]: r for r in out[0]["distribution"]}
    assert "f" in rows, "the film should be positioned"
    # B is reverse-keyed and weighs more (0.9 vs 0.5), so affirming both should
    # land NEGATIVE. Averaging the raw verdicts would have given +1.0.
    assert rows["f"]["score"] < 0, (
        f"reverse-keyed propositions were not flipped: got {rows['f']['score']:+.2f}")
    assert rows["f"]["items"] == 3


def test_an_axis_is_weighted_by_the_evidence_behind_it_not_the_count():
    """How much a film's position on one axis is worth.

    `len(stance)` was the answer, and it stopped being one the moment every
    proposition began counting on every axis in proportion to its loading:
    every axis then draws on the same propositions, so the count is identical
    across a film's axes by construction. Measured on the corpus, the spread
    between a film's busiest and emptiest axis was exactly 0.00 for all 565
    films — a weight that weighted nothing, while still varying between films
    and so still looking like it worked.

    `Stance.mass` is the loading weight actually behind the position, divided
    by the axis's own mean loading so it stays denominated in propositions.
    """
    import contextlib
    import json

    from moral_atlas import db as db_mod
    from moral_atlas.analysis import user_scores

    # Both propositions speak to both axes, and both are answered — so the
    # COUNT is two on each. They speak to axis 0 far more strongly.
    items = [
        {"item_id": "A", "factor_id": 0, "loading": 0.9, "loadings": json.dumps([0.9, 0.1])},
        {"item_id": "B", "factor_id": 1, "loading": 0.9, "loadings": json.dumps([0.9, 0.1])},
    ]
    verdicts = [{"film_id": "f", "item_id": "A", "value": 2},
                {"film_id": "f", "item_id": "B", "value": 2}]

    class Cursor:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows
        def __iter__(self): return iter(self.rows)

    class Con:
        def execute(self, sql, args=None):
            return Cursor(items if "latent_factor_items" in sql else verdicts)

    original = db_mod.connect
    db_mod.connect = lambda *a, **k: contextlib.nullcontext(Con())
    try:
        stances = user_scores.factor_stances("s", "v", "b")
    finally:
        db_mod.connect = original

    axis0, axis1 = stances["f"][0], stances["f"][1]
    assert len(axis0) == len(axis1) == 2, (
        "the count cannot tell these apart — that is the whole problem")
    assert axis0.mass > axis1.mass, (
        "the axis the propositions actually load on must carry more weight")

    # And an unweighted stance — the legacy dimensions, and every hand-built
    # list in these tests — still reports its count, which is its true mass
    # when every proposition counts once.
    assert user_scores.evidence([1.0, -1.0, 1.0]) == 3.0


def test_naming_keeps_the_answer_the_namer_would_give_again():
    """The namer is sampled, and the spread is not small.

    Asked three times for the same group it returned "Intrinsic worth vs
    Instrumental lives", "Intrinsic human worth vs Instrumental sacrifice" and
    "Absolute morality vs Instrumentalist activism" — the third a different
    reading, not a rewording. Named once, the axis a reader judges the whole
    method by is whichever sample came back last.

    A WHOLE RUN is chosen, not a per-factor mode. The namer sees every group in
    one call precisely so it has to tell them apart; names assembled from
    different runs lose that, and two axes chosen independently can come back
    describing the same thing.
    """
    from moral_atlas.analysis.factor_names import _consensus

    # The keys `_shape` emits, not the ones on the model's schema. Building
    # the fixture from the schema's names is how the first version of this
    # test passed against a function that scored every pair zero.
    def run(*pairs):
        return [{"factor_id": i, "pole_high_label": a, "pole_low_label": b,
                 "name": f"{b} vs {a}"} for i, (a, b) in enumerate(pairs)]

    agreeing_a = run(("Divine order", "Self determination"), ("Revenge", "Forgiveness"))
    agreeing_b = run(("Divine order", "Self determination"), ("Revenge", "Mercy"))
    outlier = run(("Inherited power", "Personal freedom"), ("Fate", "Agency"))

    # Deliberately first in the list: a scorer that fails silently returns 0
    # for every pair and `max` then keeps whatever it was handed first.
    kept = _consensus([outlier, agreeing_a, agreeing_b])
    assert kept is agreeing_a or kept is agreeing_b, (
        "the odd one out must not be published just because it ran first")

    # The kept answer is internally whole: every factor comes from one run.
    assert [f["name"] for f in kept] in (
        [f["name"] for f in agreeing_a], [f["name"] for f in agreeing_b])

    # And it reads the shape production hands it. If `_shape` renames a label
    # column, this must break rather than silently pick the first run.
    import pytest
    with pytest.raises(KeyError, match="drifted apart"):
        _consensus([[{"factor_id": 0, "first_label": "x", "second_label": "y"}],
                    [{"factor_id": 0, "first_label": "x", "second_label": "z"}]])

    # One run, or one surviving run, is used as-is rather than discarded.
    assert _consensus([agreeing_a]) is agreeing_a
    assert _consensus([[], agreeing_a]) is agreeing_a
    assert _consensus([]) == []


def test_a_failed_naming_run_does_not_lose_the_ones_that_worked():
    """Three calls mean three chances to hit a provider error."""
    import pytest

    from moral_atlas.analysis import factor_names

    calls = {"n": 0}

    class Flaky:
        def parse(self, system, user, output_model, max_tokens=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("502 from the provider")
            return factor_names.FactorNames(factors=[factor_names.FactorName(
                factor_id=0, first_label="A", second_label="B", first="a",
                second="b", question="q?", coherent=True)])

    report = {"scorer": "stub", "groups": {"I1": 0, "I2": 0},
              "loading": {"I1": 0.8, "I2": -0.6},
              "distance": {"I1": 0.1, "I2": 0.2},
              "dominant": {0: 0}, "eigenvalues": [9.0], "margins": [1.0]}
    named = factor_names.name_factors(
        report, {"I1": "one", "I2": "two"}, client=Flaky(), alias="stub", runs=3)
    assert calls["n"] == 3, "a failure must not abort the remaining runs"
    assert [f["name"] for f in named] == ["B vs A"]

    # But if every run fails, that is an error and not an empty axis set.
    class Broken:
        def parse(self, **kw):
            raise RuntimeError("down")

    with pytest.raises(RuntimeError, match="every naming run failed"):
        factor_names.name_factors(report, {"I1": "one", "I2": "two"},
                                  client=Broken(), alias="stub", runs=2)


def test_an_axis_with_an_unnamed_end_is_not_offered_as_a_reading():
    """The prompt forbids placeholder labels. Models write them anyway.

    Asked to name factors where only one end was observed, the uncensored model
    returned "None" as a label for eleven of fifteen axes — in every one of
    three runs, so not a bad sample — and deepseek returned "Uncharacterized vs
    Uncharacterized" on a different bank. A reader is shown two words at the
    ends of a line; "None" there is worse than a guess, and it would have been
    published as a real axis because the model did not also flag it.

    An instruction a model can decline is not a constraint.
    """
    from moral_atlas.analysis.factor_names import (
        FactorName, FactorNames, _consensus, _is_placeholder, name_factors)

    assert _is_placeholder("None") and _is_placeholder("  n/a ")
    assert _is_placeholder("Uncharacterized") and _is_placeholder("")
    assert not _is_placeholder("Divine order")
    assert not _is_placeholder("Nonviolence"), "a real word that starts with one"

    # A run that named both ends beats a more typical run that did not. Two of
    # the three agree with each other, so typicality alone would keep "None".
    def run(label, coherent=True):
        return [{"factor_id": 0, "pole_high_label": label,
                 "pole_low_label": "Revenge as justice", "name": "x",
                 "coherent": coherent}]
    named_properly = run("Restraint under provocation")
    kept = _consensus([run("None"), run("None"), named_properly])
    assert kept is named_properly

    # And when every run leaves an end unnamed, the axis is marked as one that
    # would not cohere — which keeps it out of the product and leaves it on the
    # atlas with the warning, rather than publishing "None" at one end.
    class Stub:
        def parse(self, system, user, output_model, max_tokens=None):
            return FactorNames(factors=[FactorName(
                factor_id=0, first_label="None", second_label="Revenge as justice",
                first="a", second="b", question="q?", coherent=True)])

    report = {"scorer": "s", "groups": {"I1": 0, "I2": 0},
              "loading": {"I1": 0.8, "I2": -0.6},
              "distance": {"I1": 0.1, "I2": 0.2},
              "dominant": {0: 0}, "eigenvalues": [9.0], "margins": [1.0]}
    out = name_factors(report, {"I1": "one", "I2": "two"},
                       client=Stub(), alias="s", runs=2)
    assert out[0]["coherent"] is False, (
        "the model called it coherent; an unnamed end says otherwise")
