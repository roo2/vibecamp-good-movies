"""Ingestion: turn a seed entry into a film row plus its evidence layers.

Degrades layer by layer. Wikipedia needs no credential, so the event spine and
the themes/reception layers always work; TMDB and subtitles fill in when their
keys exist. A film with only a plot section is still a usable film — it just
gets a lower completeness score and can only run the `spine` variant.
"""
from __future__ import annotations

import re
from typing import Any, Callable

import yaml

from .. import db
from ..config import settings
from . import subtitles as subs_mod
from . import tmdb as tmdb_mod
from . import wikipedia as wiki_mod


def slugify(title: str, year: int | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{slug}-{year}" if year else slug


def load_seeds(path: str) -> list[dict[str, Any]]:
    with open(path) as fh:
        data = yaml.safe_load(fh)
    return data.get("films", [])


def ingest_one(seed: dict[str, Any], progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    s = settings()
    title, year = seed["title"], seed.get("year")
    report: dict[str, Any] = {"title": title, "year": year, "layers": {}}

    # ---- metadata -------------------------------------------------------
    row: dict[str, Any] = {
        "title": title, "year": year, "seed_note": seed.get("note"),
        "fetched_at": db.now(),
    }
    if s.has_tmdb:
        try:
            hit = tmdb_mod.search(title, year)
            if hit:
                row.update(tmdb_mod.to_film_row(tmdb_mod.details(hit["id"])))
                report["tmdb"] = row.get("tmdb_id")
            else:
                report["tmdb"] = "not found"
        except Exception as e:  # noqa: BLE001
            report["tmdb"] = f"error: {e}"
    else:
        report["tmdb"] = "skipped (no key)"

    film_id = (
        f"tmdb-{row['tmdb_id']}" if row.get("tmdb_id") else slugify(title, year)
    )
    row["film_id"] = film_id
    row.setdefault("title", title)
    row.setdefault("year", year)
    report["film_id"] = film_id

    # ---- Wikipedia ------------------------------------------------------
    try:
        wiki = wiki_mod.fetch(title, year, seed.get("wikipedia"))
        row["wikipedia_title"] = wiki.get("article")
        # OPUS is keyed by IMDb id. Wikidata supplies one with no credential,
        # so the subtitle layer does not depend on having a TMDB account.
        if wiki.get("article"):
            try:
                facts = wiki_mod.wikidata_facts(wiki["article"])
                if not row.get("imdb_id"):
                    row["imdb_id"] = facts.get("imdb_id")
                if not row.get("runtime"):
                    row["runtime"] = facts.get("runtime")
                report["imdb_id"] = row.get("imdb_id")
                report["runtime"] = row.get("runtime")
            except Exception as e:  # noqa: BLE001
                report["imdb_lookup_note"] = str(e)
        db.upsert_film(row)
        for layer in ("plot", "themes", "reception"):
            content = wiki.get(layer) or ""
            if content.strip():
                db.upsert_evidence(film_id, layer, content, wiki.get("url"),
                                   {"article": wiki.get("article")})
                report["layers"][layer] = len(content.split())
            else:
                report["layers"][layer] = 0
        report["article"] = wiki.get("article")
    except Exception as e:  # noqa: BLE001
        db.upsert_film(row)
        report["wikipedia_error"] = str(e)

    # ---- subtitles ------------------------------------------------------
    try:
        cues, meta = subs_mod.acquire(
            film_id, title, year, row.get("imdb_id"), row.get("tmdb_id"),
            runtime=row.get("runtime"),
        )
        if cues:
            db.upsert_evidence(
                film_id, "subtitles", subs_mod.cues_to_text(cues), None,
                {**meta, "n_cues": len(cues),
                 "final_lines": subs_mod.final_lines(cues)},
            )
            report["layers"]["subtitles"] = len(cues)
        else:
            report["layers"]["subtitles"] = 0
            report["subtitles_note"] = meta.get("reason", "unavailable")
    except Exception as e:  # noqa: BLE001
        report["subtitles_error"] = str(e)

    if progress:
        errs = [v for k, v in report.items() if k.endswith("_error")]
        if errs:
            progress(f"[red]FAILED[/] {title[:34]:<30} {errs[0][:90]}")
        else:
            layers = ", ".join(f"{k}:{v}" for k, v in report["layers"].items())
            progress(f"{title[:34]:<36} {film_id:<22} {layers}")
    return report
