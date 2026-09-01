"""Co-preference ranking: the arithmetic, and that it actually ranks.

The existing suite passed the moment this was wired in, which proved nothing —
the test database has no `film_neighbours` table, so every one of those runs
took the fallback path and the new code was never executed.
"""
from dataclasses import replace

import pytest

from moral_atlas.analysis import neighbours


class Pref:
    """Enough of a preference for the collapsing rule to be tested."""

    def __init__(self, film_id, weight):
        self.film_id = film_id
        self.weight = weight


@pytest.fixture()
def isolated_database(monkeypatch, tmp_path):
    from moral_atlas import db
    from moral_atlas.config import settings

    test_settings = replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "atlas.sqlite",
    )
    monkeypatch.setattr(db, "settings", lambda: test_settings)
    db.init_db()
    return db


def test_a_film_resembling_a_rejected_one_scores_below_zero():
    """A rejection is evidence. If it only failed to help, the deck would keep
    offering near-copies of the thing somebody just turned down."""
    graph = {"liked-alike": [("seen", 0.8)], "hated-alike": [("rejected", 0.8)]}
    got = neighbours.score({"seen": 1.0, "rejected": -1.0}, graph)

    assert got["liked-alike"] > 0
    assert got["hated-alike"] < 0


def test_thin_evidence_cannot_outrank_thick_evidence():
    """One weak similarity divided by itself is 1.0 — a perfect score from
    almost nothing. PRIOR is what stops a film nobody has evidence about
    arriving at the top of the shortlist."""
    graph = {"thin": [("seen", 0.05)],
             "thick": [("seen", 0.9), ("other", 0.8)]}
    got = neighbours.score({"seen": 1.0, "other": 1.0}, graph)

    assert got["thick"] > got["thin"]


def test_a_film_with_no_shared_neighbours_scores_zero_rather_than_failing():
    got = neighbours.score({"seen": 1.0}, {"unrelated": [("never-rated", 0.9)]})
    assert got["unrelated"] == 0.0


def test_the_strongest_statement_about_a_film_wins():
    """A film can arrive twice — rated in the deck, then again in a pairwise
    question — and the two can disagree. Magnitude decides, so a firm rejection
    is not overwritten by an incidental later mention."""
    weights = neighbours.preference_weights(
        [Pref("f", 1.0), Pref("f", -2.0), Pref("f", 0.5)])
    assert weights["f"] == -2.0


def test_preferences_with_no_weight_are_not_evidence():
    weights = neighbours.preference_weights([Pref("f", 0.0), Pref("g", 1.0)])
    assert "f" not in weights and weights["g"] == 1.0


def test_loading_is_empty_rather_than_an_error_when_nothing_was_derived(isolated_database):
    """A database built before this existed, or one where the derivation has
    not been run, must still serve a shortlist. The caller reads an empty map
    and falls back to the moral ranking."""
    assert neighbours.load() == {}


def test_pairs_measured_on_too_few_people_are_refused(isolated_database):
    """A correlation over a handful of shared raters is noise with a decimal
    point on it, and it is stored with its support precisely so it can be
    excluded here."""
    db = isolated_database
    with db.connect() as con:
        con.executemany(
            "INSERT INTO film_neighbours (film_id, neighbour_id, similarity, support) "
            "VALUES (?,?,?,?)",
            [("a", "b", 0.9, 5), ("a", "c", 0.4, 5000)])

    graph = neighbours.load()
    assert [n for n, _ in graph["a"]] == ["c"], "the 5-rater pair should be refused"
