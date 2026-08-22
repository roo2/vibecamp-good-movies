"""Tests for the cross-model structure statistics.

These numbers are the whole claim — "the models found the same axes" or "they
did not" rests entirely on them — so they are tested against partitions whose
answer is known before the code runs: identical, relabelled, shifted by one
item, and pure noise.

No network and no LLM anywhere.
"""
from __future__ import annotations

import random

import pytest

from moral_atlas.analysis import structure_stats as stats


def partition(groups: list[list[str]]) -> dict[str, int]:
    return {item: index for index, group in enumerate(groups) for item in group}


EIGHT = {f"I{i:03d}": i % 8 for i in range(200)}


# --------------------------------------------------------------------------
# Agreement
# --------------------------------------------------------------------------

def test_a_partition_agrees_perfectly_with_itself():
    result = stats.agreement(EIGHT, dict(EIGHT))
    assert result["ari"] == 1.0
    assert result["nmi"] == 1.0
    assert result["raw"] == 1.0


def test_renumbering_the_axes_changes_nothing():
    """The point of ARI: axis 3 in one model and axis 7 in another can be the
    same axis, and no label-based measure could tell."""
    shuffled = {item: (group + 5) % 8 for item, group in EIGHT.items()}
    result = stats.agreement(EIGHT, shuffled)
    assert result["ari"] == 1.0
    assert result["raw"] == 0.0, "raw agreement is fooled by exactly this"


def test_unrelated_partitions_score_about_zero_not_about_a_tenth():
    """Two random 8-group partitions share ~12% of items by construction.

    Reporting that as agreement would make every pair of models look related,
    which is the entire reason this is chance-corrected.
    """
    rng = random.Random(11)
    noise = {item: rng.randrange(8) for item in EIGHT}
    result = stats.agreement(EIGHT, noise)
    assert abs(result["ari"]) < 0.05
    assert result["raw"] > 0.08, "raw agreement really is that generous"
    assert abs(result["z"]) < 4


def test_a_real_but_imperfect_match_lands_between():
    moved = dict(EIGHT)
    for item in list(moved)[:40]:          # disturb a fifth of the items
        moved[item] = (moved[item] + 1) % 8
    result = stats.agreement(EIGHT, moved)
    assert 0.4 < result["ari"] < 0.95
    assert result["z"] > 5, "must be far from chance"


def test_agreement_only_uses_items_both_models_placed():
    partial = {item: group for item, group in list(EIGHT.items())[:50]}
    result = stats.agreement(EIGHT, partial)
    assert result["n_items"] == 50
    assert result["ari"] == 1.0


# --------------------------------------------------------------------------
# Matching axes to each other
# --------------------------------------------------------------------------

def test_axes_are_matched_by_their_items_not_their_names():
    a = partition([["p", "q", "r"], ["s", "t", "u"]])
    b = partition([["s", "t", "u"], ["p", "q", "r"]])   # same split, opposite order
    matched = stats.match_axes(a, b, {0: "Mercy", 1: "Order"}, {0: "Order", 1: "Mercy"})
    assert all(row["jaccard"] == 1.0 for row in matched)
    assert {(row["a_name"], row["b_name"]) for row in matched} == {
        ("Mercy", "Mercy"), ("Order", "Order")}


def test_one_axis_cannot_be_the_counterpart_of_two():
    """Without the Hungarian constraint a big vague group matches everything."""
    a = partition([["p", "q", "r", "s"]])                 # one group
    b = partition([["p", "q"], ["r", "s"]])               # split in two
    matched = stats.match_axes(a, b)
    assert len(matched) == 1, "each axis matched at most once"


def test_splitting_an_axis_in_two_is_scored_as_a_partial_match():
    """B splits A's second axis, so that pair matches well but not perfectly,
    and B's leftover fragment is reported by being matched to nothing at all."""
    a = partition([["p", "q", "r"], ["s", "t", "u"]])
    b = partition([["p", "q", "r"], ["s"], ["t", "u"]])
    matched = stats.match_axes(a, b)

    assert len(matched) == 2, "A has two axes, so at most two pairs; B's {s} is left over"
    assert matched[0]["jaccard"] == 1.0
    assert matched[1]["jaccard"] == pytest.approx(2 / 3, abs=1e-3)  # {s,t,u} vs {t,u}


# --------------------------------------------------------------------------
# Is eight the joint?
# --------------------------------------------------------------------------

def test_the_sweep_finds_the_k_where_models_actually_agree():
    """k=8 built to agree, the others built to be noise; the sweep must say so."""
    rng = random.Random(3)
    by_k = {}
    for k in (4, 6, 8, 10):
        if k == 8:
            parts = {"a": EIGHT, "b": dict(EIGHT)}
        else:
            parts = {"a": {i: rng.randrange(k) for i in EIGHT},
                     "b": {i: rng.randrange(k) for i in EIGHT}}
        by_k[k] = parts

    sweep = stats.k_sweep(by_k)
    peak = stats.best_k(sweep)
    assert peak["k"] == 8
    assert peak["flat"] is False
    assert peak["margin"] > 0.5


def test_a_flat_sweep_is_reported_as_flat():
    """If agreement does not vary with k, the number came from the prompt.

    This is the result the project should be most willing to publish, so it must
    not be reported as a peak just because argmax always returns something.
    """
    rng = random.Random(7)
    by_k = {k: {"a": {i: rng.randrange(k) for i in EIGHT},
                "b": {i: rng.randrange(k) for i in EIGHT}} for k in (4, 6, 8, 10)}
    peak = stats.best_k(stats.k_sweep(by_k))
    assert peak["flat"] is True


def test_the_sweep_reports_the_spread_not_just_the_mean():
    by_k = {8: {"a": EIGHT, "b": dict(EIGHT), "c": {i: (g + 1) % 8 for i, g in EIGHT.items()}}}
    [row] = stats.k_sweep(by_k)
    assert row["pairs"] == 3
    assert row["min_ari"] <= row["mean_ari"] <= row["max_ari"]


# --------------------------------------------------------------------------
# Per-item stability
# --------------------------------------------------------------------------

def test_an_item_every_model_keeps_in_the_same_company_is_stable():
    a = partition([["p", "q", "r"], ["s", "t", "u"]])
    b = partition([["p", "q", "r"], ["s", "t"], ["u"]])
    ranked = {row["item_id"]: row["stability"] for row in stats.item_stability({"a": a, "b": b})}
    assert ranked["p"] == 1.0, "same neighbours in both"
    assert ranked["u"] < 0.5, "moved away from its group in one of them"


def test_stability_needs_two_models():
    assert stats.item_stability({"only": EIGHT}) == []
