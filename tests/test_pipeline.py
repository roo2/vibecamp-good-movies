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
