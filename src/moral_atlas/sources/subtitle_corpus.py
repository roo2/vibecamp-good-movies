"""Build a corpus from the films' own dialogue, and nothing else.

Two problems with growing the corpus out of Wikipedia, one practical and one
that matters more.

SPEED. Ranking a year's category by article length costs about thirty requests
per year against an API that answers in its own time, which came to roughly
three minutes a year — over two hours for a sweep, before a single film had been
ingested. The OPUS index makes the same corpus a handful of ranged reads: the
archive's central directory is fetched once, and every film after that is about
80 KB with no account and no daily limit.

WHAT IS IN THE TEXT. Wikipedia gives three layers and two of them are somebody
else's reading of the film. A critical reception section is *literally* a
collection of critics' moral opinions; a plot summary is an editor's decision
about which events matter and how to characterise them, written in prose that
often names the moral of the story outright. Scoring a film's moral positions
against either means measuring the encyclopaedia as much as the film — and the
inconsistency is not random, since prestige films attract long interpretive
articles and genre films get plot mechanics.

Subtitles are the film's own words. They are not neutral either — they omit
image, performance and cut, which is a real limit and is why the `subs` variant
exists alongside the others rather than replacing them — but what they leave out
is not somebody's argument about what the film means. For a corpus built to ask
what films argue, that is the difference that counts.

So films here get ONE evidence layer, and the `subs` condition is the one they
can be scored under.

SELECTION. Notability comes from Wikidata sitelinks — how many language editions
of Wikipedia carry an article on the film. It beats English article length on
both axes that matter here: it is a cross-lingual signal rather than an
anglophone one, and it is a property of the film rather than of how much a
particular wiki community enjoys writing. Films are then kept only if the OPUS
index actually holds a track for them, so nothing enters the corpus that cannot
be scored.
"""
from __future__ import annotations

from typing import Any, Iterable

from ._http import cached_get

SPARQL = "https://query.wikidata.org/sparql"

# Films with articles in at least this many language editions. 45 keeps the
# result inside the query service's time limit while still returning several
# thousand candidates — far more than a sweep needs.
MIN_SITELINKS = 45

QUERY = """
SELECT ?imdb ?title ?year ?sitelinks WHERE {
  ?film wdt:P31 wd:Q11424 ;
        wdt:P345 ?imdb ;
        wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= %(low)d && ?sitelinks < %(high)d)
  ?film rdfs:label ?title . FILTER(LANG(?title) = "en")
  OPTIONAL { ?film wdt:P577 ?date }
  BIND(YEAR(?date) AS ?year)
}
ORDER BY DESC(?sitelinks)
LIMIT %(limit)d
"""

# The query service caps a result set and, during an outage, throttles hard —
# it answered one request a minute while this was written. Asking for one band
# of notability at a time keeps each response small enough to return, and
# `cached_get` means a band already fetched is never asked for twice.
BANDS = [(60, 10_000), (48, 60), (40, 48), (34, 40), (30, 34), (26, 30), (22, 26)]


def _band(low: int, high: int, limit: int) -> list[dict[str, Any]]:
    payload = cached_get("wikidata", SPARQL, {
        "query": QUERY % {"low": low, "high": high, "limit": limit},
        "format": "json",
    }, headers={"Accept": "application/sparql-results+json"})
    return payload["results"]["bindings"]


def notable_films(bands: list[tuple[int, int]] | None = None,
                  limit: int = 2500, progress=None) -> list[dict[str, Any]]:
    """Films by how many Wikipedias carry them, most-covered first.

    A film has one row per release date in Wikidata — a re-release or a festival
    premiere each add one — so rows are collapsed onto the IMDb id and the
    EARLIEST year is kept, which is the one that dates the work rather than a
    later reissue.
    """
    rows = []
    for low, high in (bands or BANDS):
        try:
            found = _band(low, high, limit)
        except Exception as error:  # noqa: BLE001 — one throttled band is not the sweep
            if progress:
                progress(f"[yellow]sitelinks {low}-{high}: {type(error).__name__}[/]")
            continue
        rows.extend(found)
        if progress:
            progress(f"sitelinks {low}-{high}: {len(found)} rows")

    films: dict[str, dict[str, Any]] = {}
    for row in rows:
        imdb = row["imdb"]["value"]
        year = row.get("year", {}).get("value")
        year = int(year) if year and year.isdigit() else None
        existing = films.get(imdb)
        if existing is None:
            films[imdb] = {
                "imdb_id": imdb,
                "title": row["title"]["value"],
                "year": year,
                "sitelinks": int(row["sitelinks"]["value"]),
            }
        elif year and (existing["year"] is None or year < existing["year"]):
            existing["year"] = year
    return sorted(films.values(), key=lambda f: -f["sitelinks"])


def with_subtitles(
    films: Iterable[dict[str, Any]], version: str = "v2024", lang: str = "en",
) -> list[dict[str, Any]]:
    """Keep only films OPUS actually holds a track for.

    Checked against the index rather than by attempting a fetch, so a film that
    cannot be scored never reaches the corpus at all — an ingested film with no
    evidence is a row that looks like data and is not.
    """
    from . import opus

    index = opus.build_index(version, lang)
    return [film for film in films if opus.imdb_key(film["imdb_id"]) in index]


def ingest_subtitles(
    films: list[dict[str, Any]], version: str = "v2024", progress=None,
) -> dict[str, int]:
    """Store each film's dialogue, and no other layer."""
    from .. import db
    from . import subtitles as subs_mod
    from .ingest import slugify

    db.init_db()
    stats = {"ingested": 0, "no_track": 0, "failed": 0, "cues": 0}
    for film in films:
        film_id = slugify(film["title"], film.get("year"))
        try:
            # `acquire` rather than `opus.fetch_cues` directly: it walks the
            # source chain, applies the plausibility check that rejects
            # concatenated dual-language tracks and truncated stubs, and returns
            # Cue objects — which is what `cues_to_text` renders.
            cues, meta = subs_mod.acquire(
                film_id, film["title"], film.get("year"), film["imdb_id"], None)
        except Exception as error:  # noqa: BLE001 — one bad track must not end the sweep
            stats["failed"] += 1
            if progress:
                progress(f"[red]FAILED[/] {film['title']}: {type(error).__name__}: {error}")
            continue

        if not cues:
            stats["no_track"] += 1
            if progress:
                progress(f"[dim]no usable track[/] {film['title']} "
                         f"({meta.get('reason', 'unknown')})")
            continue

        db.upsert_film({
            "film_id": film_id, "title": film["title"], "year": film.get("year"),
            "imdb_id": film["imdb_id"],
            "seed_note": f"subtitles-only:sitelinks={film['sitelinks']}",
            "fetched_at": db.now(),
        })
        db.upsert_evidence(film_id, "subtitles", subs_mod.cues_to_text(cues), None,
                           {**meta, "n_cues": len(cues)})
        stats["ingested"] += 1
        stats["cues"] += len(cues)
        if progress and stats["ingested"] % 25 == 0:
            progress(f"  {stats['ingested']} ingested "
                     f"({stats['no_track']} without a usable track)")
    return stats
