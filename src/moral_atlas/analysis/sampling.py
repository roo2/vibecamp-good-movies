"""Choose which films get asked to write propositions.

The bank is written by whichever films are harvested, and everything downstream
inherits their moral vocabulary. The first harvest took the first 135 films that
happened to have subtitles, and that set is 122 English-language and 119 US or
UK — so the axes recovered from it describe the moral world of Anglophone
popular cinema and quietly present it as the moral world.

That is not a prompt problem and no wording fixes it. It is a sampling problem,
and it only became visible once the Wikidata backfill gave the films a country,
a language and a genre to be counted by.

WHAT THIS OPTIMISES. Greedy maximum coverage over facets — language, country,
decade, genre. Each film is scored by how much it adds that the chosen set does
not already have, and the rarest facets are worth the most, so the first Korean
film in the set counts for far more than the ninetieth American one. It is the
standard greedy approximation, which is within (1 - 1/e) of optimal for this
kind of coverage problem and is the right amount of machinery for the job.

WHAT IT DELIBERATELY DOES NOT DO. It does not balance the corpus to quotas. A
target of "20% non-English" would be a claim about how much of the world's moral
argument is non-English, which nobody here is in a position to make. Coverage
only says: before asking a hundredth American drama what it believes, ask the
first Iranian one.

A NOTE ON WHAT THIS CANNOT REACH. The corpus itself is ~90% Anglophone, so a
perfectly diverse sample of it is still mostly Anglophone. Sampling redistributes
attention within what has been collected; widening the collection is a separate
and larger job.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any, Iterable

from .. import db

# The facets a film is counted by. Genre is included but weighted low: it is the
# most populated field and the least morally informative — "drama film" tells
# you much less about what a work argues than the country it argues from.
FACET_WEIGHT = {
    "original_language": 3.0,
    "origin_country": 3.0,
    "decade": 1.5,
    "genres": 1.0,
}


def _facets(film: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for column in ("original_language", "origin_country", "genres"):
        raw = film.get(column)
        if not raw:
            continue
        values = json.loads(raw) if isinstance(raw, str) and raw.startswith("[") else [raw]
        out.extend((column, str(v)) for v in values if v)
    if film.get("year"):
        out.append(("decade", f"{int(film['year']) // 10 * 10}s"))
    return out


def corpus(only_with_evidence: bool = True) -> list[dict[str, Any]]:
    """Films eligible to be harvested, with the facets to balance across."""
    with db.connect(read_only=True) as con:
        rows = [dict(r) for r in con.execute(
            "SELECT film_id, title, year, original_language, origin_country, genres FROM films")]
        if only_with_evidence:
            usable = {r[0] for r in con.execute(
                "SELECT DISTINCT film_id FROM evidence WHERE layer='subtitles' "
                "AND content IS NOT NULL AND length(content) > 2000")}
            rows = [r for r in rows if r["film_id"] in usable]
    return rows


def already_harvested(scorer: str, variant: str) -> set[str]:
    with db.connect(read_only=True) as con:
        return {r[0] for r in con.execute(
            "SELECT DISTINCT film_id FROM model_propositions WHERE scorer=? AND variant=?",
            [scorer, variant])}


def select(films: list[dict[str, Any]], n: int,
           already: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Greedy maximum coverage: each pick is the film adding the most that is missing.

    A facet's value is 1/(1 + how many times it is already present), so the
    marginal worth of another American film falls away while the first film in
    an unrepresented language stays worth the whole of its weight. Films already
    harvested are not returned, but they DO count towards coverage — the point
    is to complete the set, not to re-balance it from nothing.
    """
    already = set(already)
    seen: Counter[tuple[str, str]] = Counter()
    for film in films:
        if film["film_id"] in already:
            seen.update(_facets(film))

    pool = [f for f in films if f["film_id"] not in already]
    chosen: list[dict[str, Any]] = []

    def gain(film: dict[str, Any]) -> float:
        total = 0.0
        for facet in _facets(film):
            total += FACET_WEIGHT.get(facet[0], 1.0) / (1.0 + seen[facet])
        # Films with almost no metadata should not win by being unusual; divide
        # by a gentle function of how many facets they have so that a rich film
        # and a bare one are compared on coverage per fact known.
        return total / math.sqrt(1 + len(_facets(film)))

    for _ in range(min(n, len(pool))):
        best = max(pool, key=gain)
        pool.remove(best)
        chosen.append(best)
        seen.update(_facets(best))
    return chosen


def coverage(films: list[dict[str, Any]]) -> dict[str, Any]:
    """How many distinct values of each facet a set of films reaches."""
    counts: dict[str, Counter] = {}
    for film in films:
        for column, value in _facets(film):
            counts.setdefault(column, Counter())[value] += 1
    return {
        "n_films": len(films),
        "distinct": {k: len(v) for k, v in sorted(counts.items())},
        "top": {k: v.most_common(5) for k, v in sorted(counts.items())},
        # The share held by the single most common value — one number for "how
        # lopsided is this set", which is the thing the first harvest got wrong.
        "dominance": {k: (v.most_common(1)[0][1] / max(sum(v.values()), 1))
                      for k, v in sorted(counts.items())},
    }
