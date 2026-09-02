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
PROMPT_VERSION = "p2"

USER_AGENT = "moral-atlas/0.1 (research; contact via repository owner)"


def _clean(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or None


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    cache_dir: Path = ROOT / "data" / "cache"
    # ATLAS_DB points every reader at another store. infra/export-corpus.sh
    # already used that name for the same idea; the Python side did not honour
    # it, so analysing a pulled production snapshot meant copying it over the
    # working database and hoping to remember which one was which.
    db_path: Path = Path(os.environ.get("ATLAS_DB", str(ROOT / "data" / "atlas.sqlite")))
    # Where the MovieLens ml-25m extract sits, and where the arrays derived from
    # it are cached. Both live under data/, which is git-ignored whole: ml-25m is
    # licensed for non-commercial research and may NOT be redistributed, so
    # neither the ratings nor anything holding them verbatim can enter the repo
    # or the corpus export. What ships is only aggregate — a similarity matrix
    # over our own films, and film positions on the derived dimensions.
    movielens_dir: Path = Path(
        os.environ.get("MOVIELENS_DIR", str(ROOT / "data" / "movielens" / "ml-25m")))
    derived_dir: Path = Path(
        os.environ.get("ATLAS_DERIVED_DIR", str(ROOT / "data" / "derived")))

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

    # Which model's discovered axes the PRODUCT reads. The atlas page can show
    # any scorer side by side, but a person taking the test gets one reading of
    # themselves, so one has to be chosen. DeepSeek by default: it is the only
    # model whose pipeline has run end to end, and by a wide margin the cheapest
    # to re-run when the corpus grows.
    product_scorer: str = os.environ.get("ATLAS_PRODUCT_SCORER", "deepseek")
    product_variant: str = os.environ.get("ATLAS_PRODUCT_VARIANT", "subs")
    # Whose PROPOSITIONS the product reads, which stopped being the same
    # question as whose verdicts it reads. Four combinations of two models were
    # measured, and the roles came apart: dolphin writes propositions films
    # actually divide on (40% of its bank against deepseek's 24%), and deepseek
    # answers them far more consistently (three axes replicating at 0.85 across
    # 565 films, against six at 0.66 on its own bank). Neither model is better
    # at both, so the product uses each for the job it is better at.
    #
    # Empty means "the bank this scorer wrote for itself", which is what every
    # call site used to assume.
    product_bank: str = os.environ.get("ATLAS_PRODUCT_BANK", "dolphin-subs")

    # How the moral axes are extracted: "composite" (the shipped default —
    # common factors rotated into orthogonal composites), "fa" (the common
    # factors themselves), or "pca" (principal components, what shipped until
    # 2026-09). Changed on measurement
    # evidence — components' better prediction turned out to be taste, not moral
    # signal: with taste residualised out of both the gap fell from 1.19 points
    # to 0.21, and both landed within a point of chance. See analysis/latent.py.
    #
    # ONE setting because ONE solution is stored. Serving components on one
    # screen and factors on another is the shape of every silently-wrong screen
    # this project has shipped.
    extraction: str = os.environ.get("ATLAS_EXTRACTION", "fa")

    # The most axes any reading is derived at. A CAP, not a count: the
    # permutation null still decides how many a bank supports, and that number
    # is recorded, but the readings are cut to a common ceiling so they can be
    # compared side by side. Without it the same corpus reads as 3 axes through
    # one bank and 8 through another, and a reader has no way to tell whether
    # that is a fact about the models or about how many propositions each bank
    # happens to hold.
    #
    # Supplying a number is the practice this project exists to replace, so the
    # distinction matters: nothing here invents a factor where the null found
    # fewer, and `n_supported` on every report says what the null actually said.
    max_axes: int = int(os.environ.get("ATLAS_MAX_AXES", "3"))
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
    def factor_bank(self) -> str:
        """The bank the product's axes come from. One place, deliberately.

        Three services rebuilt this string themselves as f"{scorer}-{variant}",
        which silently hard-coded the assumption that a model can only read its
        own questions.
        """
        return self.product_bank or f"{self.product_scorer}-{self.product_variant}"

    @property
    def has_movielens(self) -> bool:
        """Whether the ratings the taste and CF layers are built from are here.

        Checked rather than assumed: the download is 250MB and not in the repo,
        so a fresh checkout has everything EXCEPT this, and the failure without
        the check is a stack trace deep inside a CSV read.
        """
        return (self.movielens_dir / "ratings.csv").exists() and \
               (self.movielens_dir / "links.csv").exists()

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
        self.derived_dir.mkdir(parents=True, exist_ok=True)


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
