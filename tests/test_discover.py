"""Tests for enumerating a corpus out of Wikipedia's category tree.

The parsing is where this goes wrong quietly: a mis-split title produces a film
that ingests fine, scores fine, and is simply the wrong film. No network — the
category and length lookups are stubbed.
"""
from __future__ import annotations

import pytest

from moral_atlas.sources import discover


# --------------------------------------------------------------------------
# Titles
# --------------------------------------------------------------------------

@pytest.mark.parametrize("article,expected", [
    ("Gladiator (2000 film)", ("Gladiator", 2000)),
    ("Casablanca (film)", ("Casablanca", None)),
    ("Sense and Sensibility (1995 film)", ("Sense and Sensibility", 1995)),
    ("The Matrix", ("The Matrix", None)),
    ("Parasite (2019 film)", ("Parasite", 2019)),
])
def test_the_disambiguator_is_stripped_from_the_title_and_kept_as_the_year(article, expected):
    assert discover._clean_title(article) == expected


def test_a_title_that_merely_contains_brackets_is_not_mangled():
    """"(500) Days of Summer" has no disambiguator to strip."""
    title, year = discover._clean_title("(500) Days of Summer")
    assert title == "(500) Days of Summer"
    assert year is None


# --------------------------------------------------------------------------
# What gets kept
# --------------------------------------------------------------------------

def _stub(monkeypatch, members, lengths):
    monkeypatch.setattr(discover, "_category_members",
                        lambda year, limit: [{"title": t} for t in members])
    # Mirrors the real lookup, which only ever returns what it was asked for.
    monkeypatch.setattr(discover, "_lengths",
                        lambda titles: {t: lengths[t] for t in titles if t in lengths})


def test_the_best_documented_films_are_taken_first(monkeypatch):
    _stub(monkeypatch, ["Short One", "Long One", "Middle One"],
          {"Short One": 21_000, "Long One": 90_000, "Middle One": 50_000})
    found = discover.discover([1999], per_year=2)
    assert [f["title"] for f in found] == ["Long One", "Middle One"]


def test_stubs_are_left_behind(monkeypatch):
    """A short article has no Plot section, which is the whole spine condition."""
    _stub(monkeypatch, ["Stub", "Proper"], {"Stub": 900, "Proper": 60_000})
    assert [f["title"] for f in discover.discover([1999], per_year=5)] == ["Proper"]


@pytest.mark.parametrize("noise", [
    "List of films of 1999", "Star Wars (film series)",
    "Titanic (soundtrack)", "The Matrix (video game)",
])
def test_lists_franchises_and_spin_offs_are_not_films(monkeypatch, noise):
    _stub(monkeypatch, [noise, "Real Film"], {noise: 200_000, "Real Film": 60_000})
    assert [f["title"] for f in discover.discover([1999], per_year=5)] == ["Real Film"]


def test_a_year_that_fails_does_not_end_the_sweep(monkeypatch):
    """Fifty-five years behind one network call is fifty-five chances to lose the lot."""
    def explode(year, limit):
        if year == 1999:
            raise RuntimeError("category unavailable")
        return [{"title": "Good Film"}]

    monkeypatch.setattr(discover, "_category_members", explode)
    monkeypatch.setattr(discover, "_lengths", lambda titles: {"Good Film": 60_000})
    found = discover.discover([1999, 2000], per_year=1)
    assert [f["year"] for f in found] == [2000]


# --------------------------------------------------------------------------
# Joining the corpus
# --------------------------------------------------------------------------

def test_films_already_in_the_corpus_are_not_added_again():
    films = [{"title": "Parasite", "year": 2019, "wikipedia": "Parasite (2019 film)", "note": "d"}]
    assert discover.as_seed_entries(films, {"parasite-2019"}) == []


def test_the_article_override_is_carried_only_when_it_differs():
    films = [
        {"title": "Parasite", "year": 2019, "wikipedia": "Parasite (2019 film)", "note": "d"},
        {"title": "The Matrix", "year": 1999, "wikipedia": "The Matrix", "note": "d"},
    ]
    entries = {e["title"]: e for e in discover.as_seed_entries(films, set())}
    assert entries["Parasite"]["wikipedia"] == "Parasite (2019 film)"
    assert "wikipedia" not in entries["The Matrix"], "a plain title needs no override"


def test_duplicates_within_one_sweep_are_collapsed():
    """Films sit in several year categories, so the same title arrives twice."""
    films = [
        {"title": "Parasite", "year": 2019, "wikipedia": "Parasite (2019 film)", "note": "a"},
        {"title": "Parasite", "year": 2019, "wikipedia": "Parasite (2019 film)", "note": "b"},
    ]
    assert len(discover.as_seed_entries(films, set())) == 1
