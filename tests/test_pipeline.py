"""Tests for the parts that must work before spending money on LLM calls."""
from __future__ import annotations

import textwrap

from moral_atlas.sources import subtitles as sub
from moral_atlas.sources import wikipedia as wiki

SAMPLE = textwrap.dedent("""\
    1
    00:00:12,000 --> 00:00:15,000
    [MUFASA] Everything the light touches
    is our kingdom.

    2
    00:00:18,500 --> 00:00:21,000
    <i>But Father...</i>

    3
    01:20:04,000 --> 01:20:08,000
    Remember who you are.

    4
    01:29:55,000 --> 01:29:59,000
    It is time.
    """)


def test_parse_srt_strips_markup_and_indices():
    cues = sub.parse_srt(SAMPLE)
    assert len(cues) == 4
    assert cues[0].text.startswith("[MUFASA]")          # SDH speaker label survives
    assert cues[1].text == "But Father..."              # <i> tags removed
    assert cues[0].start_ms == 12_000


def test_act_position_slicing():
    """Timestamps are why subtitles beat screenplays: the closing slice is
    where most moral propositions actually get settled."""
    cues = sub.parse_srt(SAMPLE)
    opening = sub.slice_by_position(cues, 0.0, 0.10)
    closing = sub.slice_by_position(cues, 0.85, 1.0)
    assert [c.text for c in opening] == [cues[0].text, cues[1].text]
    # 1:20:04 of a 1:29:59 film really is inside the final 15% — both late
    # cues belong here, and that is the slice the ending is extracted from.
    assert [c.text for c in closing] == [cues[2].text, cues[3].text]
    assert not set(c.text for c in opening) & set(c.text for c in closing)


def test_final_lines_captures_the_thesis_position():
    assert "It is time." in sub.final_lines(sub.parse_srt(SAMPLE), n=2)


def test_cues_render_with_timestamps():
    out = sub.cues_to_text(sub.parse_srt(SAMPLE))
    assert out.startswith("[0:00:12]")
    assert "[1:20:04]" in out


def test_section_splitter_is_path_aware():
    """Film articles bury interpretation in subsections — Maleficent's moral
    analysis is 'Reception > Rape allegory'. A flat splitter loses it."""
    text = textwrap.dedent("""\
        Lead paragraph.

        == Plot ==
        Things happen.

        == Production ==
        === Themes ===
        The film concerns duty.

        == Reception ==
        === Box office ===
        It made money.
        === Rape allegory ===
        Commentators read the scene as a metaphor.
        """)
    sections = wiki.split_sections(text)
    paths = {p for p, _ in sections}
    assert ("production", "themes") in paths
    assert ("reception", "rape allegory") in paths

    themes = wiki._collect(sections, wiki.THEME_HEADINGS, wiki.COMMERCE_HEADINGS)
    assert "concerns duty" in themes

    reception = wiki._collect(sections, wiki.RECEPTION_HEADINGS, wiki.COMMERCE_HEADINGS)
    assert "metaphor" in reception
    assert "It made money" not in reception   # commerce noise excluded


def test_variant_layer_map_is_the_ab_design():
    from moral_atlas.sources.packet import VARIANT_LAYERS
    assert VARIANT_LAYERS["spine"] == ("plot",)
    assert "subtitles" not in VARIANT_LAYERS["spine_themes"]
    assert VARIANT_LAYERS["subs"] == ("subtitles",)
    assert set(VARIANT_LAYERS["full"]) > set(VARIANT_LAYERS["spine_themes"])


def test_rendered_form_round_trips_for_slicing():
    """Evidence is stored rendered, not as SRT, so act-position slicing has to
    parse our own format back — otherwise `slices` mode silently no-ops."""
    stored = sub.cues_to_text(sub.parse_srt(SAMPLE))
    cues = sub.parse_any(stored)
    assert len(cues) == 4
    assert cues[0].start_ms == 12_000
    assert cues[-1].text == "It is time."
    assert len(sub.slice_by_position(cues, 0.85, 1.0)) == 2


# --- OPUS archive access -------------------------------------------------

def test_imdb_key_strips_prefix_and_leading_zeros():
    """OPUS directory names are the bare integer: tt0110357 -> 110357.
    Searching for the zero-padded form silently finds nothing."""
    from moral_atlas.sources import opus
    assert opus.imdb_key("tt0110357") == "110357"
    assert opus.imdb_key("tt2321549") == "2321549"
    assert opus.imdb_key("0042876") == "42876"


def test_plausibility_rejects_concatenated_tracks():
    """The largest Lion King track in OPUS is a concatenated dual-language file:
    3,132 cues running to 165 minutes for an 88-minute picture. Accepting it
    would put the 'closing 15%' slice in the wrong place entirely."""
    from moral_atlas.sources import opus

    good = [(i * 3_500, f"line {i}") for i in range(1_498)]      # ends ~87 min
    ok, why = opus._plausibility(good, runtime=88)
    assert ok, why

    concatenated = [(i * 3_170, f"line {i}") for i in range(3_132)]  # ends ~165 min
    ok, why = opus._plausibility(concatenated, runtime=88)
    assert not ok and "runtime" in why

    assert not opus._plausibility([], runtime=88)[0]
    stub = [(i * 1000, "x") for i in range(40)]
    assert not opus._plausibility(stub, runtime=88)[0]


def test_plausibility_without_runtime_uses_absolute_bounds():
    """Wikidata does not always carry a runtime, so the sanity band still has
    to catch the worst cases on its own."""
    from moral_atlas.sources import opus
    absurd = [(i * 60_000, "x") for i in range(400)]             # 6.6 hours
    assert not opus._plausibility(absurd, runtime=None)[0]
    fine = [(i * 3_500, "x") for i in range(1_500)]
    assert opus._plausibility(fine, runtime=None)[0]


def test_parse_opus_xml_carries_timestamps_forward():
    """Sentences without their own <time> marker inherit the last one, so they
    stay on the timeline instead of being dropped from act-position slices."""
    from moral_atlas.sources import opus
    xml = b"""<?xml version="1.0" encoding="utf-8"?>
    <document id="1">
      <s id="1"><time id="T1S" value="00:01:20,720"/>From the day we arrive<time id="T1E" value="00:01:22,995"/></s>
      <s id="2">On the planet</s>
      <s id="3"><time id="T3S" value="01:20:04,000"/>Remember who you are<time id="T3E" value="01:20:07,000"/></s>
    </document>"""
    cues = opus.parse_opus_xml(xml)
    assert [t for _, t in cues] == ["From the day we arrive", "On the planet",
                                    "Remember who you are"]
    assert cues[0][0] == 80_720
    assert cues[1][0] == 80_720          # inherited, not dropped
    assert cues[2][0] == 4_804_000


def test_plausibility_scales_density_with_runtime():
    """The Wolf of Wall Street is 180 minutes with ~4,370 cues — 24 per minute,
    entirely normal for a dialogue-dense three-hour film. A flat cue ceiling
    rejects it as corrupt, so density has to be measured per minute."""
    from moral_atlas.sources import opus
    wolf = [(int(i * 180 * 60_000 / 4_370), "f-bomb") for i in range(4_370)]
    ok, why = opus._plausibility(wolf, runtime=180)
    assert ok, why

    # A dead track that ticks along with almost no dialogue is still wrong.
    sparse = [(i * 120_000, "…") for i in range(60)]
    assert not opus._plausibility(sparse, runtime=120)[0]


# --- bank construction robustness -----------------------------------------

def _tmp_db(monkeypatch, tmp_path):
    """Point the store at a throwaway database."""
    from dataclasses import replace
    from moral_atlas import db as db_mod
    from moral_atlas.config import settings as real_settings
    s = replace(real_settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
                db_path=tmp_path / "t.duckdb")
    monkeypatch.setattr(db_mod, "settings", lambda: s)
    db_mod.init_db()
    return db_mod


def test_parse_raises_instead_of_returning_none(monkeypatch):
    """The SDK reports a truncated structured response as parsed_output=None
    rather than raising. Returning that silently surfaced later as
    'NoneType has no attribute pairs', pointing at the wrong line entirely."""
    from moral_atlas.llm.client import LLMClient, LLMParseError
    import pytest

    client = LLMClient.__new__(LLMClient)
    client.model, client.effort, client.concurrency = "claude-opus-5", "high", 1
    client._effort_supported = True
    client.adaptive = True
    from moral_atlas.llm.client import Usage
    client.usage = Usage()

    class Truncated:
        stop_reason = "max_tokens"
        parsed_output = None
        class usage:  # noqa: N801
            input_tokens, output_tokens = 500, 8000
            cache_read_input_tokens = cache_creation_input_tokens = 0

    monkeypatch.setattr(client, "_with_retry", lambda fn, kw, **k: Truncated())
    from moral_atlas.llm.schemas import PropositionSet
    with pytest.raises(LLMParseError) as e:
        client.parse(system="s", user="u", output_model=PropositionSet, max_tokens=8000)
    # The message has to name the real cause, not the symptom.
    assert "max_tokens" in str(e.value)
    assert "Thinking tokens" in str(e.value)


def test_bank_survives_a_failing_reversal_pass(monkeypatch, tmp_path):
    """Canonicalisation costs dozens of LLM calls; reversal detection is a cheap
    check on top. Writing the bank only after reversals meant one failed call
    discarded everything already paid for."""
    from moral_atlas.analysis import bank as bank_mod
    db_mod = _tmp_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bank_mod, "db", db_mod)

    clusters = [
        {"cluster_id": i, "representative": f"Proposition number {i}.",
         "support": 3, "n_statements": 4, "members": []}
        for i in range(5)
    ]

    class ExplodingReversals:
        def parse(self, **kw):
            if kw["output_model"] is bank_mod.CanonicalSet:
                return bank_mod.CanonicalSet(items=[
                    bank_mod.CanonicalItem(cluster_id=c["cluster_id"],
                                           text=f"Canonical {c['cluster_id']}.",
                                           drop=False, drop_reason="")
                    for c in clusters])
            raise RuntimeError("budget exhausted before the answer was emitted")

    result = bank_mod.build_bank("btest", clusters, ExplodingReversals())

    assert result["n_items"] == 5
    assert "budget exhausted" in result["reversal_error"]
    with db_mod.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT text FROM item_bank WHERE bank_version='btest'").fetchall()
    assert len(rows) == 5, "canonicalised bank must survive a reversal failure"
    assert rows[0][0].startswith("Canonical")
