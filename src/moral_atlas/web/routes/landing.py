"""The landing page at `/`.

Two doors and a window. The doors are the product frontend and the data
explorers; the window is a live read of what the pipeline has actually produced,
because the first question anyone asks on opening this box is "did the run
finish, and what is in there now?"

The page is deliberately a single self-contained document with no build step and
no assets: it has to work on a bare EC2 box reached through an SSM tunnel, where
nothing is served but this API. It reads through the same store as everything
else and degrades to zeroes rather than a 500 when the pipeline has not been run
yet, since a fresh clone hits `/` before it has a database.
"""
from __future__ import annotations

import sqlite3
from html import escape
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ... import db
from ...config import settings

router = APIRouter(tags=["landing"])

# The evidence conditions, in the order the A/B reads them: cheapest first.
VARIANTS = ("spine", "spine_themes", "subs", "full")


def _scalar(con: sqlite3.Connection, sql: str, args: list[Any] | None = None) -> int:
    try:
        row = con.execute(sql, args or []).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0            # table not created yet — a fresh clone, not a fault


def _snapshot() -> dict[str, Any]:
    """What the store holds right now. Never raises: `/` must always render."""
    out: dict[str, Any] = {
        "films": 0, "evidence": 0, "skeletons": 0, "propositions": 0,
        "bank_items": 0, "scores": 0, "dimensions": [], "variants": [],
        "ready": False,
    }
    if not settings().db_path.exists():
        return out
    try:
        with db.connect(read_only=True) as con:
            out["films"] = _scalar(con, "SELECT COUNT(*) FROM films")
            out["evidence"] = _scalar(con, "SELECT COUNT(*) FROM evidence")
            out["skeletons"] = _scalar(con, "SELECT COUNT(*) FROM skeletons")
            out["propositions"] = _scalar(con, "SELECT COUNT(*) FROM propositions_raw")
            out["bank_items"] = _scalar(con, "SELECT COUNT(*) FROM item_bank WHERE active=1")
            out["scores"] = _scalar(con, "SELECT COUNT(*) FROM scores")
            out["ready"] = out["films"] > 0

            try:
                rows = con.execute(
                    "SELECT d.name, COUNT(i.item_id) n FROM dimensions d "
                    "LEFT JOIN item_dimensions i "
                    "  ON i.dim_version = d.dim_version AND i.dim_id = d.dim_id "
                    " AND i.pass_name = 'main' "
                    "GROUP BY d.dim_version, d.dim_id, d.name ORDER BY n DESC"
                ).fetchall()
                out["dimensions"] = [(r[0], int(r[1] or 0)) for r in rows]
            except sqlite3.Error:
                pass

            for variant in VARIANTS:
                films = _scalar(
                    con, "SELECT COUNT(DISTINCT film_id) FROM scores WHERE variant=?",
                    [variant],
                )
                if films:
                    out["variants"].append((variant, films))
    except sqlite3.Error:
        pass
    return out


def _stat(label: str, value: int, note: str) -> str:
    return (
        f'<div class="stat"><b>{value:,}</b>'
        f'<span>{escape(label)}</span><small>{escape(note)}</small></div>'
    )


def _bars(dimensions: list[tuple[str, int]]) -> str:
    if not dimensions:
        return (
            '<p class="empty">No dimension set yet — run '
            '<code>atlas dimensions</code>, then <code>atlas dimensions-validate</code> '
            'to see whether the axes survive their audit.</p>'
        )
    widest = max(n for _name, n in dimensions) or 1
    rows = "".join(
        f'<div class="bar"><span>{escape(name)}</span>'
        f'<i style="--w:{100 * n / widest:.1f}%"></i><small>{n}</small></div>'
        for name, n in dimensions
    )
    return f'<div class="bars">{rows}</div>'


def _coverage(variants: list[tuple[str, int]], films: int) -> str:
    if not variants:
        return (
            '<p class="empty">Nothing scored yet — the A/B needs at least two '
            'evidence conditions.</p>'
        )
    total = films or 1
    rows = "".join(
        f'<div class="bar"><span>{escape(v)}</span>'
        f'<i style="--w:{100 * n / total:.1f}%"></i><small>{n}/{films}</small></div>'
        for v, n in variants
    )
    return f'<div class="bars">{rows}</div>'


PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Moral Atlas</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; padding: 64px 24px 80px;
    color: #f5efe6; background: #171310;
    background-image: radial-gradient(80% 55% at 50% 0%, #2a211b 0%, #171310 72%);
    font-family: Inter, ui-sans-serif, system-ui, sans-serif; line-height: 1.5;
  }}
  .wrap {{ max-width: 880px; margin: 0 auto; }}
  .brand {{
    display: flex; align-items: center; gap: 8px; color: #b3aa9e;
    font-size: 12px; font-weight: 650; letter-spacing: .22em; text-transform: uppercase;
  }}
  .brand span {{ color: #eda36b; font-size: 22px; line-height: 1; }}
  h1 {{
    margin: 22px 0 0; font-family: Georgia, 'Times New Roman', serif;
    font-size: clamp(38px, 7vw, 60px); font-weight: 400; line-height: 1.04;
    letter-spacing: -.02em;
  }}
  h1 em {{ color: #eda36b; font-style: italic; }}
  .lede {{ max-width: 46em; margin: 16px 0 0; color: #b3aa9e; font-size: 16px; }}
  h2 {{
    margin: 0 0 14px; color: #7e766c; font-size: 11px; font-weight: 650;
    letter-spacing: .14em; text-transform: uppercase;
  }}
  section {{ margin-top: 52px; }}
  .doors {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
  a.door {{
    display: flex; flex-direction: column; gap: 8px; padding: 24px;
    border: 1px solid #2d251f; border-radius: 16px; background: #1c1713;
    color: inherit; text-decoration: none; transition: border-color .15s, background .15s;
  }}
  a.door:hover, a.door:focus-visible {{ border-color: #eda36b; background: #241d18; }}
  a.door strong {{ font-family: Georgia, serif; font-size: 26px; font-weight: 400; }}
  a.door p {{ margin: 0; color: #b3aa9e; font-size: 14px; }}
  a.door u {{ color: #eda36b; font-size: 12px; text-decoration: none; word-break: break-all; }}
  .stats {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }}
  .stat {{
    display: flex; flex-direction: column; gap: 2px; padding: 16px;
    border: 1px solid #2d251f; border-radius: 12px; background: #1c1713;
  }}
  .stat b {{ color: #f5efe6; font-size: 26px; font-weight: 500; font-variant-numeric: tabular-nums; }}
  .stat span {{ color: #b3aa9e; font-size: 13px; }}
  .stat small {{ color: #7e766c; font-size: 11px; }}
  .bars {{ display: grid; gap: 10px; }}
  .bar {{ display: grid; grid-template-columns: minmax(120px, 15em) 1fr auto; gap: 12px; align-items: center; }}
  .bar span {{ color: #f5efe6; font-size: 13px; }}
  .bar i {{ height: 8px; border-radius: 4px; background: #2d251f; }}
  .bar i::after {{
    display: block; width: var(--w); height: 8px; border-radius: 4px;
    background: linear-gradient(90deg, #eda36b, #f5b580); content: '';
  }}
  .bar small {{ color: #7e766c; font-size: 12px; font-variant-numeric: tabular-nums; }}
  .empty {{ margin: 0; color: #7e766c; font-size: 14px; }}
  code {{ color: #eda36b; font-size: 13px; }}
  footer {{ margin-top: 56px; color: #7e766c; font-size: 12px; }}
  footer a {{ color: #b3aa9e; }}
  @media (prefers-reduced-motion: reduce) {{ a.door {{ transition: none; }} }}
</style>
</head><body><div class="wrap">

<div class="brand"><span>&#9678;</span> Moral Atlas</div>
<h1>What a film <em>believes</em>,<br>measured rather than argued about.</h1>
<p class="lede">Forty films, read for the moral positions they actually take, scored
against a fixed bank of propositions under four different evidence conditions.
This page is the way in.</p>

<section>
  <h2>Two doors</h2>
  <div class="doors">
    <a class="door" href="{frontend_url}">
      <strong>The app</strong>
      <p>The matching flow — answer the questions, then find a film two people
      can agree on.</p>
      <u>{frontend_label}</u>
    </a>
    <a class="door" href="{datasette_url}">
      <strong>The data</strong>
      <p>Datasette over the atlas store: browse, query, facet and chart every
      derived layer, read-only.</p>
      <u>{datasette_label}</u>
    </a>
  </div>
</section>

<section>
  <h2>In the store right now</h2>
  <div class="stats">
    {stats}
  </div>
</section>

<section>
  <h2>Moral dimensions &mdash; items per axis</h2>
  {bars}
</section>

<section>
  <h2>Scoring coverage by evidence condition</h2>
  {coverage}
</section>

<footer>
  <a href="/docs">API reference</a> &middot;
  <a href="{sqliteweb_url}">SQLite admin</a> &middot;
  <a href="/health">health</a>
  <br><br>
  Admin UIs bind to localhost on the deployed box and are reached over an SSM
  tunnel. Point this page elsewhere with <code>ATLAS_FRONTEND_URL</code>,
  <code>ATLAS_DATASETTE_URL</code> and <code>ATLAS_SQLITEWEB_URL</code>.
</footer>

</div></body></html>"""


def _label(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").rstrip("/")


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing() -> HTMLResponse:
    s = settings()
    snap = _snapshot()

    stats = "".join([
        _stat("films", snap["films"], "seed corpus"),
        _stat("evidence layers", snap["evidence"], "plot, themes, reception, subs"),
        _stat("skeletons", snap["skeletons"], "film x condition"),
        _stat("propositions", snap["propositions"], "raw harvested pool"),
        _stat("bank items", snap["bank_items"], "active, after the prune"),
        _stat("scores", snap["scores"], "film x item x condition"),
    ])

    return HTMLResponse(PAGE.format(
        frontend_url=escape(s.frontend_url, quote=True),
        frontend_label=escape(_label(s.frontend_url)),
        datasette_url=escape(s.datasette_url, quote=True),
        datasette_label=escape(_label(s.datasette_url)),
        sqliteweb_url=escape(s.sqliteweb_url, quote=True),
        stats=stats,
        bars=_bars(snap["dimensions"]),
        coverage=_coverage(snap["variants"], snap["films"]),
    ))
