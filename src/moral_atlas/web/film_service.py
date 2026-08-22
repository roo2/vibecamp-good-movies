"""Read-only projection of the existing atlas `films` table for web cards."""
from __future__ import annotations

import random
from typing import Any

from .. import db


def random_onboarding_films(limit: int = 5) -> list[dict[str, Any]]:
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


def build_session_deck() -> dict[str, list[Any]]:
    """Create one shared, non-overlapping deck for a group session."""
    db.init_db()
    films = db.list_films()
    if len(films) < 15:
        return {"direct": [], "pairs": []}
    selected = random.SystemRandom().sample(films, k=15)
    return {
        "direct": [film["film_id"] for film in selected[:5]],
        "pairs": [[selected[index]["film_id"], selected[index + 1]["film_id"]] for index in range(5, 15, 2)],
    }


def film_card(film_id: str, include_title: bool = True) -> dict[str, Any] | None:
    film = db.get_film(film_id)
    if film is None:
        return None
    card = {"id": film["film_id"], "description": film.get("description") or "A story about the choices people make when what matters is at stake."}
    if include_title:
        card.update({
            "title": film["title"], "year": film.get("year"),
            "genre": (film.get("genres") or ["Film"])[0], "runtime_min": film.get("runtime"),
        })
    return card


def film_exists(film_id: str) -> bool:
    return db.get_film(film_id) is not None
