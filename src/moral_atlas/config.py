"""Runtime settings, resolved from the environment / .env once at import."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# Every derived row is stamped with the prompt version that produced it, so a
# rubric change never silently overwrites an earlier run's numbers.
PROMPT_VERSION = "p1"

USER_AGENT = "moral-atlas/0.1 (research; contact via repository owner)"


def _clean(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or None


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    cache_dir: Path = ROOT / "data" / "cache"
    db_path: Path = ROOT / "data" / "atlas.duckdb"

    anthropic_api_key: str | None = _clean("ANTHROPIC_API_KEY")
    tmdb_read_token: str | None = _clean("TMDB_READ_TOKEN")
    tmdb_api_key: str | None = _clean("TMDB_API_KEY")
    opensubtitles_key: str | None = _clean("OPENSUBTITLES_API_KEY")
    opensubtitles_user: str | None = _clean("OPENSUBTITLES_USERNAME")
    opensubtitles_password: str | None = _clean("OPENSUBTITLES_PASSWORD")
    subtitles_dir: str | None = _clean("SUBTITLES_DIR")

    model: str = os.environ.get("ATLAS_MODEL", "claude-opus-5")
    effort: str = os.environ.get("ATLAS_EFFORT", "high")
    concurrency: int = int(os.environ.get("ATLAS_CONCURRENCY", "6"))

    @property
    def has_tmdb(self) -> bool:
        return bool(self.tmdb_read_token or self.tmdb_api_key)

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_opensubtitles(self) -> bool:
        return bool(self.opensubtitles_key)

    @property
    def can_download_subtitles(self) -> bool:
        return bool(
            self.opensubtitles_key
            and self.opensubtitles_user
            and self.opensubtitles_password
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


# Per-million-token prices, for the running cost estimate the CLI prints.
PRICES = {
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def estimate_cost(model: str, inp: int, out: int, cache_read: int = 0) -> float:
    """Rough USD cost. Cached reads bill at ~10% of the input rate."""
    price_in, price_out = PRICES.get(model, (5.00, 25.00))
    fresh_in = max(0, inp - cache_read)
    return (
        fresh_in * price_in / 1_000_000
        + cache_read * price_in * 0.1 / 1_000_000
        + out * price_out / 1_000_000
    )
