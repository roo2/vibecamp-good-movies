"""Film metadata from Wikidata, keyed on the IMDb id we already hold.

WHY NOT TMDB. There is already a TMDB path in `tmdb.py`, and it returns more
(cast, budget, revenue, keywords). Two reasons this exists beside it.

The first is practical: the subtitle-corpus ingest never called TMDB, so 570
films arrived with an IMDb id and almost nothing else — twelve columns empty,
including every one that could group films for an analysis or filter them in the
app. Backfilling through TMDB needs a key this deployment does not have.

The second matters more. TMDB's terms of use forbid using their content to train
or develop machine-learning models, which is exactly what the factor analysis
is. Genre from TMDB may decorate the app; genre from TMDB may not become a
variable in a study of what films argue. Wikidata is CC0, so a column filled
from here can cross that line freely. Anything sourced from TMDB should stay in
the display layer, and keeping the two behind separate modules is what makes
that boundary checkable later.

Multi-valued properties come back as one row per value, so a film with three
genres and two directors returns six rows. They are folded back into lists here.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Iterator

import httpx

from .. import db
from ..config import USER_AGENT

ENDPOINT = "https://query.wikidata.org/sparql"

# One row per (film x genre x country x ...) combination, so the batch stays
# small: 50 films with a few values each is already a few hundred rows.
BATCH = 50

# The columns this source can fill, and the Wikidata property behind each. Kept
# as data so the SELECT, the OPTIONAL block and the writer cannot drift apart.
FIELDS = {
    "genres": "wdt:P136",
    "origin_country": "wdt:P495",
    "original_language": "wdt:P364",
    "directors": "wdt:P57",
    "writers": "wdt:P58",
    "based_on": "wdt:P144",
}
# Which of those are lists in our schema; the rest keep a single value.
LIST_FIELDS = {"genres", "origin_country", "directors", "writers"}


def _query(imdb_ids: list[str]) -> str:
    values = " ".join(f'"{i}"' for i in imdb_ids)
    optional = "\n  ".join(
        f"OPTIONAL {{ ?film {prop} ?{name} }}" for name, prop in FIELDS.items())
    labels = " ".join(f"?{name}Label" for name in FIELDS)
    return f"""SELECT ?imdb {labels} WHERE {{
  VALUES ?imdb {{ {values} }}
  ?film wdt:P345 ?imdb .
  {optional}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def _fetch(imdb_ids: list[str], timeout: float = 90.0) -> list[dict[str, Any]]:
    response = httpx.get(
        ENDPOINT,
        params={"query": _query(imdb_ids)},
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.json()["results"]["bindings"]


def _fold(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """One row per value-combination becomes one record per film."""
    out: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        imdb = row.get("imdb", {}).get("value")
        if not imdb:
            continue
        record = out.setdefault(imdb, {name: set() for name in FIELDS})
        for name in FIELDS:
            value = row.get(f"{name}Label", {}).get("value")
            # An unresolved label comes back as the bare Q-number, which is
            # worse than nothing in a genre filter.
            if value and not (value.startswith("Q") and value[1:].isdigit()):
                record[name].add(value)
    return {imdb: {k: sorted(v) for k, v in rec.items()} for imdb, rec in out.items()}


def batches(items: list[str], size: int = BATCH) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def films_missing_metadata(limit: int | None = None) -> list[tuple[str, str]]:
    """(film_id, imdb_id) for films that have an IMDb id but no genres yet."""
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT film_id, imdb_id FROM films "
            "WHERE imdb_id IS NOT NULL AND trim(imdb_id) <> '' "
            "AND (genres IS NULL OR genres IN ('', '[]')) "
            "ORDER BY film_id" + (f" LIMIT {int(limit)}" if limit else ""),
        ).fetchall()
    return [(r["film_id"], r["imdb_id"]) for r in rows]


def _write(film_id: str, record: dict[str, Any]) -> int:
    """UPDATE only the columns we filled.

    Deliberately not `db.upsert_film`, which is INSERT OR REPLACE across every
    column: handing it a partial row would blank the seed note, the artwork and
    the hand-written descriptions the moment this ran.
    """
    sets, args = [], []
    for name in FIELDS:
        values = record.get(name) or []
        if not values:
            continue
        sets.append(f"{name}=?")
        args.append(json.dumps(values) if name in LIST_FIELDS else values[0])
    if not sets:
        return 0
    args.append(film_id)
    with db.connect() as con:
        con.execute(f"UPDATE films SET {','.join(sets)} WHERE film_id=?", args)
    return len(sets)


def backfill(limit: int | None = None, progress=None) -> dict[str, int]:
    """Fill genre, country, language, director, writer and source from Wikidata."""
    targets = films_missing_metadata(limit)
    by_imdb = {imdb: film_id for film_id, imdb in targets}
    stats = {"looked_at": len(targets), "matched": 0, "updated": 0, "columns": 0}
    for batch in batches(sorted(by_imdb)):
        try:
            found = _fold(_fetch(batch))
        except Exception as error:            # one bad batch must not lose the rest
            if progress:
                progress(f"  batch of {len(batch)} failed: {error}")
            continue
        stats["matched"] += len(found)
        for imdb, record in found.items():
            filled = _write(by_imdb[imdb], record)
            if filled:
                stats["updated"] += 1
                stats["columns"] += filled
        if progress:
            progress(f"  {stats['updated']}/{stats['looked_at']} filled")
    return stats
