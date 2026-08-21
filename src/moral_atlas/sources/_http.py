"""Shared HTTP client with an on-disk cache.

Fetches are cached by URL+params hash so re-running ingestion is free and does
not re-hammer anyone's API. Delete data/cache to force a refetch.
"""
from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import USER_AGENT, settings


def _cache_path(kind: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    d = settings().cache_dir / kind
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{digest}.json"


def cached_get(
    kind: str,
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    as_text: bool = False,
    ttl_days: int | None = None,
) -> Any:
    key = f"{url}?{json.dumps(params or {}, sort_keys=True)}"
    path = _cache_path(kind, key)

    if path.exists():
        if ttl_days is None or (time.time() - path.stat().st_mtime) < ttl_days * 86400:
            payload = json.loads(path.read_text())
            return payload["body"]

    body = _fetch_with_retry(url, params, headers, as_text)

    path.write_text(json.dumps({"url": url, "params": params, "body": body}))
    return body


# Public APIs throttle bursts. Ingesting 40 films is ~80 requests in a tight
# loop, which is enough for Wikipedia to start returning 429 — and a swallowed
# 429 looks exactly like "this film has no plot section", which is the most
# misleading failure mode available to us.
_THROTTLE = threading.Lock()
_last_call = [0.0]
MIN_INTERVAL = 0.35


def _polite_wait() -> None:
    with _THROTTLE:
        gap = time.monotonic() - _last_call[0]
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        _last_call[0] = time.monotonic()


def _fetch_with_retry(
    url: str,
    params: dict[str, Any] | None,
    headers: dict[str, str] | None,
    as_text: bool,
    tries: int = 5,
) -> Any:
    h = {"User-Agent": USER_AGENT, **(headers or {})}
    last: Exception | None = None

    for attempt in range(tries):
        _polite_wait()
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                resp = client.get(url, params=params, headers=h)
            if resp.status_code in (429, 503):
                delay = float(resp.headers.get("Retry-After", 0)) or (2 ** attempt)
                time.sleep(min(30.0, delay + random.random()))
                last = httpx.HTTPStatusError(
                    f"{resp.status_code} throttled", request=resp.request, response=resp
                )
                continue
            resp.raise_for_status()
            return resp.text if as_text else resp.json()
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            last = e
            time.sleep(min(20.0, (2 ** attempt) + random.random()))

    raise RuntimeError(f"request failed after {tries} attempts: {url} — {last}") from last
