"""Read-only projection of the existing atlas `films` table for web cards."""
from __future__ import annotations

import math
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


# How many named films a person is asked about. Every one is a swipe, so this is
# cheaper in a person's time than its size suggests, and each one is another
# point the profile is drawn through.
DIRECT_CARDS = 20

# A deck may be short, but not this short: below this a person has been asked
# about too little for the profile to mean anything, and a session that starts
# is worse than one that says it cannot.
MIN_CARDS = 10

# Films from before this are asked about last, and rarely.
#
# Two people testing this said the films felt old, and they were right: the
# corpus reaches back to the 1920s and nothing in the deck cared what year it
# was. "Have you seen it?" is a different question about a 1953 film than a 2019
# one — most people simply have not, which spends a card and teaches nothing.
OLDEST_INTERESTING_YEAR = 1980
NEWEST_YEAR = 2025


def _recency(film: dict[str, Any]) -> float:
    """0 for anything old enough, rising to 1 for the newest films."""
    year = film.get("year") or 0
    if year <= OLDEST_INTERESTING_YEAR:
        return 0.0
    return min(1.0, (year - OLDEST_INTERESTING_YEAR) / (NEWEST_YEAR - OLDEST_INTERESTING_YEAR))


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
    """Films worth asking a person about: has a poster, and has been read.

    A poster because the card is mostly poster, and a film the scorer has read
    because otherwise the answer has no propositions to be read against — the
    question costs the person time and teaches the profile nothing.

    A hand-written description USED to be required as well, as a proxy for
    "recognisable". It was a bad proxy and an expensive one: only fifty films
    have one, half of those predate 1990, and it held the pool at forty when the
    corpus holds 463 films that have a poster and have been read — Dune, Barbie,
    Oppenheimer, Top Gun: Maverick among them. The corpus was enumerated in
    notability order, so recognisable is what it already is; the description only
    marked which films somebody had got around to writing about.

    Age is handled by weighting rather than by a bar — see `build_session_deck`.

    If too few films have been read — a fresh database, a scorer mid-run — the
    scored requirement is dropped rather than handing back an empty deck. A
    session that reads a person imperfectly beats one that cannot start.
    """
    showable = [film for film in db.list_films()
                if (film.get("artwork_url") or "").strip()]
    read = _films_the_scorer_has_read()
    scored = [film for film in showable if film["film_id"] in read]
    return scored if len(scored) >= DIRECT_CARDS else showable


def build_session_deck() -> dict[str, list[Any]]:
    """Create one shared deck of named films for a group session.

    `pairs` stays in the shape, empty. Existing sessions carry decks that have
    it, the reader of a deck is entitled to expect the key, and a session started
    before this change should keep working rather than raise a KeyError halfway
    through somebody's evening.
    """
    db.init_db()
    films = deck_eligible_films()
    if len(films) < MIN_CARDS:
        return {"direct": [], "pairs": []}
    wanted = min(DIRECT_CARDS, len(films))

    # Weighted sampling without replacement, newer films favoured. The weight is
    # applied as Gumbel noise added to the recency score and taking the top k,
    # which draws in proportion to exp(recency / SPREAD) — so a 2019 film is
    # likelier than a 1958 one without the 1958 one becoming impossible. A hard
    # cutoff would be simpler and worse: half the corpus would stop existing, and
    # an old film someone loves is one of the more informative answers there is.
    chooser = random.SystemRandom()
    spread = 0.45

    def key(film: dict[str, Any]) -> float:
        gumbel = -math.log(-math.log(chooser.random()))
        return _recency(film) + spread * gumbel

    direct = sorted(films, key=key, reverse=True)[:wanted]
    chooser.shuffle(direct)   # drawn newest-first; shown in no particular order
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
