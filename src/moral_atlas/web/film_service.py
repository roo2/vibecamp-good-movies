"""Read-only projection of the existing atlas `films` table for web cards."""
from __future__ import annotations

import random
from typing import Any

from .. import db


def random_onboarding_films(limit: int = 10) -> list[dict[str, Any]]:
    db.init_db()
    films = db.list_films()
    if not films:
        return []
    selected = random.SystemRandom().sample(films, k=min(limit, len(films)))
    return [
        {
            "id": film["film_id"],
            "title": film["title"],
            "year": film.get("year"),
            "genre": (film.get("genres") or ["Film"])[0],
            "runtime_min": film.get("runtime"),
        }
        for film in selected
    ]


def film_exists(film_id: str) -> bool:
    return db.get_film(film_id) is not None
