"""Subtitle tracks — the primary text.

Chosen over screenplays for one decisive reason: subtitles are transcribed from
the finished film, whereas most circulating screenplays are shooting drafts or
earlier. Endings get rewritten in the edit, and the ending is where most moral
propositions are actually settled — so a draft script is wrong precisely where
it matters most.

Timestamps are the second reason. They give act position for free, so the
closing slice can be extracted with real confidence, along with the final line
of spoken dialogue — which in a surprising number of films is the thesis stated
outright.

SDH / closed-caption tracks are preferred: they carry speaker labels and
non-dialogue cues that plain tracks drop, and speaker attribution matters a
great deal for working out whose interiority the film grants.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..config import USER_AGENT, settings
from ._http import cached_get

API = "https://api.opensubtitles.com/api/v1"

TIMECODE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
TAG = re.compile(r"<[^>]+>|\{[^}]*\}")


@dataclass
class Cue:
    start_ms: int
    text: str


def _ms(h: str, m: str, s: str, frac: str) -> int:
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(frac.ljust(3, "0"))


def parse_srt(raw: str) -> list[Cue]:
    """Parse SRT/VTT into timed cues, dropping markup and index lines."""
    raw = raw.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        start = None
        body: list[str] = []
        for line in lines:
            m = TIMECODE.search(line)
            if m:
                start = _ms(*m.groups()[:4])
                continue
            if line.strip().isdigit() and start is None and not body:
                continue  # subtitle index
            if line.strip().upper().startswith(("WEBVTT", "NOTE ")):
                continue
            body.append(TAG.sub("", line).strip())
        text = " ".join(b for b in body if b).strip()
        if start is not None and text:
            cues.append(Cue(start, text))
    return cues


RENDERED = re.compile(r"^\[(\d+):(\d{2}):(\d{2})\]\s*(.*)$")


def parse_rendered(text: str) -> list[Cue]:
    """Read back the '[h:mm:ss] line' form we store in the evidence table.

    Evidence is stored rendered rather than as raw SRT, so anything that wants
    to slice by act position has to parse our own format, not SRT.
    """
    cues = []
    for line in text.splitlines():
        m = RENDERED.match(line.strip())
        if m:
            h, mm, ss, body = m.groups()
            if body.strip():
                cues.append(Cue((int(h) * 3600 + int(mm) * 60 + int(ss)) * 1000,
                                body.strip()))
    return cues


def parse_any(text: str) -> list[Cue]:
    """Parse either raw SRT/VTT or our rendered form."""
    return parse_srt(text) if "-->" in text else parse_rendered(text)


def cues_to_text(cues: list[Cue], with_timestamps: bool = True) -> str:
    """Render cues as text. Timestamps are kept so the model can reason about
    act position without us having to describe it."""
    out = []
    for c in cues:
        if with_timestamps:
            mm, ss = divmod(c.start_ms // 1000, 60)
            hh, mm = divmod(mm, 60)
            out.append(f"[{hh:d}:{mm:02d}:{ss:02d}] {c.text}")
        else:
            out.append(c.text)
    return "\n".join(out)


def slice_by_position(cues: list[Cue], start_frac: float, end_frac: float) -> list[Cue]:
    """Slice cues by fractional position through the runtime."""
    if not cues:
        return []
    span = cues[-1].start_ms or 1
    lo, hi = span * start_frac, span * end_frac
    return [c for c in cues if lo <= c.start_ms <= hi]


def final_lines(cues: list[Cue], n: int = 12) -> str:
    return "\n".join(c.text for c in cues[-n:])


# --------------------------------------------------------------------------
# Acquisition
# --------------------------------------------------------------------------

def from_local_dir(film_id: str, title: str, year: int | None) -> str | None:
    """Look for a hand-supplied track in SUBTITLES_DIR.

    Lets you run the full pipeline on the phase-0 films without an OpenSubtitles
    account at all — drop in 40 .srt files and everything downstream works.
    """
    d = settings().subtitles_dir
    if not d:
        return None
    folder = Path(d).expanduser()
    if not folder.is_dir():
        return None

    candidates = [
        f"{film_id}.srt", f"{film_id}.vtt",
        f"{title}.srt", f"{title} ({year}).srt" if year else "",
    ]
    for name in filter(None, candidates):
        p = folder / name
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")

    # Loose match: normalised title appears in the filename.
    norm = re.sub(r"[^a-z0-9]", "", title.lower())
    for p in folder.iterdir():
        if p.suffix.lower() in {".srt", ".vtt"}:
            if norm and norm in re.sub(r"[^a-z0-9]", "", p.stem.lower()):
                return p.read_text(encoding="utf-8", errors="replace")
    return None


def search_opensubtitles(imdb_id: str | None, tmdb_id: int | None,
                         language: str = "en") -> list[dict[str, Any]]:
    """Search, ranked so SDH tracks and well-downloaded tracks come first."""
    s = settings()
    if not s.opensubtitles_key:
        return []

    params: dict[str, Any] = {"languages": language, "order_by": "download_count",
                              "order_direction": "desc"}
    if imdb_id:
        params["imdb_id"] = imdb_id.removeprefix("tt")
    elif tmdb_id:
        params["tmdb_id"] = tmdb_id
    else:
        return []

    data = cached_get(
        "opensub", f"{API}/subtitles", params,
        {"Api-Key": s.opensubtitles_key, "Accept": "application/json"},
    )
    results = data.get("data", []) or []
    # SDH first: speaker labels and sound cues are worth more than raw popularity.
    results.sort(
        key=lambda r: (
            not r.get("attributes", {}).get("hearing_impaired", False),
            -(r.get("attributes", {}).get("download_count") or 0),
        )
    )
    return results


def _login_token() -> str | None:
    s = settings()
    if not s.can_download_subtitles:
        return None
    with httpx.Client(timeout=45.0) as client:
        r = client.post(
            f"{API}/login",
            json={"username": s.opensubtitles_user, "password": s.opensubtitles_password},
            headers={"Api-Key": s.opensubtitles_key, "User-Agent": USER_AGENT,
                     "Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json().get("token")


def download_opensubtitles(file_id: int) -> str | None:
    """Download one subtitle file. Requires a login as well as the API key."""
    s = settings()
    token = _login_token()
    if not token:
        return None
    headers = {
        "Api-Key": s.opensubtitles_key, "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT, "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        r = client.post(f"{API}/download", json={"file_id": file_id}, headers=headers)
        r.raise_for_status()
        link = r.json().get("link")
        if not link:
            return None
        return client.get(link).text


def acquire(
    film_id: str, title: str, year: int | None,
    imdb_id: str | None, tmdb_id: int | None, runtime: int | None = None,
) -> tuple[list[Cue], dict[str, Any]]:
    """Get a track as timed cues, trying sources in order of preference.

    1. SUBTITLES_DIR — a hand-supplied file always wins. It is the only source
       that can carry SDH speaker labels, so it beats whatever a bulk archive
       or an API ranking picks.
    2. OPUS — no account, no daily limit, ~80 KB per film via ranged requests
       into the research archive. This is the one that scales to 2,000 films.
    3. OpenSubtitles API — 20 downloads/day on a free account. Reserved for the
       gaps: films newer than the archive release, and anything OPUS lacks.
    """
    local = from_local_dir(film_id, title, year)
    if local:
        return parse_any(local), {"source": "local", "sdh": None}

    if imdb_id:
        try:
            from . import opus
            cues, meta = opus.fetch_cues(imdb_id, runtime=runtime)
            if cues:
                return [Cue(ms, text) for ms, text in cues], meta
            opus_reason = meta.get("reason")
        except Exception as e:  # noqa: BLE001
            opus_reason = f"opus error: {e}"
    else:
        opus_reason = "no imdb id, cannot look up OPUS"

    results = search_opensubtitles(imdb_id, tmdb_id)
    if not results:
        return [], {"source": None, "reason": opus_reason}

    top = results[0]
    files = top.get("attributes", {}).get("files", [])
    if not files:
        return [], {"source": None, "reason": "opensubtitles result had no files"}

    raw = download_opensubtitles(files[0]["file_id"])
    if not raw:
        return [], {
            "source": None,
            "reason": f"{opus_reason}; opensubtitles download needs "
                      f"OPENSUBTITLES_USERNAME/PASSWORD",
        }
    return parse_any(raw), {
        "source": "opensubtitles",
        "sdh": top["attributes"].get("hearing_impaired"),
        "release": top["attributes"].get("release"),
    }
