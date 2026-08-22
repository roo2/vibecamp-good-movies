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
    db_path: Path = ROOT / "data" / "atlas.sqlite"

    anthropic_api_key: str | None = _clean("ANTHROPIC_API_KEY")
    # Alternative scorers, for auditing whose morals the scores encode. Each is
    # optional: absent means that model sits the comparison out, not that the
    # pipeline breaks.
    xai_api_key: str | None = _clean("XAI_API_KEY")
    deepseek_api_key: str | None = _clean("DEEPSEEK_API_KEY")
    openrouter_api_key: str | None = _clean("OPENROUTER_API_KEY")
    tmdb_read_token: str | None = _clean("TMDB_READ_TOKEN")
    tmdb_api_key: str | None = _clean("TMDB_API_KEY")
    opensubtitles_key: str | None = _clean("OPENSUBTITLES_API_KEY")
    opensubtitles_user: str | None = _clean("OPENSUBTITLES_USERNAME")
    opensubtitles_password: str | None = _clean("OPENSUBTITLES_PASSWORD")
    subtitles_dir: str | None = _clean("SUBTITLES_DIR")

    # `.env.example` has described Sonnet as the default for some time while this
    # line still said Opus, so a checkout without ATLAS_MODEL set quietly ran the
    # expensive model. Now that every derived row records the model that produced
    # it, that kind of drift shows up in `atlas provenance` instead of in a bill.
    model: str = os.environ.get("ATLAS_MODEL", "claude-sonnet-5")
    effort: str = os.environ.get("ATLAS_EFFORT", "high")
    concurrency: int = int(os.environ.get("ATLAS_CONCURRENCY", "6"))

    # Where the landing page at `/` sends people. The defaults are the local dev
    # ports. On the deployed box the admin UIs are bound to 127.0.0.1 and reached
    # over an SSM tunnel, so the operator sets these rather than the page
    # guessing at a hostname it cannot know.
    frontend_url: str = os.environ.get("ATLAS_FRONTEND_URL", "http://localhost:5173")
    datasette_url: str = os.environ.get("ATLAS_DATASETTE_URL", "http://localhost:8001")
    sqliteweb_url: str = os.environ.get("ATLAS_SQLITEWEB_URL", "http://localhost:8002")

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
    # Alternative scorers. Published list prices at time of writing; they move,
    # and the cost line in the CLI is an estimate rather than an invoice.
    "grok-4": (3.00, 15.00),
    "grok-3": (3.00, 15.00),
    "deepseek-chat": (0.28, 0.42),
    "deepseek-reasoner": (0.55, 2.19),
    # Read off the OpenRouter catalogue rather than remembered.
    "nousresearch/hermes-4-405b": (1.00, 3.00),
    "nousresearch/hermes-3-llama-3.1-405b": (1.00, 1.00),
    "cognitivecomputations/dolphin-mistral-24b-venice-edition": (0.20, 0.90),
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
