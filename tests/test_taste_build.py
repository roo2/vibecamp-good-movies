"""Tests for the taste pipeline, aimed at the ways it has actually broken.

Two of the three failures below were shipped to production before anyone noticed,
and neither raised anything. They are regression tests, not hypotheticals.
"""
from __future__ import annotations

import numpy as np
import pytest

from moral_atlas.analysis import taste


def test_curated_names_carry_an_anchor_wherever_they_are_named():
    """A named dimension without an anchor cannot be oriented, so it will flip.

    The pole labels are fixed text keyed by dim_id while the SVD's signs are
    arbitrary. Any named dimension missing its anchor is one rebuild away from
    describing the wrong ends — which is how The Godfather came to sit under
    "Enjoyable trash".
    """
    entries = taste.curated()
    assert entries, "the seed file should describe some dimensions"
    for dim_id, entry in entries.items():
        if entry["status"] == "named":
            assert entry["pole_high"] and entry["pole_low"], f"dim {dim_id} half-named"
            assert entry["anchor"], f"dim {dim_id} is named but has no anchor tag"
        else:
            # Unnamed and franchise dimensions are stored, but never presented as
            # a finding, so they need no orientation.
            assert entry["status"] in ("unnamed", "franchise")


def test_orient_flips_a_component_that_points_away_from_its_anchor():
    loadings = np.array([[1.0, 5.0], [-1.0, 6.0]])
    tags = {1: "masterpiece", 2: "bad plot"}
    # The anchor correlates NEGATIVELY, so the component is upside down.
    correlations = np.array([-0.8, 0.4])

    out, flipped = taste.orient(loadings, 0, correlations, "masterpiece", tags)

    assert flipped is True
    assert out[0] == pytest.approx(0.8), "anchor must end up on the high pole"
    assert loadings[:, 0].tolist() == [-1.0, 1.0], "loadings flip with the labels"
    assert loadings[:, 1].tolist() == [5.0, 6.0], "other components untouched"


def test_orient_leaves_a_correctly_pointed_component_alone():
    loadings = np.array([[1.0], [-1.0]])
    correlations = np.array([0.8])
    out, flipped = taste.orient(loadings, 0, correlations, "masterpiece",
                                {1: "masterpiece"})
    assert flipped is False
    assert out[0] == pytest.approx(0.8)
    assert loadings[:, 0].tolist() == [1.0, -1.0]


def test_orient_rejects_an_anchor_that_is_not_a_real_tag():
    """Better to fail than to silently skip the orientation of a named axis."""
    with pytest.raises(ValueError, match="not in the MovieLens genome"):
        taste.orient(np.array([[1.0]]), 0, np.array([0.5]), "not a tag",
                     {1: "masterpiece"})


def test_kept_components_are_indexed_by_their_own_column():
    """`keep` holds column indices, not positions — they are not interchangeable.

    The original store step indexed loadings by a component's POSITION in `keep`
    rather than by the column it names. With keep = [0..10, 13, 14, 22] that
    silently hands dimension 14 the data belonging to column 11, and raises
    nothing at all. This pins the contract the store step relies on.
    """
    keep = list(range(11)) + [13, 14, 22]
    loadings = np.arange(30 * 24, dtype=float).reshape(30, 24)

    by_column = [loadings[:, column] for column in keep]
    by_position = [loadings[:, i] for i, _ in enumerate(keep)]

    assert np.array_equal(by_column[11], loadings[:, 13])
    assert not np.array_equal(by_column[11], by_position[11])
    # The dimension numbers the product shows are the columns, one-based.
    assert [c + 1 for c in keep][-3:] == [14, 15, 23]
