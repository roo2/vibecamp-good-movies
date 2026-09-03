"""Tests for the taste pipeline, aimed at the ways it has actually broken.

Two of the three failures below were shipped to production before anyone noticed,
and neither raised anything. They are regression tests, not hypotheticals.
"""
from __future__ import annotations

import inspect

import numpy as np
import pytest

from moral_atlas.analysis import movielens, taste


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


def test_film_correlation_is_a_correlation_matrix():
    """The FA path factors this, so a mis-scaled version would poison everything.

    Built from a Gram matrix rather than a dense one — 162,000 users by 646 films
    will not fit — and that route is easy to get subtly wrong in a way no caller
    would notice: an uncentred version still looks like a plausible matrix and
    still factors.
    """
    from scipy import sparse

    rng = np.random.default_rng(0)
    dense = rng.standard_normal((400, 12))
    dense[:, 1] = dense[:, 0] * 0.9 + dense[:, 1] * 0.1
    matrix = sparse.csr_matrix(dense)

    r = taste.film_correlation(matrix)
    assert r.shape == (12, 12)
    assert np.allclose(np.diag(r), 1.0, atol=1e-8), "diagonal of a correlation is 1"
    assert np.allclose(r, r.T, atol=1e-10), "a correlation matrix is symmetric"
    assert np.abs(r).max() <= 1.0 + 1e-9
    # Against numpy's own answer on the dense equivalent, which is the definition.
    assert np.allclose(r, np.corrcoef(dense, rowvar=False), atol=1e-6)
    assert r[0, 1] > 0.9, "the deliberately correlated pair must show up"


def test_factors_are_ordered_by_strength():
    """Seeded names are keyed by position, so position has to mean something.

    Promax is free to reorder importance, so without the sort afterwards
    dimension 1 is not reliably the largest and every label in the seed file
    lands on a different structure than the one it was written for.
    """
    from scipy import sparse

    rng = np.random.default_rng(1)
    base = rng.standard_normal((500, 3))
    dense = np.hstack([
        base[:, [0]] * 3 + rng.standard_normal((500, 4)) * 0.2,
        base[:, [1]] * 2 + rng.standard_normal((500, 4)) * 0.2,
        base[:, [2]] * 1 + rng.standard_normal((500, 4)) * 0.2,
    ])
    loadings, strength = taste._factors(sparse.csr_matrix(dense), 3)
    assert loadings.shape == (12, 3)
    assert list(strength) == sorted(strength, reverse=True), "strongest factor first"


def test_every_seeded_dimension_has_a_status_the_pipeline_understands():
    """`franchise` and `unnamed` are load-bearing, not decoration.

    Half the dimensions that replicate are franchise capture and are stored but
    never presented as findings about taste. A typo in the status would quietly
    promote one of them into the interface as though it were a kind of film.
    """
    entries = taste.curated()
    for dim_id, entry in entries.items():
        assert entry["status"] in {"named", "franchise", "unnamed"}, \
            f"dim {dim_id} has status {entry['status']!r}"
        if entry["status"] == "unnamed":
            assert not entry["pole_high"] and not entry["pole_low"], \
                f"dim {dim_id} is unnamed but carries pole labels"


def test_profile_reliability_needs_disjoint_halves():
    """The two halves must not share a film, or every dimension looks reliable.

    Split-half on overlapping samples measures the overlap. A rater with 12
    ratings asked for two halves of 10 would share 8 of them and correlate with
    itself — which is why the eligibility bar is twice the sample, not the sample.
    """
    assert taste.PROFILE_RATINGS >= 1
    src = inspect.getsource(taste.profile_reliability)
    assert "take * 2" in src, "eligibility must require two disjoint halves"


def test_profile_reliability_returns_one_figure_per_kept_dimension():
    """Stored by column, so a length mismatch would silently shift every label.

    `keep` is not contiguous — it skips the dimensions that failed replication —
    and the caller indexes into this by position in `keep`. A short array would
    put dimension 15's reliability on dimension 17 without raising.
    """
    rng = np.random.default_rng(2)
    n_films, n_users = 40, 900
    loadings = rng.standard_normal((n_films, 6))
    axes = taste.Axes(loadings=loadings, keep=[0, 2, 5],
                      variance=np.full(6, 0.1), replication=np.full(6, 0.9),
                      movie_ids=np.arange(1, n_films + 1))

    # Each rater gets their OWN affinity for dimension 1. Without that every
    # synthetic person has identical taste, there is nothing to tell apart, and
    # a working measure correctly reports zero.
    users, movies, stars = [], [], []
    for u in range(n_users):
        affinity = rng.normal()
        picks = rng.choice(n_films, size=30, replace=False)
        for f in picks:
            users.append(u)
            movies.append(f + 1)
            stars.append(3.0 + affinity * loadings[f, 0] + rng.normal(0, 0.3))
    ratings = movielens.Ratings(
        users=np.array(users), movies=np.array(movies), stars=np.array(stars),
        movie_ids=np.arange(1, n_films + 1),
        film_ids=np.array([f"film-{i}" for i in range(1, n_films + 1)]))

    out = taste.profile_reliability(axes, ratings, take=10)
    assert out.shape == (3,), "one figure per kept dimension, in keep order"
    assert np.all((out[np.isfinite(out)] >= 0) & (out[np.isfinite(out)] <= 1.001))
    # Dimension 1 is what the ratings were generated from; 3 and 6 are noise.
    assert out[0] > out[1] and out[0] > out[2], "the real dimension must win"
