"""Anthropic client wrapper: caching, bounded concurrency, retry, cost accounting."""
from __future__ import annotations

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, TypeVar

import anthropic
from pydantic import BaseModel

from ..config import estimate_cost, settings

T = TypeVar("T", bound=BaseModel)


# Not every model takes the same request shape. Adaptive thinking and
# output_config.effort are 4.6-and-later features; Haiku 4.5 and earlier use the
# older budget_tokens form and reject both with a 400. Sending the wrong shape
# fails the whole run, so capability is looked up rather than assumed.
ADAPTIVE_THINKING = (
    "claude-fable-5", "claude-mythos-5", "claude-opus-5", "claude-opus-4-8",
    "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-5", "claude-sonnet-4-6",
)


def supports_adaptive(model: str) -> bool:
    return model in ADAPTIVE_THINKING


def supports_effort(model: str) -> bool:
    return model in ADAPTIVE_THINKING or model.startswith("claude-opus-4-5")


class LLMParseError(RuntimeError):
    """A call returned no usable structured output.

    Almost always a token budget problem: with adaptive thinking, reasoning
    tokens are drawn from the same max_tokens pool as the answer, so a heavy
    reasoning task can consume the whole budget and truncate before the JSON is
    emitted. The SDK reports that as parsed_output=None rather than raising,
    which is why this has to be checked explicitly.
    """


@dataclass
class Usage:
    n_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, model: str, u: Any) -> None:
        with self._lock:
            self.n_calls += 1
            inp = getattr(u, "input_tokens", 0) or 0
            out = getattr(u, "output_tokens", 0) or 0
            cr = getattr(u, "cache_read_input_tokens", 0) or 0
            cw = getattr(u, "cache_creation_input_tokens", 0) or 0
            self.input_tokens += inp + cr + cw
            self.output_tokens += out
            self.cache_read_tokens += cr
            self.cache_write_tokens += cw
            self.cost_usd += estimate_cost(model, inp + cr + cw, out, cr)

    def add_openai(self, model: str, usage: dict[str, Any]) -> None:
        """Same accounting, OpenAI's field names.

        Cached prompt tokens are reported inside `prompt_tokens_details` when a
        provider reports them at all, so they are pulled out separately rather
        than billed at the full input rate.
        """
        with self._lock:
            self.n_calls += 1
            inp = usage.get("prompt_tokens", 0) or 0
            out = usage.get("completion_tokens", 0) or 0
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
            self.input_tokens += inp
            self.output_tokens += out
            self.cache_read_tokens += cached
            self.cost_usd += estimate_cost(model, inp, out, cached)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_calls": self.n_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cost_usd": round(self.cost_usd, 4),
            "errors": self.errors,
        }


class LLMClient:
    def __init__(self, model: str | None = None, effort: str | None = None):
        s = settings()
        if not s.has_anthropic:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        self.model = model or s.model
        self.effort = effort or s.effort
        self.concurrency = s.concurrency
        self.client = anthropic.Anthropic(api_key=s.anthropic_api_key)
        self.usage = Usage()
        self.adaptive = supports_adaptive(self.model)
        # Whether output_config.effort can ride alongside output_format is
        # resolved once, on the first call, rather than assumed.
        self._effort_supported: bool | None = None if supports_effort(self.model) else False

    # -- single call ------------------------------------------------------

    def parse(
        self,
        *,
        system: str,
        user: str,
        output_model: type[T],
        max_tokens: int = 16000,
        cache_system: bool = True,
    ) -> T:
        """One structured call.

        The system block carries the instructions and any item bank — large,
        byte-identical across every film, and therefore the cache prefix. The
        film's own evidence goes in the user turn, after the breakpoint, because
        it is the only part that varies.
        """
        system_blocks: list[dict[str, Any]] = [{"type": "text", "text": system}]
        if cache_system:
            system_blocks[-1]["cache_control"] = {"type": "ephemeral"}

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": [{"role": "user", "content": user}],
            "output_format": output_model,
        }
        if self.adaptive:
            kwargs["thinking"] = {"type": "adaptive"}
        if self._effort_supported is not False:
            kwargs["output_config"] = {"effort": self.effort}

        resp = self._with_retry(lambda: self.client.messages.parse(**kwargs), kwargs)
        self.usage.add(self.model, resp.usage)

        parsed = getattr(resp, "parsed_output", None)
        if parsed is None:
            stop = getattr(resp, "stop_reason", "unknown")
            out = getattr(resp.usage, "output_tokens", 0)
            hint = ""
            if stop == "max_tokens":
                hint = (f" The budget was exhausted before the answer was emitted "
                        f"(max_tokens={max_tokens}, output_tokens={out}). Thinking "
                        f"tokens come out of the same pool — raise max_tokens or "
                        f"split the work into smaller batches.")
            elif stop == "refusal":
                hint = " The request was declined by a safety classifier."
            raise LLMParseError(
                f"{output_model.__name__}: no structured output "
                f"(stop_reason={stop}, output_tokens={out}).{hint}"
            )
        return parsed

    def _with_retry(self, fn: Callable[[], Any], kwargs: dict[str, Any], tries: int = 5) -> Any:
        last: Exception | None = None
        for attempt in range(tries):
            try:
                out = fn()
                if self._effort_supported is None:
                    self._effort_supported = "output_config" in kwargs
                return out
            except TypeError as e:
                # Older SDK that does not accept one of our kwargs.
                if "output_config" in str(e) and "output_config" in kwargs:
                    self._effort_supported = False
                    kwargs.pop("output_config")
                    continue
                raise
            except anthropic.BadRequestError as e:
                # effort and output_format may not be combinable on this SDK/API
                # pairing; drop effort once and retry rather than failing the run.
                if "output_config" in kwargs and "output_config" in str(e).lower():
                    self._effort_supported = False
                    kwargs.pop("output_config")
                    continue
                raise
            except anthropic.RateLimitError as e:
                last = e
            except anthropic.APIStatusError as e:
                if e.status_code < 500:
                    raise
                last = e
            except anthropic.APIConnectionError as e:
                last = e

            time.sleep(min(60.0, (2 ** attempt) + random.random()))
        self.usage.errors += 1
        raise RuntimeError(f"gave up after {tries} attempts: {last}") from last

    # -- fan-out ----------------------------------------------------------

    def map(
        self,
        items: Iterable[Any],
        fn: Callable[[Any], Any],
        on_result: Callable[[Any, Any], None] | None = None,
        on_error: Callable[[Any, Exception], None] | None = None,
    ) -> list[Any]:
        """Run fn over items with bounded concurrency.

        A failing item is reported and skipped rather than aborting the sweep —
        40 films should not be lost to one malformed subtitle file.
        """
        items = list(items)
        results: list[Any] = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {pool.submit(fn, it): it for it in items}
            for fut in as_completed(futures):
                item = futures[fut]
                try:
                    res = fut.result()
                except Exception as e:  # noqa: BLE001 - surfaced, not swallowed
                    self.usage.errors += 1
                    if on_error:
                        on_error(item, e)
                    continue
                results.append(res)
                if on_result:
                    on_result(item, res)
        return results
