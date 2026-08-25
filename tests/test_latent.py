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
    matrix = planted(n_films=60, per_factor=20, k=3, noise=0.3)
    items = [f"I{i:03d}" for i in range(matrix.shape[1])]
    groups, distance, loading = latent.item_groups(matrix, items, 3)

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


def test_the_namer_is_shown_each_factor_from_its_centre_outward():
    """What the namer reads decides what the axis is called.

    The sample used to be ordered by item_id — bank insertion order — so a namer
    saw an arbitrary corner of a cluster and named that. DeepSeek's largest
    factor opened with "Sacrificing oneself for another is the highest act of
    love" and came back called Self-preservation vs Heroic self-sacrifice, while
    the propositions nearest its centre were about deception as survival and
    childhood damage. Centre-first is the fix, and this pins it.
    """
    from moral_atlas.analysis.factor_names import _items_by_factor

    groups = {"I900": 0, "I001": 0, "I500": 0}
    texts = {"I900": "nearest the centre", "I001": "furthest out", "I500": "in between"}
    distance = {"I900": 0.1, "I001": 0.9, "I500": 0.5}

    assert _items_by_factor(groups, texts, distance)[0] == [
        "nearest the centre", "in between", "furthest out"]
    # With no distances it must still be deterministic rather than dict order.
    assert len(_items_by_factor(groups, texts)[0]) == 3


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
    groups, distance, loading = item_groups(matrix, ["a", "b", "c", "d"], 2)

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

    The product still shows a few, because somebody choosing a film is not
    auditing a corpus. That limit is honest about being about a screen.
    """
    from moral_atlas.analysis import factor_names, user_scores

    assert not hasattr(factor_names, "DISPLAY_MARGIN"), (
        "the editorial threshold is gone; nothing should filter the atlas")
    assert user_scores.PRODUCT_AXES == 6

    axes = [{"dim_id": i, "name": f"axis {i}", "question": "?", "pole_high": "h",
             "pole_low": "l"} for i in range(11)]
    assert len(axes[:user_scores.PRODUCT_AXES]) == 6
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
    groups, _distance, loading = latent.item_groups(matrix, items, 3)

    assert set(loading) == set(items), "every item carries a signed weight"
    for factor in sorted(set(groups.values())):
        members = [loading[i] for i in items if groups[i] == factor]
        positive = sum(1 for v in members if v > 0)
        assert positive >= len(members) / 2, (
            f"factor {factor} is oriented against its own majority")


