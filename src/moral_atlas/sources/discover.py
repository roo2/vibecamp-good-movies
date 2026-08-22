"""Find several hundred films worth scoring, without a hand-written list.

The corpus has been the binding constraint on every question worth asking. Forty
films against 694 items means the item correlation matrix has rank at most 39,
so the number of moral dimensions cannot be estimated with any confidence — the
last factors to clear the parallel-analysis null clear it by fractions of a
percent and move when the null is resampled. More respondents is the only fix,
and fifty hand-picked titles will not get there.

So the list is enumerated rather than curated: Wikipedia's per-year film
categories, filtered by article length.

Article length is a blunt proxy for notability and a precise one for what this
pipeline actually needs. A film with a long article has a Plot section, which is
the whole of the `spine` evidence condition; a stub does not, and would be
ingested only to be discarded at scoring. Sorting by length and taking the top
of each year gets both properties at once without a popularity API.

Sampling per YEAR rather than taking the longest few thousand articles overall
is deliberate. Article length rises steeply with recency — a 2019 blockbuster
has three times the coverage of a 1975 equivalent — so a single global ranking
would return almost nothing before 2000 and the corpus would silently become a
study of contemporary film. A quota per year holds the era spread open.

What this does NOT fix: Wikipedia's own coverage skews anglophone, so a corpus
drawn from it inherits that. The `origin_country` covariate is what would show
it, which is a reason to keep collecting that column rather than a reason to
believe the sample is neutral.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from ._http import cached_get
from .wikipedia import API

# Enough coverage to carry a Plot section. Below this the article is a stub or a
# redirect-with-infobox, and ingestion would fetch it only to find nothing.
MIN_ARTICLE_BYTES = 20_000

# Categories are noisy: they carry lists, franchises and documentation pages.
SKIP_PATTERNS = re.compile(
    r"^(List of|Category:|Template:|Index of|Outline of)|"
    r"\b(film series|filmography|awards|soundtrack|video game)\b", re.I)


def _category_members(year: int, limit: int) -> list[dict[str, Any]]:
    """Article titles in `Category:<year> films`, paged."""
    members: list[dict[str, Any]] = []
    cont: str | None = None
    while len(members) < limit:
        params = {
            "action": "query", "list": "categorymembers",
            "cmtitle": f"Category:{year} films", "cmtype": "page",
            "cmlimit": "500", "format": "json", "formatversion": "2",
        }
        if cont:
            params["cmcontinue"] = cont
        data = cached_get("wiki", API, params)
        members.extend(data.get("query", {}).get("categorymembers", []))
        cont = (data.get("continue") or {}).get("cmcontinue")
        if not cont:
            break
    return members


def _lengths(titles: Iterable[str]) -> dict[str, int]:
    """Article length in bytes, 50 titles per request."""
    out: dict[str, int] = {}
    titles = list(titles)
    for start in range(0, len(titles), 50):
        batch = titles[start:start + 50]
        data = cached_get("wiki", API, {
            "action": "query", "prop": "info", "titles": "|".join(batch),
            "format": "json", "formatversion": "2",
        })
        for page in data.get("query", {}).get("pages", []):
            if "missing" not in page:
                out[page["title"]] = page.get("length", 0)
    return out


def _clean_title(article: str) -> tuple[str, int | None]:
    """Split "Gladiator (2000 film)" into ("Gladiator", 2000).

    The disambiguator is how Wikipedia distinguishes films from the novels and
    songs they share a name with, so it is kept as the article override and
    stripped from the title the product shows.
    """
    match = re.match(r"^(.*?)\s*\((?:(\d{4})\s+)?film\)$", article)
    if match:
        return match.group(1).strip(), int(match.group(2)) if match.group(2) else None
    match = re.match(r"^(.*?)\s*\((\d{4})\s+.*\)$", article)
    if match:
        return match.group(1).strip(), int(match.group(2))
    return article.strip(), None


def discover(
    years: Iterable[int], per_year: int = 10, min_bytes: int = MIN_ARTICLE_BYTES,
    progress=None,
) -> list[dict[str, Any]]:
    """The best-documented `per_year` films for each year given."""
    found: list[dict[str, Any]] = []
    for year in years:
        try:
            members = _category_members(year, 1200)
        except Exception as error:  # noqa: BLE001 — one bad year must not end the sweep
            if progress:
                progress(f"[yellow]{year}: {type(error).__name__}: {error}[/]")
            continue
        titles = [m["title"] for m in members if not SKIP_PATTERNS.search(m["title"])]
        lengths = _lengths(titles)
        ranked = sorted(((length, title) for title, length in lengths.items()
                         if length >= min_bytes), reverse=True)[:per_year]
        for length, article in ranked:
            title, parsed_year = _clean_title(article)
            found.append({
                "title": title, "year": parsed_year or year,
                "wikipedia": article, "bytes": length,
                "note": f"discovered:{year}",
            })
        if progress:
            progress(f"{year}  {len(ranked):>3} kept of {len(titles)} in category")
    return found


def bulk_ingest(entries: list[dict[str, Any]], progress=None) -> dict[str, int]:
    """Wikipedia evidence only, for films joining the corpus in bulk.

    `ingest_one` also chases Wikidata and a subtitle track, which is right for a
    curated seed and wrong for five hundred: subtitles dominate the wall clock
    and the `spine` condition — the one these films will be scored under — reads
    the plot section and nothing else. Films that turn out to have no plot
    section are left out of `films` entirely rather than stored as rows that can
    never be scored.

    No `description` is written. That is what keeps the research corpus out of
    the product's blind pairs; see `film_service.deck_eligible_films`.
    """
    from .. import db
    from . import wikipedia as wiki_mod
    from .ingest import slugify

    db.init_db()
    stats = {"ingested": 0, "no_plot": 0, "failed": 0}
    for entry in entries:
        film_id = slugify(entry["title"], entry.get("year"))
        try:
            wiki = wiki_mod.fetch(entry["title"], entry.get("year"), entry.get("wikipedia"))
        except Exception as error:  # noqa: BLE001 — one bad article must not end the sweep
            stats["failed"] += 1
            if progress:
                progress(f"[red]FAILED[/] {entry['title']}: {type(error).__name__}: {error}")
            continue

        if not (wiki.get("plot") or "").strip():
            stats["no_plot"] += 1
            if progress:
                progress(f"[dim]no plot[/] {entry['title']}")
            continue

        db.upsert_film({
            "film_id": film_id, "title": entry["title"], "year": entry.get("year"),
            "seed_note": entry.get("note"), "wikipedia_title": wiki.get("article"),
            "fetched_at": db.now(),
        })
        for layer in ("plot", "themes", "reception"):
            content = (wiki.get(layer) or "").strip()
            if content:
                db.upsert_evidence(film_id, layer, content, wiki.get("url"))
        stats["ingested"] += 1
        if progress and stats["ingested"] % 25 == 0:
            progress(f"  {stats['ingested']} ingested, {stats['no_plot']} without a plot section")
    return stats


def as_seed_entries(films: list[dict[str, Any]], exclude: set[str]) -> list[dict[str, Any]]:
    """Seed-file shaped, minus anything already in the corpus."""
    from .ingest import slugify

    out, seen = [], set(exclude)
    for film in films:
        film_id = slugify(film["title"], film["year"])
        if film_id in seen:
            continue
        seen.add(film_id)
        entry = {"title": film["title"], "year": film["year"], "note": film["note"]}
        # Only carry the override when the plain title would be ambiguous.
        if film["wikipedia"] != film["title"]:
            entry["wikipedia"] = film["wikipedia"]
        out.append(entry)
    return out
