"""Which Wikipedia article a film is read from, and how a wrong one is caught.

Two films in the corpus turned out to carry another film's IMDb id — Carlos
(2010) carried Marmaduke's and Jeanne Dielman carried Gerry's — and nothing in
the pipeline noticed. The plot section, the dialogue track and every score built
on them belonged to a different film, and the only visible symptom was a blind
story card that did not sound like the film it was filed under.

So resolution is by identifier, and the identifier itself is checked against
what Wikidata says it points at.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from moral_atlas import db
from moral_atlas.config import settings
from moral_atlas.sources import wikipedia as wiki


@pytest.fixture
def store(monkeypatch, tmp_path):
    test_settings = replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "atlas.sqlite",
    )
    monkeypatch.setattr(db, "settings", lambda: test_settings)
    db.init_db()
    return test_settings


def _film(film_id, title, year, imdb_id, article=None):
    db.upsert_film({"film_id": film_id, "title": title, "year": year,
                    "imdb_id": imdb_id, "wikipedia_title": article})


def test_an_identifier_pointing_at_another_film_is_reported_not_followed(
    store, monkeypatch,
):
    _film("carlos-2010", "Carlos", 2010, "tt1392197")
    _film("the-godfather-1972", "The Godfather", 1972, "tt0068646")
    monkeypatch.setattr(wiki, "articles_by_imdb", lambda ids: {
        "tt1392197": {"article": "Marmaduke (2010 film)",
                      "labels": {"Marmaduke"}, "years": {2010}},
        "tt0068646": {"article": "The Godfather",
                      "labels": {"The Godfather"}, "years": {1972}},
    })

    said = []
    stats = wiki.resolve_articles(progress=said.append)

    assert stats["suspect"] == 1
    assert stats["stored"] == 1
    assert any("WRONG ID" in line and "Carlos" in line for line in said)
    assert db.get_film("the-godfather-1972")["wikipedia_title"] == "The Godfather"
    assert db.get_film("carlos-2010")["wikipedia_title"] is None, (
        "a film whose id belongs to another film must not be pointed at that "
        "film's article — the wrong plot is worse than no plot"
    )


def test_a_title_that_matches_an_alias_or_a_release_a_year_out_is_not_suspect(
    store, monkeypatch,
):
    _film("se7en-1995", "Se7en", 1995, "tt0114369")
    _film("metropolis-1927", "Metropolis", 1926, "tt0017136")
    monkeypatch.setattr(wiki, "articles_by_imdb", lambda ids: {
        # Wikidata labels it Seven and carries Se7en as an alias.
        "tt0114369": {"article": "Seven (1995 film)",
                      "labels": {"Seven", "Se7en"}, "years": {1995}},
        # Release dates differ by country; a year either side is the same film.
        "tt0017136": {"article": "Metropolis (1927 film)",
                      "labels": {"Metropolis"}, "years": {1927}},
    })

    stats = wiki.resolve_articles(progress=None)

    assert stats["suspect"] == 0
    assert db.get_film("se7en-1995")["wikipedia_title"] == "Seven (1995 film)"
    assert db.get_film("metropolis-1927")["wikipedia_title"] == "Metropolis (1927 film)"


def test_backfill_reads_the_stored_article_rather_than_searching_by_title(
    store, monkeypatch,
):
    _film("the-birds-1963", "The Birds", 1963, "tt0056869", "The Birds (film)")
    asked = []

    def fake_fetch(title, year=None, article=None):
        asked.append((title, year, article))
        return {"found": True, "article": article, "url": f"https://en.wikipedia.org/wiki/{article}",
                "plot": "## Plot\nBirds attack a coastal town.", "themes": "", "reception": ""}

    monkeypatch.setattr(wiki, "fetch", fake_fetch)
    monkeypatch.setattr(wiki, "search_article",
                        lambda *a, **k: pytest.fail("resolution must not fall back to a title search"))

    stats = wiki.backfill_plots(progress=None)

    assert stats["fetched"] == 1
    assert asked == [("The Birds", 1963, "The Birds (film)")]
    assert "Birds attack" in db.get_evidence("the-birds-1963")["plot"]


def test_a_film_with_no_resolved_article_is_skipped_rather_than_searched(
    store, monkeypatch,
):
    _film("carlos-2010", "Carlos", 2010, "tt1392197")  # quarantined: no article
    monkeypatch.setattr(wiki, "fetch",
                        lambda *a, **k: pytest.fail("nothing may be fetched by title guess"))

    said = []
    stats = wiki.backfill_plots(progress=said.append)

    assert stats == {"fetched": 0, "no_plot": 0, "not_found": 0, "skipped": 0,
                     "failed": 0, "unresolved": 1}
    assert any("resolve-articles" in line for line in said)
