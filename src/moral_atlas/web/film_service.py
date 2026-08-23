"""Read-only projection of the existing atlas `films` table for web cards."""
from __future__ import annotations

import random
from typing import Any

from .. import db


def random_onboarding_films(limit: int = 5) -> list[dict[str, Any]]:
    db.init_db()
    films = deck_eligible_films()
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
            "artwork_url": film.get("artwork_url"),
        }
        for film in selected
    ]


def deck_eligible_films() -> list[dict[str, Any]]:
    """Films the product may show a person.

    The research corpus is far larger than the curated one and grows by
    enumeration, so its films have no hand-written blind-story description. The
    blind pairs are nothing BUT that description — without one every pair would
    read "A story about the choices people make", which is not a choice between
    two stories. Having a description is therefore the eligibility test.
    """
    return [film for film in db.list_films() if (film.get("description") or "").strip()]


def build_session_deck() -> dict[str, list[Any]]:
    """Create one shared, non-overlapping deck for a group session."""
    db.init_db()
    films = deck_eligible_films()
    films_with_artwork = [film for film in films if (film.get("artwork_url") or "").strip()]
    if len(films) < 15:
        return {"direct": [], "pairs": []}

    # The first five cards are named films, so they should always have their
    # poster available. The later blind-story cards deliberately conceal their
    # titles and can use the wider eligible corpus.
    chooser = random.SystemRandom()
    direct = chooser.sample(films_with_artwork if len(films_with_artwork) >= 5 else films, k=5)
    direct_ids = {film["film_id"] for film in direct}
    blind = chooser.sample([film for film in films if film["film_id"] not in direct_ids], k=10)
    return {
        "direct": [film["film_id"] for film in direct],
        "pairs": [[blind[index]["film_id"], blind[index + 1]["film_id"]] for index in range(0, 10, 2)],
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
            "artwork_url": film.get("artwork_url"),
        })
    return card


def film_exists(film_id: str) -> bool:
    return db.get_film(film_id) is not None
