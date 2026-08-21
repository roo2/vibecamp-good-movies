"""OPUS OpenSubtitles — bulk subtitle acquisition without rate limits.

The OpenSubtitles REST API allows 5 downloads/day anonymously and 20/day with a
free account, which is two days of waiting for a 40-film pilot and roughly three
months for a 2,000-film sweep. A VIP subscription lifts that to ~1,000/day, but
there is a better option for research use.

The OPUS project (Helsinki NLP) republishes the whole OpenSubtitles collection
as a citable research corpus: 446k English tracks across 140k IMDb ids in the
v2018 release, more in v2024. It is a single very large zip — 13.7 GB for v2018,
35.8 GB for v2024 — which sounds prohibitive until you notice the host supports
HTTP range requests.

So we never download the archive. We fetch its Zip64 central directory once
(~70 MB), build a local index of IMDb id -> byte offset, and then pull
individual entries with two ranged requests each: ~80 KB per film instead of
13.7 GB, with no daily limit and no account.

Trade-off worth knowing: OPUS has stripped SDH speaker labels. Dash-prefixed
two-speaker cues survive (275 of them in The Lion King) so turn-taking is still
visible, but "[MUFASA]" style attribution is gone. Where knowing who spoke
actually matters, prefer a hand-supplied SDH track in SUBTITLES_DIR.

Cite: P. Lison and J. Tiedemann (2016), "OpenSubtitles2016: Extracting Large
Parallel Corpora from Movie and TV Subtitles", LREC.
"""
from __future__ import annotations

import pickle
import re
import struct
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import httpx

from ..config import USER_AGENT, settings

BASE = "https://object.pouta.csc.fi/OPUS-OpenSubtitles"
DEFAULT_VERSION = "v2024"
# Tried in order. v2024 has the wider and more recent coverage and retains more
# SDH markers; v2018 still holds some tracks that were dropped from the later
# release, so it is worth a second look before falling back to the rate-limited
# API. Neither covers films released after its cut-off.
VERSION_CHAIN = ("v2024", "v2018")

# Central-directory file header, from byte 10 to byte 46.
_CD_FMT = "<H4xIIIHHHHHII"
_ZIP64_SENTINEL_32 = 0xFFFFFFFF


@dataclass(frozen=True)
class Entry:
    path: str
    offset: int          # local file header offset
    csize: int
    usize: int
    method: int          # 0 stored, 8 deflate

    @property
    def year(self) -> str:
        parts = self.path.split("/")
        return parts[3] if len(parts) > 4 else ""


def archive_url(version: str = DEFAULT_VERSION, lang: str = "en") -> str:
    return f"{BASE}/{version}/raw/{lang}.zip"


def index_path(version: str, lang: str) -> Path:
    return settings().cache_dir / "opus" / f"index-{version}-{lang}.pkl"


# --------------------------------------------------------------------------
# Index construction
# --------------------------------------------------------------------------

def _archive_size(url: str) -> int:
    with httpx.Client(timeout=60, follow_redirects=True) as c:
        r = c.head(url, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        return int(r.headers["content-length"])


def _get_range(url: str, start: int, end: int, client: httpx.Client | None = None) -> bytes:
    headers = {"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end}"}
    if client is not None:
        r = client.get(url, headers=headers)
    else:
        with httpx.Client(timeout=180, follow_redirects=True) as c:
            r = c.get(url, headers=headers)
    r.raise_for_status()
    return r.content


def _locate_central_directory(url: str, size: int) -> tuple[int, int, int]:
    """Find the central directory via the Zip64 end-of-central-directory record.

    These archives exceed 4 GB, so the classic EOCD carries 0xFFFFFFFF
    sentinels and the real offsets live in the Zip64 record behind it. A reader
    that only understands the 32-bit EOCD reports 'not a zip file'.
    """
    tail = _get_range(url, max(0, size - 65536), size - 1)
    j = tail.rfind(b"PK\x06\x06")
    if j >= 0:
        vals = struct.unpack("<QHHIIQQQQ", tail[j + 4:j + 56])
        return vals[8], vals[7], vals[6]        # offset, size, n_entries

    i = tail.rfind(b"PK\x05\x06")
    if i < 0:
        raise RuntimeError(f"no end-of-central-directory record found in {url}")
    _, _, _, n_total, cd_size, cd_off, _ = struct.unpack("<HHHHIIH", tail[i + 4:i + 22])
    return cd_off, cd_size, n_total


def _iter_central_directory(data: bytes) -> Iterator[Entry]:
    i, n = 0, len(data)
    while i + 46 <= n:
        if data[i:i + 4] != b"PK\x01\x02":
            i += 1
            continue
        (method, _crc, csize, usize, fn_len, ex_len, cm_len,
         _disk, _ia, _ea, offset) = struct.unpack(_CD_FMT, data[i + 10:i + 46])
        name = data[i + 46:i + 46 + fn_len].decode("utf-8", "replace")
        extra = data[i + 46 + fn_len:i + 46 + fn_len + ex_len]

        if _ZIP64_SENTINEL_32 in (csize, usize, offset):
            j = 0
            while j + 4 <= len(extra):
                hid, hsz = struct.unpack("<HH", extra[j:j + 4])
                body, k = extra[j + 4:j + 4 + hsz], 0
                if hid == 1:
                    if usize == _ZIP64_SENTINEL_32:
                        usize = struct.unpack("<Q", body[k:k + 8])[0]; k += 8
                    if csize == _ZIP64_SENTINEL_32:
                        csize = struct.unpack("<Q", body[k:k + 8])[0]; k += 8
                    if offset == _ZIP64_SENTINEL_32:
                        offset = struct.unpack("<Q", body[k:k + 8])[0]; k += 8
                j += 4 + hsz

        if name.endswith(".xml"):
            yield Entry(name, offset, csize, usize, method)
        i += 46 + fn_len + ex_len + cm_len


def build_index(
    version: str = DEFAULT_VERSION, lang: str = "en",
    force: bool = False, progress=None,
) -> dict[str, list[Entry]]:
    """Fetch and parse the archive's central directory into a local index.

    One-off cost of a ~70-180 MB ranged download. Everything afterwards is
    ~80 KB per film.
    """
    path = index_path(version, lang)
    if path.exists() and not force:
        with path.open("rb") as fh:
            return pickle.load(fh)

    url = archive_url(version, lang)
    size = _archive_size(url)
    cd_off, cd_size, n_entries = _locate_central_directory(url, size)
    if progress:
        progress(f"archive {size / 1e9:.1f} GB, {n_entries:,} entries; "
                 f"fetching {cd_size / 1e6:.0f} MB central directory")

    with httpx.Client(timeout=600, follow_redirects=True) as client:
        data = _get_range(url, cd_off, cd_off + cd_size - 1, client)

    index: dict[str, list[Entry]] = {}
    for entry in _iter_central_directory(data):
        parts = entry.path.split("/")
        if len(parts) < 2:
            continue
        index.setdefault(parts[-2], []).append(entry)

    # Order by closeness to the median size for that title. Size alone is a
    # trap: the largest Lion King track is a concatenated dual-language file
    # with 3,132 cues running to 165 minutes for an 88-minute picture, and the
    # smallest are truncated stubs. The median is robust to both.
    for key, entries in index.items():
        sizes = sorted(e.usize for e in entries)
        median = sizes[len(sizes) // 2]
        entries.sort(key=lambda e: abs(e.usize - median))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump(index, fh, protocol=pickle.HIGHEST_PROTOCOL)
    if progress:
        progress(f"indexed {sum(len(v) for v in index.values()):,} tracks "
                 f"across {len(index):,} titles -> {path}")
    return index


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------

def imdb_key(imdb_id: str) -> str:
    """OPUS directory names drop the tt prefix AND leading zeros."""
    return str(int(re.sub(r"\D", "", imdb_id)))


def fetch_entry(entry: Entry, version: str = DEFAULT_VERSION, lang: str = "en") -> bytes:
    """Two ranged requests: local header (for its variable-length fields), then data."""
    url = archive_url(version, lang)
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        header = _get_range(url, entry.offset, entry.offset + 29, client)
        fn_len, ex_len = struct.unpack("<HH", header[26:30])
        start = entry.offset + 30 + fn_len + ex_len
        blob = _get_range(url, start, start + entry.csize - 1, client)
    return zlib.decompress(blob, -15) if entry.method == 8 else blob


def parse_opus_xml(raw: bytes) -> list[tuple[int, str]]:
    """Parse OPUS subtitle XML into (start_ms, text) pairs.

    Each <s> holds its text plus <time> markers. Sentences without their own
    marker inherit the last seen timestamp, which keeps the act-position slicing
    honest rather than dropping those lines.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        root = ET.fromstring(raw.decode("utf-8", "replace"))

    out: list[tuple[int, str]] = []
    last_ms = 0
    for s in root.iter("s"):
        start_ms = None
        for t in s.findall("time"):
            value = t.get("value") or ""
            m = re.match(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})", value)
            if m and (t.get("id") or "").endswith("S"):
                h, mm, ss, frac = m.groups()
                start_ms = (int(h) * 3600 + int(mm) * 60 + int(ss)) * 1000 + int(frac.ljust(3, "0"))
                break
        text = " ".join("".join(s.itertext()).split())
        if not text:
            continue
        last_ms = start_ms if start_ms is not None else last_ms
        out.append((last_ms, text))
    return out


MAX_CANDIDATES = 4


def _plausibility(cues: list[tuple[int, str]], runtime: int | None) -> tuple[bool, str]:
    """Reject tracks that cannot be this film.

    Act-position slicing depends on the timeline being real: a track running to
    165 minutes for an 88-minute film puts the "closing 15%" in the wrong place
    entirely, which quietly corrupts every ending-derived proposition.
    """
    if not cues:
        return False, "no cues"
    duration = cues[-1][0] / 60000
    if not 20 <= duration <= 300:
        return False, f"duration {duration:.0f} min out of range"
    if runtime:
        if not 0.70 * runtime <= duration <= 1.20 * runtime:
            return False, f"duration {duration:.0f} min vs runtime {runtime} min"
        # Density has to scale with length, not sit at a fixed cap. The Wolf of
        # Wall Street is 180 minutes and legitimately carries ~4,370 cues at 24
        # per minute; a flat ceiling of 4,000 rejects it as corrupt.
        per_min = len(cues) / max(duration, 1.0)
        if not 2.0 <= per_min <= 45.0:
            return False, f"{per_min:.0f} cues/min out of range"
    elif not 100 <= len(cues) <= 6000:
        return False, f"{len(cues)} cues out of range"
    return True, ""


def fetch_cues(
    imdb_id: str, version: str | None = None, lang: str = "en",
    runtime: int | None = None,
) -> tuple[list[tuple[int, str]], dict[str, Any]]:
    """Look up a film by IMDb id and return its best track as timed cues.

    With no explicit version, walks VERSION_CHAIN. An index that has not been
    built yet is skipped rather than triggering a surprise 180 MB download in
    the middle of an ingest.
    """
    versions = (version,) if version else VERSION_CHAIN
    tried = []
    key = imdb_key(imdb_id)

    for v in versions:
        if not index_path(v, lang).exists():
            tried.append(f"{v}: not indexed (run `atlas opus-index --version {v}`)")
            continue
        candidates = build_index(v, lang).get(key)
        if not candidates:
            tried.append(f"{v}: no track for imdb {imdb_id}")
            continue

        best: tuple[list[tuple[int, str]], Entry, float] | None = None
        for entry in candidates[:MAX_CANDIDATES]:
            cues = parse_opus_xml(fetch_entry(entry, v, lang))
            ok, why = _plausibility(cues, runtime)
            if not ok:
                tried.append(f"{v}:{entry.path.split('/')[-1]} rejected ({why})")
                continue
            duration = cues[-1][0] / 60000
            gap = abs(duration - runtime) if runtime else 0.0
            if best is None or gap < best[2]:
                best = (cues, entry, gap)
            if not runtime:
                break        # no runtime to discriminate on; first plausible wins

        if best:
            cues, entry, _ = best
            return cues, {
                "source": f"opus/{v}",
                "path": entry.path,
                "candidates": len(candidates),
                "n_cues": len(cues),
                "duration_min": round(cues[-1][0] / 60000, 1),
                "runtime_min": runtime,
            }

    return [], {"source": None, "reason": "; ".join(tried)}
