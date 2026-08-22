"""Tests for the scorer-bias audit.

No network anywhere. The two things worth proving are that the transport can
survive models which do not honour a schema — that is the whole reason a
no-guardrails scorer is reachable at all — and that the report's arithmetic
says what the write-up will claim it says, on verdicts whose answer is known by
construction.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from moral_atlas.analysis import model_bias
from moral_atlas.llm import providers


# --------------------------------------------------------------------------
# Transport: surviving models that will not follow a schema
# --------------------------------------------------------------------------

def test_json_is_recovered_from_a_chatty_model():
    """A base model answers in prose with the object somewhere inside."""
    text = ('Sure! Here is what I think:\n```json\n'
            '{"scores": [{"item_id": "I1", "verdict": "affirms"}]}\n```\nHope that helps.')
    assert providers._first_json_object(text) == {
        "scores": [{"item_id": "I1", "verdict": "affirms"}]}


def test_braces_inside_strings_do_not_end_the_object():
    text = 'blah {"evidence": "he said {not really}", "value": 1} trailing'
    assert providers._first_json_object(text) == {
        "evidence": "he said {not really}", "value": 1}


def test_a_leading_broken_object_does_not_hide_a_good_one():
    text = '{oops not json} then {"item_id": "I2"}'
    assert providers._first_json_object(text) == {"item_id": "I2"}


def test_prose_with_no_object_at_all_is_not_invented():
    assert providers._first_json_object("I have no idea, sorry.") is None


@pytest.mark.parametrize("text", [
    "I can't help with rating the morality of this film.",
    "As an AI, I do not make moral judgements about people.",
    "I'm not able to assign moral verdicts here.",
])
def test_refusals_are_recognised(text):
    assert providers._looks_like_refusal(text)


def test_an_ordinary_answer_is_not_read_as_a_refusal():
    assert not providers._looks_like_refusal(
        "The film denies that obedience excuses complicity.")


def test_missing_credentials_names_the_variable_and_the_console(monkeypatch):
    from moral_atlas.config import settings

    monkeypatch.setattr(providers, "settings",
                        lambda: replace(settings(), xai_api_key=None, deepseek_api_key=None))
    missing = providers.missing_credentials(["grok", "deepseek"])
    assert set(missing) == {"grok", "deepseek"}
    assert missing["grok"].env_var == "XAI_API_KEY"
    assert missing["grok"].console.startswith("https://")


def test_an_unknown_scorer_is_refused_by_name():
    with pytest.raises(KeyError, match="gpt-9"):
        providers.resolve("gpt-9")


# --------------------------------------------------------------------------
# The report's arithmetic
# --------------------------------------------------------------------------

@pytest.fixture
def two_scorers(monkeypatch, tmp_path):
    """One axis, ten items, two films — and two scorers who disagree on purpose.

    The incumbent affirms every item; the challenger denies a third of them.
    Every item has polarity +1, so the incumbent's lean must be exactly +1 and
    the challenger's exactly the affirm/deny balance of what it said.
    """
    from moral_atlas import db
    from moral_atlas.config import settings

    test_settings = replace(settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
                            db_path=tmp_path / "bias.sqlite")
    monkeypatch.setattr(db, "settings", lambda: test_settings)
    db.init_db()

    with db.connect() as con:
        con.execute(
            "INSERT INTO dimensions (dim_version, dim_id, name, question, pole_high, "
            "pole_low, n_dims, source, created_at) VALUES ('d1',1,'Payback or Mercy','?','h','l',1,'test',?)",
            [db.now()],
        )
        for item in range(10):
            con.execute(
                "INSERT INTO item_bank (item_id, bank_version, text, cluster_id, active) "
                "VALUES (?,'b1',?,?,1)", [f"I{item}", f"proposition {item}", item])
            con.execute(
                "INSERT INTO item_dimensions (dim_version, bank_version, item_id, dim_id, "
                "polarity, fit, pass_name, created_at) VALUES ('d1','b1',?,1,1,0.9,'main',?)",
                [f"I{item}", db.now()])
        for film in ("film-a", "film-b"):
            for item in range(10):
                # Incumbent: everything affirms.
                con.execute(
                    "INSERT INTO scores (film_id, item_id, bank_version, variant, run_id, "
                    "value, confidence) VALUES (?,?, 'b1','spine','run-opus',1,0.9)",
                    [film, f"I{item}"])
                # Challenger: denies every third item.
                con.execute(
                    "INSERT INTO model_verdicts (scorer, model, film_id, item_id, bank_version, "
                    "variant, run_id, value, confidence, created_at) "
                    "VALUES ('grok','grok-4',?,?,'b1','spine','run-grok',?,0.9,?)",
                    [film, f"I{item}", -1 if item % 3 == 0 else 1, db.now()])
    return db


def test_the_report_separates_the_scorer_from_the_corpus(two_scorers):
    report = model_bias.report("b1", "d1")

    assert set(report["scorers"]) == {"opus", "grok"}
    assert report["scorers"]["opus"]["verdicts"] == 20
    assert report["scorers"]["opus"]["affirm_share"] == 1.0

    # 4 of every 10 items denied (0, 3, 6, 9) -> lean = (6 - 4) / 10
    lean = report["lean"]
    assert lean["opus"]["Payback or Mercy"]["lean"] == 1.0
    assert lean["grok"]["Payback or Mercy"]["lean"] == pytest.approx(0.2)

    [divergence] = report["divergence"]
    assert divergence["scorer"] == "grok"
    assert divergence["gap"] == pytest.approx(-0.8)
    assert divergence["n"] == 20


def test_agreement_is_chance_corrected(two_scorers):
    agreement = model_bias.report("b1", "d1")["agreement"]["grok vs opus"]
    assert agreement["shared_cells"] == 20
    assert agreement["raw"] == pytest.approx(0.6)
    # The incumbent never denies anything, so there is no agreement beyond
    # chance to find and kappa must not reward the 60% raw overlap.
    assert agreement["kappa"] == 0.0


def test_a_refusal_is_reported_rather_than_lost(two_scorers):
    with two_scorers.connect() as con:
        con.execute(
            "INSERT INTO model_refusals (scorer, model, film_id, variant, run_id, detail, "
            "created_at) VALUES ('grok','grok-4','film-a','spine','run-grok','declined',?)",
            [two_scorers.now()])
    assert model_bias.report("b1", "d1")["scorers"]["grok"]["refusals"] == 1


def test_the_audit_never_writes_to_the_product_scores(two_scorers):
    """The whole design rests on this: scoring again must not move the atlas."""
    with two_scorers.connect(read_only=True) as con:
        before = con.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    model_bias.report("b1", "d1")
    with two_scorers.connect(read_only=True) as con:
        after = con.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        challenger = con.execute(
            "SELECT COUNT(*) FROM scores WHERE run_id LIKE '%grok%'").fetchone()[0]
    assert before == after == 20
    assert challenger == 0


# --------------------------------------------------------------------------
# The request ladder, against a mock server rather than a real bill
# --------------------------------------------------------------------------

import httpx
from pydantic import BaseModel


class Verdict(BaseModel):
    item_id: str
    verdict: str


def _client_with(handler, alias="grok", monkeypatch=None):
    """An OpenAICompatibleClient whose transport is a function, not a network."""
    from moral_atlas.config import settings

    monkeypatch.setattr(providers, "settings",
                        lambda: replace(settings(), xai_api_key="test-key",
                                        openrouter_api_key="test-key", concurrency=2))
    client = providers.OpenAICompatibleClient(alias)
    client._client = httpx.Client(base_url="https://example.invalid",
                                  transport=httpx.MockTransport(handler))
    return client


def _completion(content, usage=None):
    return httpx.Response(200, json={
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20},
    })


def test_a_provider_that_rejects_json_schema_falls_back(monkeypatch):
    """xAI takes json_schema; DeepSeek 400s on it and takes json_object."""
    seen = []

    def handler(request):
        body = json.loads(request.content)
        kind = (body.get("response_format") or {}).get("type")
        seen.append(kind)
        if kind == "json_schema":
            return httpx.Response(400, json={"error": "response_format not supported"})
        return _completion('{"item_id": "I1", "verdict": "affirms"}')

    client = _client_with(handler, monkeypatch=monkeypatch)
    out = client.parse(system="s", user="u", output_model=Verdict)

    assert out.item_id == "I1"
    assert seen == ["json_schema", "json_object"]
    # The working rung is remembered, so the next call does not pay for the 400.
    client.parse(system="s", user="u", output_model=Verdict)
    assert seen == ["json_schema", "json_object", "json_object"]


def test_a_model_that_ignores_response_format_still_parses(monkeypatch):
    """The no-guardrails scorers answer in prose; the object is dug out."""
    def handler(request):
        assert "response_format" not in json.loads(request.content), \
            "scorers that cannot honour a schema should not be asked to"
        return _completion('Sure thing!\n{"item_id": "I7", "verdict": "denies"}\nHope that helps.')

    client = _client_with(handler, alias="dolphin", monkeypatch=monkeypatch)
    assert client.parse(system="s", user="u", output_model=Verdict).verdict == "denies"


def test_a_refusal_is_raised_as_a_refusal_not_a_parse_error(monkeypatch):
    def handler(request):
        return _completion("I can't make moral judgements about this film.")

    client = _client_with(handler, monkeypatch=monkeypatch)
    with pytest.raises(providers.Refusal):
        client.parse(system="s", user="u", output_model=Verdict)
    assert len(client.refusals) == 1


def test_a_provider_content_filter_counts_as_a_refusal(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        })

    client = _client_with(handler, monkeypatch=monkeypatch)
    with pytest.raises(providers.Refusal):
        client.parse(system="s", user="u", output_model=Verdict)


def test_usage_is_accounted_in_the_providers_own_field_names(monkeypatch):
    def handler(request):
        return _completion('{"item_id": "I1", "verdict": "affirms"}',
                           usage={"prompt_tokens": 1000, "completion_tokens": 200,
                                  "prompt_tokens_details": {"cached_tokens": 400}})

    client = _client_with(handler, monkeypatch=monkeypatch)
    client.parse(system="s", user="u", output_model=Verdict)
    usage = client.usage.as_dict()
    assert usage["n_calls"] == 1
    assert usage["input_tokens"] == 1000
    assert usage["output_tokens"] == 200
    assert usage["cache_read_tokens"] == 400
    assert usage["cost_usd"] > 0
