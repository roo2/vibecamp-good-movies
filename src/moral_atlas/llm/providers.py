"""Talking to scorers other than Claude, so the instrument can be audited.

Every number in this project comes from one model reading a film and voting on
694 moral propositions. That model has moral opinions of its own, and nothing in
the pipeline so far can tell the difference between "the film argues this" and
"a model trained a particular way reads the film as arguing this". The only way
to find out is to hand the identical bank, the identical evidence packet and the
identical rubric to models trained by different people under different norms,
and see where they part company.

Which is why this module exists and why it is deliberately thin. It is not a
general LLM abstraction — it is the smallest surface that lets `model_bias.py`
put a second and third scorer behind the same `parse()` call the Anthropic
client already offers, so the comparison differs in the model and in nothing
else.

Three things make other providers awkward, and each is handled rather than
assumed away:

*Structured output is not portable.* Anthropic takes a Pydantic model directly.
The OpenAI-compatible providers offer `json_schema` (xAI), `json_object`
(DeepSeek), or, on some community models served through OpenRouter, nothing at
all. `_request` walks down that ladder on rejection instead of failing, and the
last rung extracts the first JSON object out of prose.

*Refusals are data here, not errors.* A scorer that declines to judge a film's
morality is telling us something the study is specifically about, so a refusal
is captured as a `Refusal` and counted, never retried into silence.

*Cost accounting differs.* Usage comes back under OpenAI's field names, and
prices live in `config.PRICES` alongside the Anthropic ones.
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Iterable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..config import USER_AGENT, estimate_cost, settings
from .client import Usage

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    env_var: str
    console: str


PROVIDERS = {
    "anthropic": Provider("anthropic", "", "ANTHROPIC_API_KEY", "https://console.anthropic.com/"),
    "xai": Provider("xai", "https://api.x.ai/v1", "XAI_API_KEY", "https://console.x.ai/"),
    "deepseek": Provider("deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY",
                         "https://platform.deepseek.com/api_keys"),
    # One key reaches every open-weight model, including the ones no first-party
    # API will host. That is the only practical route to a scorer with no
    # refusal training, so the study depends on it.
    "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
                           "https://openrouter.ai/keys"),
}


@dataclass(frozen=True)
class Scorer:
    """One model under test, and what we expect its alignment posture to be.

    `posture` is a hypothesis, not a measurement — it records what we believe
    about the model's training so the report can say whether the verdicts bore
    it out. Writing it down in advance is what stops the result being read back
    into whatever we already believed.
    """
    alias: str
    provider: str
    model: str
    posture: str
    note: str


SCORERS = {
    s.alias: s for s in [
        Scorer("opus", "anthropic", "claude-opus-5", "safety-trained",
               "The incumbent. Every existing score in the database is this model."),
        Scorer("sonnet", "anthropic", "claude-sonnet-5", "safety-trained",
               "The same house as the incumbent at a fifth of the price, which "
               "makes it the affordable way to ask whether a Claude/DeepSeek gap "
               "is about training or about capability."),
        Scorer("grok", "xai", "grok-4", "lightly-filtered",
               "xAI trains explicitly against what it calls moralising; the most "
               "interesting comparison to a safety-trained scorer."),
        Scorer("deepseek", "deepseek", "deepseek-chat", "safety-trained, different norms",
               "Trained under Chinese content rules rather than US ones, so its "
               "guardrails sit in different places rather than being absent."),
        Scorer("deepseek-r1", "deepseek", "deepseek-reasoner", "safety-trained, reasoning",
               "Same house, reasoning-tuned: separates 'this model's norms' from "
               "'this model thought harder'."),
        Scorer("hermes", "openrouter", "nousresearch/hermes-4-405b",
               "neutrally aligned",
               "The strongest genuinely unaligned model OpenRouter serves: 405B, "
               "and Nous trains it to follow the operator rather than an internal "
               "policy, with refusal behaviour deliberately minimised. Frontier "
               "scale is what makes it evidence — when it disagrees with Claude "
               "that is a difference of judgement, not of competence."),
        Scorer("hermes-3", "openrouter", "nousresearch/hermes-3-llama-3.1-405b",
               "neutrally aligned, older",
               "The previous generation at the same size. Worth a run only to ask "
               "whether a Hermes/Claude gap is stable across Nous releases or an "
               "artefact of one of them."),
        Scorer("dolphin", "openrouter", "cognitivecomputations/dolphin-mistral-24b-venice-edition",
               "explicitly uncensored",
               "Alignment data stripped from the fine-tune outright. At 24B it is "
               "an order of magnitude smaller than Hermes, so a gap here may be "
               "incapacity rather than candour — read it as a floor, not a "
               "verdict. It is also the ONLY dolphin OpenRouter still lists; the "
               "8x22B mixtral edition is gone."),
    ]
}

# Some scorers cannot be trusted to honour a schema; ask for less from them.
# OpenRouter reports dolphin as taking response_format but not strict structured
# outputs, and at 24B it is the most likely to answer in prose regardless.
NO_RESPONSE_FORMAT = {"dolphin"}

REFUSAL_MARKERS = (
    "i can't", "i cannot", "i won't", "i'm not able to", "i am not able to",
    "i'm unable", "as an ai", "i must decline", "i do not feel comfortable",
    "i don't feel comfortable", "against my guidelines", "i apologize, but",
)


class Refusal(RuntimeError):
    """The scorer declined to answer. Counted and reported, never retried away."""

    def __init__(self, model: str, text: str):
        super().__init__(f"{model} declined: {text[:200]}")
        self.model = model
        self.text = text


def resolve(alias: str) -> Scorer:
    if alias not in SCORERS:
        raise KeyError(f"unknown scorer {alias!r} — known: {', '.join(SCORERS)}")
    return SCORERS[alias]


def credential_for(provider: str) -> str | None:
    s = settings()
    return {
        "anthropic": s.anthropic_api_key,
        "xai": s.xai_api_key,
        "deepseek": s.deepseek_api_key,
        "openrouter": s.openrouter_api_key,
    }.get(provider)


def available(alias: str) -> bool:
    return bool(credential_for(resolve(alias).provider))


def missing_credentials(aliases: Iterable[str]) -> dict[str, Provider]:
    """{alias: provider} for every requested scorer we have no key for."""
    out = {}
    for alias in aliases:
        scorer = resolve(alias)
        if not credential_for(scorer.provider):
            out[alias] = PROVIDERS[scorer.provider]
    return out


class Truncated(RuntimeError):
    """The answer was cut off by the token budget.

    Worth its own type because the failure it causes is silent otherwise. When
    the outer object never closes, brace-matching skips it and returns the first
    *inner* object that happens to balance — a single score instead of the whole
    set — which then fails schema validation somewhere far from the cause.
    """


def _first_json_object(text: str, require_key: str | None = None) -> dict[str, Any] | None:
    """Pull the first balanced {...} out of prose.

    The last resort for models that cannot be told to answer in JSON. Brace
    counting rather than a regex because the payload nests. `require_key` keeps
    a truncated outer object from silently degrading into an inner fragment:
    with it, only an object carrying the schema's own top-level key will do.
    """
    for candidate in _balanced_objects(text):
        if require_key is None or require_key in candidate:
            return candidate
    return None


def _balanced_objects(text: str):
    start = text.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        yield json.loads(text[start:index + 1])
                    except json.JSONDecodeError:
                        pass
                    break
        start = text.find("{", start + 1)


class OpenAICompatibleClient:
    """Same shape as `LLMClient`, so callers cannot tell which one they hold."""

    def __init__(self, alias: str, effort: str | None = None, timeout: float = 300.0):
        self.scorer = resolve(alias)
        self.alias = alias
        self.provider = PROVIDERS[self.scorer.provider]
        key = credential_for(self.scorer.provider)
        if not key:
            raise RuntimeError(
                f"{self.provider.env_var} is not set — {alias} needs a key from "
                f"{self.provider.console}"
            )
        self.model = self.scorer.model
        self.effort = effort or settings().effort
        self.concurrency = settings().concurrency
        self.usage = Usage()
        self.refusals: list[Refusal] = []
        self._lock = threading.Lock()
        self._format: str | None = None if alias not in NO_RESPONSE_FORMAT else "none"
        self._client = httpx.Client(
            base_url=self.provider.base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT},
        )

    # -- single call ------------------------------------------------------

    def parse(self, *, system: str, user: str, output_model: type[T],
              max_tokens: int = 16000, cache_system: bool = True) -> T:
        schema = output_model.model_json_schema()
        instruction = (
            f"{system}\n\nReply with a single JSON object and nothing else — no "
            f"prose, no markdown fence. It must satisfy this JSON schema:\n"
            f"{json.dumps(schema)}"
        )
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": user},
            ],
        }
        data = self._request(payload, output_model, schema)
        try:
            return output_model.model_validate(data)
        except ValidationError as e:
            raise RuntimeError(f"{self.model} returned JSON that is not a {output_model.__name__}: {e}") from e

    def _response_formats(self, schema: dict[str, Any], name: str) -> list[Any]:
        """The ladder, most capable first; `_format` remembers the rung that stuck."""
        if self._format == "none":
            return [None]
        rungs = {
            "json_schema": {"type": "json_schema",
                            "json_schema": {"name": name, "strict": False, "schema": schema}},
            "json_object": {"type": "json_object"},
            "none": None,
        }
        if self._format:
            return [rungs[self._format]]
        return list(rungs.values())

    def _request(self, payload: dict[str, Any], output_model: type[T],
                 schema: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for response_format in self._response_formats(schema, output_model.__name__):
            body = dict(payload)
            if response_format is not None:
                body["response_format"] = response_format
            try:
                text = self._post(body)
            except Truncated:
                raise
            except httpx.HTTPStatusError as e:
                # A 400 here usually means "I do not support that
                # response_format" — drop to the next rung rather than give up.
                if e.response.status_code == 400:
                    last = e
                    continue
                raise
            root_key = next(iter(schema.get("properties") or {}), None)
            parsed = _first_json_object(text, root_key)
            if parsed is None:
                if _looks_like_refusal(text):
                    refusal = Refusal(self.model, text)
                    with self._lock:
                        self.refusals.append(refusal)
                    raise refusal
                last = RuntimeError(f"{self.model} returned no JSON object: {text[:200]}")
                continue
            with self._lock:
                if self._format is None:
                    self._format = ("json_schema" if response_format
                                    and response_format.get("type") == "json_schema"
                                    else "json_object" if response_format else "none")
            return parsed
        raise RuntimeError(f"{self.model}: no usable structured output ({last})")

    def _post(self, body: dict[str, Any], tries: int = 5) -> str:
        last: Exception | None = None
        for attempt in range(tries):
            try:
                response = self._client.post("/chat/completions", json=body)
                if response.status_code == 429 or response.status_code >= 500:
                    last = httpx.HTTPStatusError(
                        f"{response.status_code}", request=response.request, response=response)
                    time.sleep(min(60.0, (2 ** attempt) + random.random()))
                    continue
                response.raise_for_status()
                data = response.json()
                self.usage.add_openai(self.model, data.get("usage") or {})
                choice = (data.get("choices") or [{}])[0]
                finish = choice.get("finish_reason")
                if finish == "content_filter":
                    raise Refusal(self.model, "stopped by the provider's content filter")
                content = (choice.get("message") or {}).get("content") or ""
                if finish == "length":
                    raise Truncated(
                        f"{self.model} hit the output limit after "
                        f"{(data.get('usage') or {}).get('completion_tokens', '?')} tokens. "
                        f"It is answering at far greater length than the rubric asks "
                        f"for — the bank expects only the items a film engages.")
                return content
            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as e:
                last = e
                time.sleep(min(60.0, (2 ** attempt) + random.random()))
        self.usage.errors += 1
        raise RuntimeError(f"{self.model}: gave up after {tries} attempts: {last}")

    # -- fan-out ----------------------------------------------------------

    def map(self, items: Iterable[Any], fn: Callable[[Any], Any],
            on_result: Callable[[Any, Any], None] | None = None,
            on_error: Callable[[Any, Exception], None] | None = None) -> list[Any]:
        items = list(items)
        results: list[Any] = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {pool.submit(fn, it): it for it in items}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    results.append(future.result())
                except Exception as e:  # noqa: BLE001 — surfaced, not swallowed
                    self.usage.errors += 1
                    if on_error:
                        on_error(item, e)
                    continue
                if on_result:
                    on_result(item, results[-1])
        return results


def _looks_like_refusal(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", text.lower())
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def client_for(alias: str, effort: str | None = None):
    """The right client for a scorer, Anthropic or otherwise."""
    scorer = resolve(alias)
    if scorer.provider == "anthropic":
        from .client import LLMClient
        return LLMClient(model=scorer.model, effort=effort)
    return OpenAICompatibleClient(alias, effort=effort)
