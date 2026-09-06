"""Wikipedia evidence — the event spine, plus themes and reception.

Needs no API key, which makes it the one layer that works out of the box.

The themes/reception sections matter more than they look. They are the main
defence against the endorsement problem: a plot summary of Starship Troopers
reads as a sincere war picture, and it is the analysis section that says
"satire" out loud.
"""
from __future__ import annotations

import re
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    """Store Wikipedia lead-image URLs; no API key is required.

    `pilicense=any` is what makes this useful rather than nearly empty. The
    parameter defaults to `free`, and a film poster is almost never freely
    licensed — so the default returns an image only for films old enough to have
    fallen into the public domain. On this corpus that was six of forty: the
    pre-1960 titles, and nothing since.
    """
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
            "pithumbsize": 780, "pilicense": "any", "titles": article, "redirects": 1,
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


WDQS = "https://query.wikidata.org/sparql"


def articles_by_imdb(imdb_ids: list[str], chunk: int = 120) -> dict[str, dict[str, Any]]:
    """Resolve IMDb ids to English Wikipedia articles through Wikidata.

    `search_article` guesses from a title string, and on this corpus it guessed
    wrong twice in six hundred: Carlos (2010) resolved to Marmaduke and Jeanne
    Dielman to Gerry, both silently, both then read as plot evidence for a film
    they have nothing to do with. A title search cannot tell a right answer from
    a confident wrong one; an identifier can.

    Returns {imdb_id: {"article", "labels", "years"}}. The labels and years are
    what makes this an integrity check as well as a lookup — a stored title that
    matches no label on the entity means the id itself is wrong, which is a
    worse problem than a missing plot section and invisible without asking.
    """
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(imdb_ids), chunk):
        values = " ".join(f'"{i}"' for i in imdb_ids[start:start + chunk])
        query = (
            "SELECT ?imdb ?label ?alias ?date ?article WHERE {"
            f" VALUES ?imdb {{ {values} }}"
            " ?film wdt:P345 ?imdb ."
            ' OPTIONAL { ?film rdfs:label ?label . FILTER(lang(?label)="en") }'
            # Aliases, because a corpus title is not always the entity's label:
            # Se7en is stored on Wikidata as "Seven" with "Se7en" an alias, and
            # without this it reads as an identifier pointing at another film.
            ' OPTIONAL { ?film skos:altLabel ?alias . FILTER(lang(?alias)="en") }'
            " OPTIONAL { ?film wdt:P577 ?date }"
            " OPTIONAL { ?article schema:about ?film ;"
            " schema:isPartOf <https://en.wikipedia.org/> } }"
        )
        data = cached_get("wdqs", WDQS, {"query": query, "format": "json"})
        for binding in data.get("results", {}).get("bindings", []):
            record = out.setdefault(
                binding["imdb"]["value"], {"article": None, "labels": set(), "years": set()})
            for field in ("label", "alias"):
                if field in binding:
                    record["labels"].add(binding[field]["value"])
            if "date" in binding:
                record["years"].add(int(binding["date"]["value"][:4]))
            if "article" in binding and not record["article"]:
                # The sitelink is a URL, so the title arrives percent-encoded:
                # "It%27s a Wonderful Life" is not a title the API will match.
                slug = binding["article"]["value"].rsplit("/", 1)[-1]
                record["article"] = urllib.parse.unquote(slug).replace("_", " ")
    return out


def _comparable(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", stripped.lower())


def resolve_articles(progress=None) -> dict[str, int]:
    """Store each film's Wikipedia article, resolved by identifier, and report doubt.

    Only writes `wikipedia_title`. Films whose stored title matches no label on
    the entity behind their IMDb id are reported and left alone: the fix there
    is to correct the identifier, and overwriting the article title would bury
    the evidence that anything is wrong.
    """
    db.init_db()
    films = [f for f in db.list_films() if (f.get("imdb_id") or "").strip()]
    resolved = articles_by_imdb(sorted({f["imdb_id"] for f in films}))
    stats = {"stored": 0, "unchanged": 0, "no_article": 0, "no_entity": 0, "suspect": 0}

    for film in films:
        record = resolved.get(film["imdb_id"])
        if not record:
            stats["no_entity"] += 1
            if progress:
                progress(f"[yellow]no Wikidata entity[/] {film['title']} ({film['imdb_id']})")
            continue

        labels = {_comparable(l) for l in record["labels"]}
        title = _comparable(film["title"])
        title_ok = not labels or any(title == l or title in l or l in title for l in labels)
        years = record["years"]
        year_ok = not years or film.get("year") is None or min(
            abs(y - film["year"]) for y in years) <= 1
        if not (title_ok and year_ok):
            stats["suspect"] += 1
            if progress:
                progress(
                    f"[red]WRONG ID[/] {film['title']} ({film.get('year')}) carries "
                    f"{film['imdb_id']}, which Wikidata says is "
                    f"{sorted(record['labels'])[:1]} {sorted(years)[:1]}"
                )
            continue

        article = record["article"]
        if not article:
            stats["no_article"] += 1
            continue
        if (film.get("wikipedia_title") or "") == article:
            stats["unchanged"] += 1
            continue
        with db.connect() as con:
            con.execute("UPDATE films SET wikipedia_title=? WHERE film_id=?",
                        [article, film["film_id"]])
        stats["stored"] += 1
    return stats


def backfill_plots(force: bool = False, limit: int | None = None,
                   workers: int = 4, progress=None) -> dict[str, int]:
    """Fetch the Wikipedia layers for films already in the corpus without them.

    The 520 films that arrived through the subtitles-only sweep were never sent
    to Wikipedia at all: `bulk_ingest` writes the layers for the films IT adds,
    and those rows came in another way. So the corpus holds six hundred films
    and 157 plot sections, and the product's blind story pairs — which need a
    short description written from something — had only the fifty hand-written
    ones to draw on.

    Only the evidence rows and `wikipedia_title` are written. `upsert_film` is
    deliberately avoided: it is INSERT OR REPLACE over every column, and these
    rows carry metadata (imdb ids, artwork, MovieLens joins) that a partial row
    would erase.
    """
    db.init_db()
    stats = {"fetched": 0, "no_plot": 0, "not_found": 0, "skipped": 0,
             "failed": 0, "unresolved": 0}
    films = db.list_films()
    todo = []
    for film in films:
        has_plot = bool((db.get_evidence(film["film_id"]).get("plot") or "").strip())
        if has_plot and not force:
            stats["skipped"] += 1
            continue
        # No article, no fetch. `fetch` would fall back to a title search, which
        # is how Carlos (2010) came to hold Marmaduke's plot: a search returns a
        # confident answer whether or not it is the right film, and the mistake
        # is then indistinguishable from data. `resolve_articles` supplies the
        # article from the identifier, or says why it cannot.
        if not (film.get("wikipedia_title") or "").strip():
            stats["unresolved"] += 1
            if progress:
                progress(f"[yellow]no resolved article[/] {film['title']} "
                         f"({film.get('year')}) — run `atlas resolve-articles`")
            continue
        todo.append(film)
    if limit:
        todo = todo[:limit]

    # Fetched in parallel, written serially. The plaintext extract of a long
    # article takes Wikipedia ten to fifteen seconds to generate — Titanic is
    # 89,000 characters — so a serial sweep of six hundred films is an hour of
    # waiting on a service that is not remotely busy. `_polite_wait` still
    # spaces the requests globally, so this is four workers taking turns rather
    # than four times the load.
    def store(film: dict[str, Any], wiki: dict[str, Any]) -> None:
        if not wiki.get("found"):
            stats["not_found"] += 1
            if progress:
                progress(f"[dim]no article[/] {film['title']} ({film.get('year')})")
            return

        wrote = False
        for layer in ("plot", "themes", "reception"):
            content = (wiki.get(layer) or "").strip()
            if content:
                db.upsert_evidence(film["film_id"], layer, content, wiki.get("url"))
                wrote = wrote or layer == "plot"
        with db.connect() as con:
            con.execute("UPDATE films SET wikipedia_title=? WHERE film_id=?",
                        [wiki.get("article"), film["film_id"]])

        if wrote:
            stats["fetched"] += 1
        else:
            stats["no_plot"] += 1
            if progress:
                progress(f"[dim]no plot section[/] {film['title']} -> {wiki.get('article')}")
        if progress and (stats["fetched"] + stats["no_plot"]) % 25 == 0:
            progress(f"  {stats['fetched']} plots, {stats['no_plot']} without one, "
                     f"{stats['not_found']} no article")

    # Fetched in parallel, written as each lands. The plaintext extract of a
    # long article takes Wikipedia ten to fifteen seconds to generate — Titanic
    # is 89,000 characters — so a serial sweep of six hundred films is an hour
    # of waiting on a service that is not remotely busy. `_polite_wait` still
    # spaces the requests globally, so this is four workers taking turns rather
    # than four times the load. Writing inside the loop rather than after it
    # keeps the sweep resumable: an interrupted run has banked everything it
    # fetched, and the next run skips those films.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, f["title"], f.get("year"), f.get("wikipedia_title")): f
                   for f in todo}
        for future in as_completed(futures):
            film = futures[future]
            try:
                store(film, future.result())
            except Exception as error:  # noqa: BLE001 — one bad article must not end the sweep
                stats["failed"] += 1
                if progress:
                    progress(f"[red]FAILED[/] {film['title']}: {type(error).__name__}: {error}")
    return stats
