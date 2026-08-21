"""Evidence packet assembly — the mechanism the source A/B runs on.

A packet is the text handed to the model for one film under one *variant*.
Variants deliberately withhold layers so the same proposition can be scored
from different evidence and the answers compared:

    spine         metadata + Wikipedia plot only
                  The condition you were worried about: a human-written summary,
                  interpretation stripped out by editorial policy.

    spine_themes  spine + themes/analysis + reception
                  Adds other people's readings. The difference between this and
                  `spine` is a direct measurement of what critical reception buys
                  — which is the endorsement problem in isolation.

    subs          metadata + the subtitle track
                  The film's own words, unmediated by any summariser. The
                  reference condition everything else is compared against.

    full          everything

Comparing `spine` against `subs` answers your question with a number instead of
an argument. Comparing `spine` against `spine_themes` tells you whether the
cheap fix is enough.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import db
from . import subtitles as subs_mod

VARIANTS = ("spine", "spine_themes", "subs", "full")

VARIANT_LAYERS: dict[str, tuple[str, ...]] = {
    "spine": ("plot",),
    "spine_themes": ("plot", "themes", "reception"),
    "subs": ("subtitles",),
    "full": ("plot", "themes", "reception", "subtitles"),
}

LAYER_TITLES = {
    "plot": "PLOT SUMMARY (Wikipedia, editorially neutral event recounting)",
    "themes": "THEMES AND ANALYSIS (Wikipedia)",
    "reception": "CRITICAL RECEPTION (Wikipedia)",
    "subtitles": "DIALOGUE TRACK (transcribed from the finished film; "
                 "timestamps show position through the runtime)",
}


def estimate_tokens(text: str) -> int:
    return len(text) // 4


@dataclass
class Packet:
    film_id: str
    variant: str
    title: str
    year: int | None
    header: str
    body: str
    layers_present: list[str] = field(default_factory=list)
    layers_missing: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return f"{self.header}\n\n{self.body}"

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)

    @property
    def usable(self) -> bool:
        """A packet with none of its variant's layers cannot be scored."""
        return bool(self.layers_present)


def _metadata_header(film: dict[str, Any], blind: bool = False) -> str:
    """Factual identifiers only.

    Genre and keywords are deliberately withheld: they are confound covariates
    for the analysis, and feeding them to the scorer would let topic leak
    straight back into the propositions we are trying to keep topic-free.
    """
    bits = [f"TITLE: {film['title']}"]
    if film.get("year"):
        bits.append(f"YEAR: {film['year']}")
    if film.get("runtime"):
        bits.append(f"RUNTIME: {film['runtime']} min")
    if film.get("original_language"):
        bits.append(f"ORIGINAL LANGUAGE: {film['original_language']}")
    if film.get("origin_country"):
        bits.append(f"COUNTRY: {', '.join(film['origin_country'])}")
    if film.get("directors"):
        bits.append(f"DIRECTED BY: {', '.join(film['directors'])}")
    if film.get("based_on"):
        bits.append(f"SOURCE MATERIAL: {film['based_on']}")
    return "\n".join(bits)


def build(film_id: str, variant: str, subtitle_mode: str = "full") -> Packet:
    """Assemble one film's packet for one variant.

    subtitle_mode:
      full     the whole track
      slices   opening 10% + closing 15% only, for cheap ending extraction
    """
    if variant not in VARIANT_LAYERS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {VARIANTS}")

    film = db.get_film(film_id)
    if film is None:
        raise KeyError(f"no such film: {film_id}")

    evidence = db.get_evidence(film_id)
    wanted = VARIANT_LAYERS[variant]

    present, missing, chunks = [], [], []
    for layer in wanted:
        content = (evidence.get(layer) or "").strip()
        if not content:
            missing.append(layer)
            continue

        if layer == "subtitles" and subtitle_mode == "slices":
            cues = subs_mod.parse_any(content)
            if cues:
                opening = subs_mod.cues_to_text(subs_mod.slice_by_position(cues, 0.0, 0.10))
                closing = subs_mod.cues_to_text(subs_mod.slice_by_position(cues, 0.85, 1.0))
                content = (
                    f"[OPENING 10%]\n{opening}\n\n[CLOSING 15%]\n{closing}"
                )

        present.append(layer)
        chunks.append(f"===== {LAYER_TITLES[layer]} =====\n{content}")

    return Packet(
        film_id=film_id,
        variant=variant,
        title=film["title"],
        year=film.get("year"),
        header=_metadata_header(film),
        body="\n\n".join(chunks) if chunks else "(no evidence available)",
        layers_present=present,
        layers_missing=missing,
    )


def completeness(film_id: str) -> dict[str, Any]:
    """Per-film evidence completeness, kept as a covariate.

    Thin-evidence films score differently from well-documented ones. That
    difference has to be visible in the data rather than hiding inside the
    factors, so it is recorded rather than inferred.
    """
    evidence = db.get_evidence(film_id)
    weights = {"plot": 0.40, "themes": 0.20, "reception": 0.15, "subtitles": 0.25}
    have = {k: bool((evidence.get(k) or "").strip()) for k in weights}
    score = sum(w for k, w in weights.items() if have[k])
    return {
        "film_id": film_id,
        "score": round(score, 2),
        "layers": have,
        "plot_words": len((evidence.get("plot") or "").split()),
        "subtitle_cues": (evidence.get("subtitles") or "").count("-->"),
        "runnable_variants": [
            v for v in VARIANTS
            if any(have.get(l) for l in VARIANT_LAYERS[v])
        ],
    }
