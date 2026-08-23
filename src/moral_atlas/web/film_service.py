"""Read-only projection of the existing atlas `films` table for web cards."""
from __future__ import annotations

import random
from typing import Any

from .. import db
from ..config import settings


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


# How many named films a person is asked about. The session used to ask five and
# then put five blind story pairs on top; the pairs are gone, so the whole read
# now comes from films the person recognises, and there need to be enough of them
# to place someone on more than a couple of axes.
DIRECT_CARDS = 12


def _films_the_scorer_has_read() -> set[str]:
    """Film ids the product's scorer has actually returned verdicts on."""
    config = settings()
    bank = f"{config.product_scorer}-{config.product_variant}"
    with db.connect(read_only=True) as con:
        return {row["film_id"] for row in con.execute(
            "SELECT DISTINCT film_id FROM model_verdicts WHERE scorer=? "
            "AND bank_version=? AND variant=?",
            [config.product_scorer, bank, config.product_variant])}


def deck_eligible_films() -> list[dict[str, Any]]:
    """Films worth asking a person about.

    Three conditions, and the third is the one that was missing. A poster,
    because the card is mostly poster. A hand-written description, which nothing
    displays any more now that the blind pairs are gone but which still marks the
    ~50 curated titles out of 570 that arrived by enumeration — recognisable is
    the property, and having been written about by hand is its proxy.

    And a film the scorer has read. Asking whether someone liked a film the
    instrument has never scored costs them a question and teaches the profile
    nothing: their answer has no propositions to be read against. Ten of the
    fifty curated films were in that state, so a twelve-card deck could spend a
    fifth of itself learning nothing.

    If too few films clear all three — a fresh database, a scorer mid-run — the
    scored requirement is dropped rather than handing back an empty deck. A
    session that reads a person imperfectly beats one that cannot start.
    """
    curated = [film for film in db.list_films()
               if (film.get("description") or "").strip()
               and (film.get("artwork_url") or "").strip()]
    read = _films_the_scorer_has_read()
    scored = [film for film in curated if film["film_id"] in read]
    return scored if len(scored) >= DIRECT_CARDS else curated


def build_session_deck() -> dict[str, list[Any]]:
    """Create one shared deck of named films for a group session.

    `pairs` stays in the shape, empty. Existing sessions carry decks that have
    it, the reader of a deck is entitled to expect the key, and a session started
    before this change should keep working rather than raise a KeyError halfway
    through somebody's evening.
    """
    db.init_db()
    films = deck_eligible_films()
    if len(films) < DIRECT_CARDS:
        return {"direct": [], "pairs": []}

    chooser = random.SystemRandom()
    direct = chooser.sample(films, k=DIRECT_CARDS)
    return {"direct": [film["film_id"] for film in direct], "pairs": []}


def film_card(film_id: str, include_title: bool = True) -> dict[str, Any] | None:
    film = db.get_film(film_id)
    if film is None:
        return None
    # No stand-in sentence. Most of the corpus has no hand-written description,
    # and "A story about the choices people make when what matters is at stake."
    # fitted every one of them equally — which is what made it worse than saying
    # nothing: it read as a description of THIS film and described none.
    description = (film.get("description") or "").strip()
    card = {"id": film["film_id"]}
    if description:
        card["description"] = description
    if include_title:
        card.update({
            "title": film["title"], "year": film.get("year"),
            "genre": (film.get("genres") or ["Film"])[0], "runtime_min": film.get("runtime"),
            "artwork_url": film.get("artwork_url"),
        })
    return card


def film_exists(film_id: str) -> bool:
    return db.get_film(film_id) is not None
