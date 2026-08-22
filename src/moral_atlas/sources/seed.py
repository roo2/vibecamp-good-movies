"""Seed the existing films table without fetching external evidence."""
from __future__ import annotations

from .ingest import load_seeds, slugify
from .. import db


def seed_films(path: str = "seeds/phase0.yaml") -> int:
    """Insert missing seed films; never overwrite an existing film row."""
    db.init_db()
    existing = {(film["title"], film.get("year")) for film in db.list_films()}
    inserted = 0
    for seed in load_seeds(path):
        key = (seed["title"], seed.get("year"))
        if key in existing:
            continue
        film_id = slugify(*key)
        db.upsert_film({
            "film_id": film_id,
            "title": seed["title"],
            "year": seed.get("year"),
            "seed_note": seed.get("note"),
            "fetched_at": db.now(),
        })
        existing.add(key)
        inserted += 1
    return inserted
