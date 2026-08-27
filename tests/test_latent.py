"""Tests for recovering the number of dimensions from film responses.

The whole value of this module is that the count is discovered rather than
supplied, so the tests plant a known number of factors and check it comes back —
and, just as importantly, check that structureless data yields nothing. A method
that always returns a number would be indistinguishable from asking an LLM for
eight, which is the practice it exists to replace.

No network, no LLM, no database.
"""
from __future__ import annotations

import numpy as np
import pytest

from moral_atlas.analysis import latent


def planted(n_films=60, per_factor=25, k=3, noise=0.35, seed=4):
    """A response matrix with k groups of items driven by k latent variables."""
    rng = np.random.default_rng(seed)
    factors = rng.normal(size=(n_films, k))
    columns = []
    for f in range(k):
        for _ in range(per_factor):
            signal = factors[:, f] + rng.normal(scale=noise, size=n_films)
            columns.append(np.sign(signal))
    return np.array(columns).T


def like_the_corpus(n_films=200, per_factor=25, k=3, noise=0.35,
                    acquiescence=0.75, seed=4, talkative=True):
    """Planted factors, plus the two pathologies the real corpus has.

    Films differ wildly in how much of the bank they engage at all, and the
    scorer says "affirms" far more often than "denies" — 75% to 93% depending on
    the model. Neither is a moral dimension, and both are larger than any moral
    dimension in the data.
    """
    rng = np.random.default_rng(seed)
    factors = rng.normal(size=(n_films, k))
    columns = []
    for f in range(k):
        for _ in range(per_factor):
            signal = factors[:, f] + rng.normal(scale=noise, size=n_films)
            columns.append(np.where(signal > 0, 1.0,
                                    np.where(rng.random(n_films) < acquiescence, 1.0, -1.0)))
    matrix = np.array(columns).T
    if not talkative:
        return matrix                      # complete, for isolating one effect
    share = rng.uniform(0.15, 0.95, size=n_films)
    matrix[~(rng.random(matrix.shape) < share[:, None])] = 0.0
    return matrix


def test_the_planted_number_of_factors_is_recovered():
    """On data shaped like the corpus: sparse, and agreed with far too often."""
    result = latent.parallel_analysis(like_the_corpus(k=3, seed=4), n_iter=60, seed=1)
    assert result["n_factors"] == 3
    assert result["n_clear_factors"] == 3


def test_a_different_planted_number_is_also_recovered():
    """Guards against a method that happens to like one answer."""
    result = latent.parallel_analysis(like_the_corpus(k=5, seed=9), n_iter=60, seed=1)
    assert result["n_factors"] in (5, 6), f"5 planted, {result['n_factors']} found"


def test_complete_data_costs_the_estimator_one_factor():
    """A known cost, recorded rather than discovered later.

    Judging each film against its own rate of agreement spends a degree of
    freedom. Where there is no acquiescence to remove and nothing is missing,
    that degree of freedom was signal, and the count comes back one short. The
    corpus is neither complete nor unbiased, so this is the price of handling
    the case that exists — but it is a price.
    """
    result = latent.parallel_analysis(planted(k=3, n_films=200), n_iter=60, seed=1)
    assert result["n_factors"] == 2


def test_the_count_depends_on_how_engagement_is_distributed():
    """The estimator's weakest point, pinned so nobody has to rediscover it.

    Films differ in how much of the bank they engage, and that structure is what
    film-centring removes. Take it away — spray the same number of silences
    uniformly at random instead — and pairs end up correlated over unrelated
    subsets of films, which manufactures eigenvalues. It is stable rather than
    noisy: more null sampling does not move it.

    So the count is trustworthy to the extent that missingness is a property of
    films rather than of cells. On this corpus it is: engagement is a film
    talking about more or fewer things.
    """
    rng = np.random.default_rng(4)
    by_film = like_the_corpus(k=3, seed=4)

    # The same planted signal and the same amount of silence, scattered over
    # cells at random instead of concentrated in quieter films.
    complete = like_the_corpus(k=3, seed=4, talkative=False)
    uniform = complete.copy()
    uniform[rng.random(uniform.shape) > (by_film != 0).mean()] = 0.0

    structured = latent.parallel_analysis(by_film, n_iter=60, seed=1)["n_factors"]
    scattered = latent.parallel_analysis(uniform, n_iter=60, seed=1)["n_factors"]

    assert structured == 3
    assert scattered > structured, (
        f"three planted, {scattered} found once missingness stopped being a "
        "property of films — if this stops holding the limit has been fixed and "
        "the module docstring should say so")


def test_structureless_responses_yield_no_factors():
    """The result the method must be able to return, or it proves nothing."""
    rng = np.random.default_rng(3)
    noise = rng.choice([-1.0, 0.0, 1.0], size=(60, 75))
    result = latent.parallel_analysis(noise, n_iter=60, seed=1)
    assert result["n_factors"] <= 1, "random responses are not a moral dimension"


def test_items_are_grouped_with_the_ones_sharing_their_factor():
    """Including the items that point the OTHER WAY on the same factor.

    An axis has two ends: a proposition at one loads +0.8 where its opposite
    loads -0.8. Grouping on the signed loadings puts those as far apart as two
    points can be, so it files the two ends of one axis as two different axes —
    which is what it did on the real corpus, where two of three groups were both
    drawn from factor 1 with every proposition in each pointing one way.

    The planted data used to give every item the same sign, so it never
    exercised the case and never caught it. Half of each block is reverse-keyed
    here, as a real factor is.
    """
    # Built bipolar from the start. Flipping columns after the fact does not
    # work: film-centring subtracts each film's mean across items, so reversing
    # half of them redistributes the signal and leaves no clean factor to find.
    rng = np.random.default_rng(4)
    factors = rng.normal(size=(60, 3))
    columns = []
    for f in range(3):
        for j in range(20):
            pole = 1.0 if j % 2 == 0 else -1.0        # half at each end
            columns.append(np.sign(pole * factors[:, f]
                                   + rng.normal(scale=0.3, size=60)))
    matrix = np.array(columns).T
    items = [f"I{i:03d}" for i in range(matrix.shape[1])]
    groups, distance, loading, _dominant, _all = latent.item_groups(matrix, items, 3)

    # Both ends of each planted factor must land together.
    for start in (0, 20, 40):
        block = [groups[items[i]] for i in range(start, start + 20)]
        assert len(set(block)) == 1, (
            f"planted factor {start // 20} was split across groups {sorted(set(block))} "
            "— its two poles were filed as different axes")
    # And the sign must still separate the poles INSIDE the group.
    for start in (0, 20, 40):
        signs = [loading[items[i]] >= 0 for i in range(start, start + 20)]
        assert 0 < sum(signs) < 20, "a real factor has propositions at both ends"

    # Items 0-19 were built from factor 0, 20-39 from factor 1, 40-59 from 2.
    blocks = [ {groups[items[i]] for i in range(start, start + 20)}
               for start in (0, 20, 40) ]
    assert all(len(b) == 1 for b in blocks), "each planted block lands in one group"
    assert len({next(iter(b)) for b in blocks}) == 3, "and the blocks are kept apart"
    assert set(distance) == set(items), "every item knows how far it sits from its centre"
    assert set(loading) == set(items), "and which way it points on its own factor"


def test_margins_expose_a_factor_that_only_just_clears():
    """A count alone would report a hair's-breadth factor as confidently as a
    dominant one; the margins are what stop `n_factors` being over-quoted."""
    result = latent.parallel_analysis(like_the_corpus(k=3, seed=4), n_iter=60, seed=1)
    assert len(result["margins"]) == result["n_factors"]
    assert all(m > 0 for m in result["margins"]), "a retained factor cleared the null"
    # NOT asserted: that the first factor clears by the most. Under this
    # estimator the null's own eigenvalues fall away steeply, so a second factor
    # can clear a much lower bar by a wider relative margin than the first
    # clears a high one. Margin ranks how surely a factor is real, not how large
    # it is; the eigenvalues are what say that.

    # The floor must actually bite. Planted factors here clear the null by a
    # long way, so only an unreachable floor separates the two counts — but it
    # has to separate them, or `n_clear_factors` is decoration.
    floored = latent.parallel_analysis(like_the_corpus(k=3, seed=4), n_iter=60, seed=1,
                                       margin_floor=100.0)
    assert floored["n_factors"] == 3 and floored["n_clear_factors"] == 0


def test_the_null_preserves_each_items_own_engagement_rate():
    """Shuffling the whole matrix would let 'some items are scored more often'
    masquerade as a dimension, so the null must permute within columns."""
    rng = np.random.default_rng(0)
    # Items with wildly different engagement rates but no relationship at all.
    matrix = np.zeros((80, 60))
    for column in range(60):
        rate = 0.05 + 0.9 * (column / 60)
        matrix[:, column] = rng.choice([0.0, 1.0], size=80, p=[1 - rate, rate])
    result = latent.parallel_analysis(matrix, n_iter=60, seed=2)
    assert result["n_factors"] <= 1, "unequal salience alone is not structure"


def test_convergence_reports_disagreement_rather_than_averaging_it():
    reports = [
        {"scorer": "a", "n_factors": 8, "groups": {f"I{i}": i % 8 for i in range(80)}},
        {"scorer": "b", "n_factors": 8, "groups": {f"I{i}": i % 8 for i in range(80)}},
        {"scorer": "c", "n_factors": 5, "groups": {f"I{i}": i % 5 for i in range(80)}},
    ]
    out = latent.convergence(reports)
    assert out["counts"] == {"a": 8, "b": 8, "c": 5}
    assert out["same_count"] is False
    assert out["spread"] == 3
    assert out["grouping_agreement"]["a vs b"]["ari"] == 1.0
    assert out["grouping_agreement"]["a vs c"]["ari"] < 0.5


def test_agreeing_on_the_count_is_not_agreeing_on_the_grouping():
    """Two models can both say eight and carve the material completely
    differently, which would be a coincidence of arithmetic, not a structure."""
    rng = np.random.default_rng(7)
    reports = [
        {"scorer": "a", "n_factors": 8, "groups": {f"I{i}": i % 8 for i in range(160)}},
        {"scorer": "b", "n_factors": 8,
         "groups": {f"I{i}": int(rng.integers(0, 8)) for i in range(160)}},
    ]
    out = latent.convergence(reports)
    assert out["same_count"] is True
    assert abs(out["grouping_agreement"]["a vs b"]["ari"]) < 0.1


def test_the_namer_is_shown_each_factor_strongest_first():
    """What the namer reads decides what the axis is called.

    Ordered by item_id — bank insertion order — a namer saw an arbitrary corner
    of a cluster and named that. Ordered by DISTANCE from the cluster centroid
    it saw something better but still wrong: distance measures position across
    every factor, not how much a proposition defines THIS one. On the real
    corpus that put "the state has the right to take a person's life"
    (loading 0.56, the axis's strongest) seventh, behind "there is a right order
    that precedes individual choice" at 0.17 — which is how an axis gets named
    for something it is not chiefly measuring.

    Strongest loading first, with the weight shown.
    """
    from moral_atlas.analysis.factor_names import _items_by_factor

    groups = {"I900": 0, "I001": 0, "I500": 0}
    texts = {"I900": "weak but near the centre", "I001": "the strongest",
             "I500": "middling"}
    distance = {"I900": 0.1, "I001": 0.9, "I500": 0.5}
    loading = {"I900": 0.17, "I001": 0.56, "I500": 0.30}

    high, low = _items_by_factor(groups, texts, distance, loading, loading)[0]
    assert [text for _w, text in high] == ["the strongest", "middling",
                                           "weak but near the centre"], (
        "the proposition that defines the axis most must be read first")
    assert [round(w, 2) for w, _t in high] == [0.56, 0.30, 0.17], (
        "and its weight is shown, not just implied by position")
    assert low == [], "nothing loads negative here"

    # And the two ends are separated, because an axis has two of them and which
    # one a proposition belongs to is the SIGN of its loading. Handed a flat
    # list, the namer was guessing the split and then naming its guess — on the
    # real corpus that meant 17 of 37 propositions asserting the opposite pole
    # with nothing marking them.
    loading = {"I900": 0.8, "I001": -0.4, "I500": 0.2}
    high, low = _items_by_factor(groups, texts, distance, loading, loading)[0]
    assert [text for _w, text in high] == ["weak but near the centre", "middling"]
    assert [text for _w, text in low] == ["the strongest"]

    # With nothing given it must still be deterministic rather than dict order.
    assert len(_items_by_factor(groups, texts)[0][0]) == 3


def test_item_groups_reports_how_far_each_item_sits_from_its_centre():
    """Membership says an item belongs somewhere; distance says how much."""
    import numpy as np
    from moral_atlas.analysis.latent import item_groups

    # Two obvious clumps: films answer the first two items alike, and the last
    # two alike, so the clustering has something real to find.
    matrix = np.array([
        [1.0, 1.0, -1.0, -1.0],
        [1.0, 1.0, -1.0, -1.0],
        [-1.0, -1.0, 1.0, 1.0],
        [-1.0, -1.0, 1.0, 1.0],
        [1.0, 1.0, 1.0, -1.0],
    ])
    groups, distance, loading, _dominant, _all = item_groups(matrix, ["a", "b", "c", "d"], 2)

    assert set(groups) == {"a", "b", "c", "d"}
    assert groups["a"] == groups["b"] and groups["c"] != groups["a"]
    assert all(value >= 0 for value in distance.values())
    assert set(distance) == set(groups)
    assert set(loading) == set(groups)


def test_the_atlas_hides_nothing_and_the_product_shows_a_handful():
    """Two different jobs, and only one of them is a presentation choice.

    A 25% margin bar used to sit on top of the null test and decide what reached
    the page. It was picked to keep a list short — a layout problem in the
    clothes of a statistical one — and it hid real findings from the page whose
    whole purpose is to show them. The null test at 5% is the only bar on the
    atlas now.

    The product shows few, and that limit stopped being about a screen. Split
    the films in half and ask whether both halves find the same variation: the
    first factor returns at 0.59 against a chance floor of 0.003, the second at
    0.35, and by the fifth it is 0.21 and falling into the floor. Clearing a
    permutation null and surviving a change of sample are different tests, and
    most of the twenty pass only the first.
    """
    from moral_atlas.analysis import factor_names, user_scores

    assert not hasattr(factor_names, "DISPLAY_MARGIN"), (
        "the editorial threshold is gone; nothing should filter the atlas")
    assert user_scores.PRODUCT_AXES <= 3, (
        "the product's axis count is a claim about what replicates, not a layout "
        "decision — raising it needs replication evidence behind it")
def test_the_strict_estimator_ignores_silence_entirely():
    """Two items only ever answered by different films cannot be correlated."""
    matrix = np.array([
        [1.0, 0.0],
        [-1.0, 0.0],
        [0.0, 1.0],
        [0.0, -1.0],
    ])
    correlation = latent._pairwise_correlation(matrix)

    assert correlation[0, 1] == 0.0, (
        "no film took a position on both, so there is nothing to correlate — "
        "the dense reading would call these related because the silences line up")
    assert correlation[0, 0] == 1.0


def test_the_strict_estimator_recovers_what_the_dense_one_cannot():
    """The dense reading finds talkativeness and acquiescence before the truth."""
    matrix = like_the_corpus(k=3, seed=4)

    found = latent.parallel_analysis(matrix, n_iter=80, seed=1)["n_factors"]

    assert found == 3, f"three factors were planted; found {found}"


def test_the_strict_estimator_still_reports_nothing_when_there_is_nothing():
    """The result it must be able to return, or finding factors proves nothing."""
    rng = np.random.default_rng(3)
    noise = rng.choice([-1.0, 0.0, 1.0], size=(120, 90))

    assert latent.parallel_analysis(noise, n_iter=80, seed=1)["n_factors"] == 0


def test_film_centring_removes_a_films_own_affirm_rate():
    """Acquiescence is a property of the judge as much as the judged."""
    matrix = np.array([
        [1.0, 1.0, 1.0, -1.0],   # affirms nearly everything
        [1.0, -1.0, 0.0, 0.0],   # engages two, split
    ])
    centred = latent._film_centred(matrix)

    assert np.isclose(centred[0][matrix[0] != 0].mean(), 0.0)
    assert np.isclose(centred[1][matrix[1] != 0].mean(), 0.0)
    assert (centred[matrix == 0] == 0).all(), "silence stays silent, not centred into a value"


def test_every_factor_is_oriented_by_its_majority():
    """A factor's direction has to be defined by something, or its sign is noise.

    Items in a factor do not all run the same way — on the real corpus 85 of 298
    load against their own group's majority, because "selfishness is necessary"
    and "altruism is superior" belong to one axis while pointing opposite ways.
    The majority sets the direction, which is the direction the naming step is
    shown, so a positive loading always means "affirming this is the high pole".
    """
    matrix = like_the_corpus(k=3, seed=4)
    items = [f"I{i:03d}" for i in range(matrix.shape[1])]
    groups, _distance, loading, _dominant, _all = latent.item_groups(matrix, items, 3)

    assert set(loading) == set(items), "every item carries a signed weight"
    for factor in sorted(set(groups.values())):
        members = [loading[i] for i in items if groups[i] == factor]
        positive = sum(1 for v in members if v > 0)
        assert positive >= len(members) / 2, (
            f"factor {factor} is oriented against its own majority")




def test_a_bipolar_group_claims_the_factor_it_is_actually_made_of():
    """Which factor a group is named, ranked and oriented by.

    Claim strength measured `abs(mean(signed_loading))` — how big the group's
    average loading is. A bipolar group's average loading is ~0 by
    construction: half its members load +0.6 and half -0.6 on exactly the
    factor that defines them. So the group that most owns a factor made the
    weakest claim to it, lost it, and took another by default.

    That is the same defect the one-to-one assignment was written to fix,
    surviving it — because clustering on magnitudes, which keeps an axis's two
    poles together, is what makes the groups bipolar in the first place. On the
    real corpus it left 26 of 90 propositions filed under a factor that was not
    their strongest, named the weakest factor as the strongest, and buried the
    single largest loading in the solution (0.83) under a factor where it
    loads 0.17.

    The measure is the average SIZE of the loadings, not the size of the
    average.
    """
    import numpy as np

    from moral_atlas.analysis.latent import item_groups

    # Two factors. Items 0-3 are the poles of factor 0 and load nothing on
    # factor 1; items 4-7 are one-sided on factor 1. Only the first group is
    # bipolar, and only it is at risk.
    rng = np.random.default_rng(3)
    films = 60
    matrix = np.zeros((films, 8))
    a = rng.normal(size=films)
    b = rng.normal(size=films)
    for i in range(4):
        matrix[:, i] = np.sign(a * (1 if i < 2 else -1) + rng.normal(0, .3, films))
    for i in range(4, 8):
        matrix[:, i] = np.sign(b + rng.normal(0, .3, films))
    items = [f"I{i}" for i in range(8)]

    groups, _distance, _signed, _dominant, all_loadings = item_groups(matrix, items, 2)

    for item, factor in groups.items():
        strongest = int(np.argmax(np.abs(all_loadings[item])))
        assert factor == strongest, (
            f"{item} is filed under factor {factor} but loads most on "
            f"{strongest}: {[round(v, 2) for v in all_loadings[item]]}")


def test_an_axis_carries_one_factors_eigenvalue_and_that_same_factors_margin():
    """The two numbers an axis is judged by must describe the same factor.

    A k-means label is arbitrary, so a group's numbers have to be looked up
    through the group->factor mapping. The eigenvalue was; the margin on the
    very next line was not. So an axis went out carrying one factor's size
    beside a different factor's certainty — and the product orders its axes by
    margin, which meant the corpus's third-largest factor was published as its
    most certain at +267% while showing an eigenvalue of 4.69.
    """
    from moral_atlas.analysis.factor_names import FactorName, FactorNames, name_factors

    class Stub:
        def parse(self, system, user, output_model, max_tokens=None):
            return FactorNames(factors=[
                FactorName(factor_id=i, first_label="A", second_label="B",
                           first="a", second="b", question="q?", coherent=True)
                for i in (0, 1)])

    report = {
        "scorer": "stub",
        "groups": {"I1": 0, "I2": 0, "I3": 1, "I4": 1},
        "loading": {"I1": 0.8, "I2": -0.7, "I3": 0.6, "I4": -0.5},
        "distance": {k: 0.1 for k in ("I1", "I2", "I3", "I4")},
        # Group 0 loads on factor 1, group 1 on factor 0 — the crossed mapping
        # that makes the bug visible.
        "dominant": {0: 1, 1: 0},
        "eigenvalues": [15.95, 4.69],
        "margins": [2.671, 0.243],
    }
    texts = {k: f"proposition {k}" for k in report["groups"]}

    named = {f["factor_id"]: f for f in
             name_factors(report, texts, client=Stub(), alias="stub")}

    assert named[0]["eigenvalue"] == 4.69 and named[0]["margin"] == 0.243, (
        "group 0 loads on factor 1 and must carry BOTH of factor 1's numbers")
    assert named[1]["eigenvalue"] == 15.95 and named[1]["margin"] == 2.671


def test_an_axis_lists_its_propositions_strongest_first(monkeypatch, tmp_path):
    """The evidence under an axis, in the order a reader meets it.

    Ordered by distance from the group centroid, which sounds like centrality
    and is not: distance measures an item's position across every factor at
    once, so an item can sit near the centre while barely loading on this axis.
    On the real reading it put the defining proposition of all three axes last
    — "There is a right order that precedes individual choice", loading 0.83
    and the largest in the solution, was 23rd of 23. The cap then cut the
    remainder by the same unrelated criterion.
    """
    from dataclasses import replace

    from moral_atlas import db
    from moral_atlas.analysis import factor_detail
    from moral_atlas.config import settings

    monkeypatch.setattr(db, "settings", lambda: replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "isolated.sqlite"))
    db.init_db()
    with db.connect() as con:
        con.executemany("INSERT INTO films (film_id, title) VALUES (?,?)",
                        [("f1", "One"), ("f2", "Two"), ("f3", "Three")])
        con.executemany(
            "INSERT INTO model_verdicts (scorer, model, film_id, item_id, "
            "bank_version, variant, value) VALUES (?,?,?,?,?,?,?)",
            [("x", "m", film, item, "b", "v", value)
             for film in ("f1", "f2", "f3")
             for item, value in (("I1", 1), ("I2", -1), ("I3", 1))])

    detail = factor_detail.detail(
        scorer="x", bank_version="b", variant="v",
        groups={"I1": 0, "I2": 0, "I3": 0},
        texts={"I1": "weak", "I2": "strongest", "I3": "middling"},
        # Deliberately opposed to the loadings, the way the real data was.
        distance={"I1": 0.1, "I2": 0.9, "I3": 0.5},
        loadings={"I1": 0.17, "I2": -0.83, "I3": 0.40},
        vectors={"I1": [0.17], "I2": [-0.83], "I3": [0.40]},
    )
    shown = [row["text"] for row in detail[0]["propositions"]]
    assert shown == ["strongest", "middling", "weak"], (
        "an axis must open with what defines it, whichever pole that is on")
