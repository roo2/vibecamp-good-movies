"""Wikipedia evidence — the event spine, plus themes and reception.

Needs no API key, which makes it the one layer that works out of the box.

The themes/reception sections matter more than they look. They are the main
defence against the endorsement problem: a plot summary of Starship Troopers
reads as a sincere war picture, and it is the analysis section that says
"satire" out loud.
"""
from __future__ import annotations

import re
from typing import Any

from .. import db
from ._http import cached_get

API = "https://en.wikipedia.org/w/api.php"

# Wikipedia section headings vary; map the ones that matter onto our layers.
PLOT_HEADINGS = {"plot", "plot summary", "synopsis", "story", "premise", "plot synopsis"}
THEME_HEADINGS = {
    "themes", "analysis", "interpretation", "themes and analysis",
    "themes and interpretation", "themes and motifs", "style and themes",
    "motifs", "symbolism", "interpretations", "themes and style",
    "analysis and themes", "style", "genre and themes",
}
RECEPTION_HEADINGS = {
    "reception", "critical reception", "critical response", "critical analysis",
    "legacy", "reception and legacy", "critical reception and legacy",
    "contemporary reception", "retrospective assessment", "accolades",
}


def search_article(title: str, year: int | None = None) -> str | None:
    """Find the most plausible article title for a film."""
    query = f"{title} {year} film" if year else f"{title} film"
    data = cached_get(
        "wiki",
        API,
        {
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": 8, "format": "json", "formatversion": 2,
        },
    )
    hits = data.get("query", {}).get("search", [])
    if not hits:
        return None

    lowered = title.lower()
    # Prefer an exact-ish title match that looks like a film article.
    for hit in hits:
        name = hit["title"]
        low = name.lower()
        if low == lowered or low.startswith(f"{lowered} ("):
            if "film" in low or low == lowered:
                return name
    for hit in hits:
        if "film" in hit["title"].lower():
            return hit["title"]
    return hits[0]["title"]


def populate_artwork(force: bool = False) -> dict[str, int]:
    """Store Wikipedia lead-image URLs; no API key is required."""
    db.init_db()
    stats = {"updated": 0, "missing": 0, "skipped": 0}
    for film in db.list_films():
        if film.get("artwork_url") and not force:
            stats["skipped"] += 1
            continue
        article = film.get("wikipedia_title") or search_article(film["title"], film.get("year"))
        if not article:
            stats["missing"] += 1
            continue
        data = cached_get("wiki", API, {
            "action": "query", "prop": "pageimages", "piprop": "thumbnail",
            "pithumbsize": 780, "titles": article, "redirects": 1,
            "format": "json", "formatversion": 2,
        })
        pages = data.get("query", {}).get("pages", [])
        url = pages[0].get("thumbnail", {}).get("source") if pages else None
        if not url:
            stats["missing"] += 1
            continue
        db.set_film_artwork_url(film["film_id"], url)
        stats["updated"] += 1
    return stats


def fetch_extract(article: str) -> tuple[str, str] | None:
    """Return (plaintext, canonical_title) for an article, following redirects."""
    data = cached_get(
        "wiki",
        API,
        {
            "action": "query", "prop": "extracts", "explaintext": 1,
            "exsectionformat": "wiki", "titles": article, "redirects": 1,
            "format": "json", "formatversion": 2,
        },
    )
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    page = pages[0]
    text = page.get("extract") or ""
    return (text, page.get("title", article)) if text else None


def split_sections(text: str) -> list[tuple[tuple[str, ...], str]]:
    """Split a plaintext extract into (heading path, body) pairs, in order.

    Path-aware rather than flat, because on film articles the interpretive
    material is almost never a level-2 heading. Real examples from the corpus:
    Maleficent's moral analysis lives at 'Reception > Rape allegory', and
    themes sections routinely hang off 'Production'. Folding subsections into
    their parent loses exactly the text we most want.
    """
    heading_re = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$")
    sections: list[tuple[tuple[str, ...], list[str]]] = []
    stack: list[tuple[int, str]] = []
    current: list[str] = []
    sections.append(((("__lead__",)), current))

    for line in text.splitlines():
        m = heading_re.match(line.strip())
        if not m:
            current.append(line)
            continue
        level, name = len(m.group(1)), m.group(2).strip().lower()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, name))
        current = []
        sections.append((tuple(n for _, n in stack), current))

    return [(path, "\n".join(body).strip()) for path, body in sections]


# Commercial and administrative subsections carry no moral signal and would
# dilute the layer they sit in.
COMMERCE_HEADINGS = {
    "box office", "accolades", "awards", "home media", "marketing", "release",
    "theatrical", "year-end lists", "other honors", "video games",
    "sequels and spin-offs", "stage adaptations", "cgi remake", "re-releases",
    "localization", "original theatrical run", "commercial analysis",
    "casting", "filming", "visual effects", "costume design", "reshoots",
}


def _collect(
    sections: list[tuple[tuple[str, ...], str]],
    wanted: set[str],
    exclude: set[str] = frozenset(),
) -> str:
    parts = []
    for path, body in sections:
        if not body:
            continue
        names = set(path)
        if names & exclude:
            continue
        if names & wanted:
            label = " > ".join(p.title() for p in path)
            parts.append(f"## {label}\n{body}")
    return "\n\n".join(parts)


def fetch(title: str, year: int | None = None, article: str | None = None) -> dict[str, Any]:
    """Fetch and split one film's Wikipedia evidence.

    Returns {plot, themes, reception, article, url, found}. Missing layers come
    back as empty strings rather than raising — a film with no themes section is
    a normal, informative outcome, not an error.
    """
    name = article or search_article(title, year)
    if not name:
        return {"found": False, "article": None, "plot": "", "themes": "", "reception": ""}

    got = fetch_extract(name)
    if not got:
        return {"found": False, "article": name, "plot": "", "themes": "", "reception": ""}

    text, canonical = got
    sections = split_sections(text)

    return {
        "found": True,
        "article": canonical,
        "url": f"https://en.wikipedia.org/wiki/{canonical.replace(' ', '_')}",
        "plot": _collect(sections, PLOT_HEADINGS),
        "themes": _collect(sections, THEME_HEADINGS, COMMERCE_HEADINGS),
        "reception": _collect(sections, RECEPTION_HEADINGS, COMMERCE_HEADINGS),
        "lead": next((b for p, b in sections if p == ("__lead__",)), ""),
        "all_headings": [" > ".join(p) for p, _ in sections if p != ("__lead__",)],
    }


WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def wikidata_facts(article: str) -> dict[str, Any]:
    """Get IMDb id (P345) and runtime in minutes (P2047) from Wikidata.

    Needs no credential, which matters more than it looks. The OPUS subtitle
    archive is keyed by IMDb id, so without this the only route to one is a TMDB
    account. Runtime matters too: OPUS holds dozens of tracks per film including
    concatenated dual-language files, and runtime is what tells a plausible
    track from a corrupt one.
    """
    data = cached_get(
        "wikidata", WIKIDATA_API,
        {"action": "wbgetentities", "sites": "enwiki", "titles": article,
         "props": "claims", "format": "json", "formatversion": 2},
    )
    out: dict[str, Any] = {"imdb_id": None, "runtime": None}
    for entity in (data.get("entities") or {}).values():
        claims = entity.get("claims") or {}
        for claim in claims.get("P345", []):
            value = (claim.get("mainsnak", {}).get("datavalue", {}) or {}).get("value")
            if value and out["imdb_id"] is None:
                out["imdb_id"] = str(value)
        for claim in claims.get("P2047", []):
            value = (claim.get("mainsnak", {}).get("datavalue", {}) or {}).get("value")
            if isinstance(value, dict) and out["runtime"] is None:
                try:
                    out["runtime"] = int(float(value.get("amount", 0)))
                except (TypeError, ValueError):
                    pass
    return out


def imdb_id(article: str) -> str | None:
    return wikidata_facts(article).get("imdb_id")
