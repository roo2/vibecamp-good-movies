"""Curated blind-story copy and its deploy-time data migration."""
from __future__ import annotations

from dataclasses import replace

import pytest

from moral_atlas import db
from moral_atlas.config import settings
from moral_atlas.sources import seed


def isolated_store(monkeypatch, tmp_path):
    test_settings = replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "atlas.sqlite",
    )
    monkeypatch.setattr(db, "settings", lambda: test_settings)


def test_description_migration_updates_existing_rows_and_inserts_new_ones(
    monkeypatch, tmp_path,
):
    isolated_store(monkeypatch, tmp_path)
    db.init_db()
    db.upsert_film({
        "film_id": "legacy-lion-id", "title": "The Lion King", "year": 1994,
        "runtime": 88, "tmdb_id": 8587, "genres": ["Animation", "Drama"],
        "artwork_url": "https://example.test/lion.jpg",
        "description": "Old difficult copy.",
    })
    seed_file = tmp_path / "films.yaml"
    seed_file.write_text(
        "films:\n"
        "  - title: The Lion King\n"
        "    year: 1994\n"
        "  - title: The Matrix\n"
        "    year: 1999\n",
        encoding="utf-8",
    )

    first = seed.sync_seed_films(str(seed_file))
    assert first == {"inserted": 1, "updated": 1, "unchanged": 0}
    lion = db.get_film("legacy-lion-id")
    assert lion["description"] == seed.DESCRIPTIONS["The Lion King"]
    assert lion["runtime"] == 88, "the migration must preserve corpus metadata"
    assert lion["tmdb_id"] == 8587
    assert lion["genres"] == ["Animation", "Drama"]
    assert lion["artwork_url"] == "https://example.test/lion.jpg"
    assert db.get_film("the-matrix-1999")["description"] == seed.DESCRIPTIONS["The Matrix"]

    second = seed.sync_seed_films(str(seed_file))
    assert second == {"inserted": 0, "updated": 0, "unchanged": 2}


def test_blind_story_descriptions_stay_short():
    too_long = {
        title: len(description.split())
        for title, description in seed.DESCRIPTIONS.items()
        if len(description.split()) > 20
    }
    assert too_long == {}


def test_description_migration_refuses_to_replace_a_colliding_film(
    monkeypatch, tmp_path,
):
    isolated_store(monkeypatch, tmp_path)
    db.init_db()
    db.upsert_film({
        "film_id": "the-matrix-1999", "title": "A Different Film", "year": 2001,
        "runtime": 123, "description": "Keep me.",
    })
    seed_file = tmp_path / "films.yaml"
    seed_file.write_text(
        "films:\n  - title: The Matrix\n    year: 1999\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Refusing to replace existing film"):
        seed.sync_seed_films(str(seed_file))

    untouched = db.get_film("the-matrix-1999")
    assert untouched["title"] == "A Different Film"
    assert untouched["runtime"] == 123
    assert untouched["description"] == "Keep me."
