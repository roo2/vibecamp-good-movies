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


def test_the_planted_number_of_factors_is_recovered():
    matrix = planted(k=3)
    result = latent.parallel_analysis(matrix, n_iter=60, seed=1)
    assert result["n_factors"] == 3
    assert result["n_clear_factors"] == 3


def test_a_different_planted_number_is_also_recovered():
    """Guards against a method that happens to like one answer."""
    result = latent.parallel_analysis(planted(k=5, seed=9), n_iter=60, seed=1)
    assert result["n_factors"] == 5


def test_structureless_responses_yield_no_factors():
    """The result the method must be able to return, or it proves nothing."""
    rng = np.random.default_rng(3)
    noise = rng.choice([-1.0, 0.0, 1.0], size=(60, 75))
    result = latent.parallel_analysis(noise, n_iter=60, seed=1)
    assert result["n_factors"] <= 1, "random responses are not a moral dimension"


def test_items_are_grouped_with_the_ones_sharing_their_factor():
    matrix = planted(n_films=60, per_factor=20, k=3, noise=0.3)
    items = [f"I{i:03d}" for i in range(matrix.shape[1])]
    groups = latent.item_groups(matrix, items, 3)

    # Items 0-19 were built from factor 0, 20-39 from factor 1, 40-59 from 2.
    blocks = [ {groups[items[i]] for i in range(start, start + 20)}
               for start in (0, 20, 40) ]
    assert all(len(b) == 1 for b in blocks), "each planted block lands in one group"
    assert len({next(iter(b)) for b in blocks}) == 3, "and the blocks are kept apart"


def test_margins_expose_a_factor_that_only_just_clears():
    """A count alone would report a hair's-breadth factor as confidently as a
    dominant one; the margins are what stop `n_factors` being over-quoted."""
    result = latent.parallel_analysis(planted(k=3), n_iter=60, seed=1)
    assert len(result["margins"]) == result["n_factors"]
    assert all(m > 0 for m in result["margins"]), "a retained factor cleared the null"
    assert result["margins"][0] == max(result["margins"]), \
        "the leading factor clears by the most"

    # The floor must actually bite. Planted factors here clear the null by a
    # long way, so only an unreachable floor separates the two counts — but it
    # has to separate them, or `n_clear_factors` is decoration.
    strict = latent.parallel_analysis(planted(k=3), n_iter=60, seed=1, margin_floor=100.0)
    assert strict["n_factors"] == 3 and strict["n_clear_factors"] == 0


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
