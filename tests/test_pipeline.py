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
