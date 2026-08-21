"""TMDB metadata.

Everything here doubles as a confound covariate: genre, year, country and
language are exactly what section 05 of the plan regresses each emergent factor
against, to catch a "factor" that is really just 'is this a war film'.

Billing order is kept because cast position is a free, weak point-of-view
signal — whose story the production thought it was telling.
"""
from __future__ import annotations

from typing import Any

from ..config import settings
from ._http import cached_get

BASE = "https://api.themoviedb.org/3"


def _auth() -> tuple[dict[str, str], dict[str, Any]]:
    """Return (headers, extra_params) for whichever TMDB credential exists."""
    s = settings()
    if s.tmdb_read_token:
        return {"Authorization": f"Bearer {s.tmdb_read_token}"}, {}
    if s.tmdb_api_key:
        return {}, {"api_key": s.tmdb_api_key}
    raise RuntimeError(
        "No TMDB credential. Set TMDB_READ_TOKEN (preferred) or TMDB_API_KEY in .env — "
        "both are free from https://www.themoviedb.org/settings/api"
    )


def search(title: str, year: int | None = None) -> dict[str, Any] | None:
    headers, extra = _auth()
    params = {"query": title, "include_adult": "false", **extra}
    if year:
        params["year"] = year
    data = cached_get("tmdb", f"{BASE}/search/movie", params, headers)
    results = data.get("results", [])
    if not results:
        return None
    if year:
        exact = [
            r for r in results
            if (r.get("release_date") or "").startswith(str(year))
        ]
        if exact:
            return exact[0]
    return results[0]


def details(tmdb_id: int) -> dict[str, Any]:
    headers, extra = _auth()
    return cached_get(
        "tmdb",
        f"{BASE}/movie/{tmdb_id}",
        {"append_to_response": "credits,keywords,external_ids", **extra},
        headers,
    )


def to_film_row(d: dict[str, Any]) -> dict[str, Any]:
    """Flatten a TMDB detail payload into our films table shape."""
    credits = d.get("credits", {}) or {}
    crew = credits.get("crew", []) or []
    cast = credits.get("cast", []) or []

    directors = [c["name"] for c in crew if c.get("job") == "Director"]
    writers = [
        c["name"] for c in crew
        if c.get("department") == "Writing"
        and c.get("job") in {"Screenplay", "Writer", "Story", "Novel", "Author"}
    ]
    keywords = [k["name"] for k in (d.get("keywords", {}) or {}).get("keywords", [])]

    # TMDB records source-material relationships as keywords; these are the
    # revision-lineage signal, which is the highest value-per-token input we have.
    based_on = next(
        (k for k in keywords if "based on" in k.lower() or "adapted from" in k.lower()),
        None,
    )

    release = d.get("release_date") or ""
    return {
        "tmdb_id": d.get("id"),
        "imdb_id": (d.get("external_ids", {}) or {}).get("imdb_id") or d.get("imdb_id"),
        "title": d.get("title"),
        "year": int(release[:4]) if release[:4].isdigit() else None,
        "runtime": d.get("runtime"),
        "origin_country": d.get("origin_country") or
                          [c["iso_3166_1"] for c in d.get("production_countries", [])],
        "original_language": d.get("original_language"),
        "genres": [g["name"] for g in d.get("genres", [])],
        "keywords": keywords,
        "directors": directors,
        "writers": sorted(set(writers)),
        "billed_cast": [c["name"] for c in sorted(cast, key=lambda c: c.get("order", 999))[:10]],
        "collection": (d.get("belongs_to_collection") or {}).get("name"),
        "based_on": based_on,
        "budget": d.get("budget"),
        "revenue": d.get("revenue"),
    }
