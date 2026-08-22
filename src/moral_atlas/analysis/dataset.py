"""The public dataset the interface visualises.

One JSON document, derived from the store, shaped for reading rather than for
transfer — `export.py` is the transfer format and keeps the tables as they are;
this is the opposite trade, denormalised so the browser does no joins.

It is built to be published. The demo site is static S3 behind CloudFront and
`/api/*` is served from the bucket, not from this API, so the visualisation
cannot query anything at run time: whatever it shows has to be in this file.
Two consequences follow, and both are deliberate rather than incidental.

**No evidence layer.** `evidence` holds subtitle text, which the repository is
careful never to commit because it is not ours to redistribute. It is not in
this bundle either, at any size. The short `evidence_quotes` a skeleton cites to
ground its own claims are kept — that is quotation for analysis, and the point
of the corpus is that every assertion can be checked against a line — but they
are capped per film so the bundle can never become a subtitle track by degrees.

**The variant is named, per film.** A film's skeleton exists under up to four
evidence conditions, and which one you read changes what it says. Showing a
number without saying which condition produced it is the one thing the source
A/B was built to stop, so every film here carries the variant it was read from.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .. import db
from ..config import PROMPT_VERSION

# Richest evidence first. A film shows the best skeleton it has, and says so.
VARIANT_PREFERENCE = ("full", "subs", "spine_themes", "spine")

# The A/B reads these cheapest-first; the interface reports coverage in the
# same order so the two never disagree about what "condition 1" means.
VARIANT_ORDER = ("spine", "spine_themes", "subs", "full")

VARIANT_LABELS = {
    "spine": "Plot only",
    "spine_themes": "Plot + themes",
    "subs": "Dialogue",
    "full": "Everything",
}

# Most retributive to most reparative. Not a score — an ordering that makes the
# distribution legible, which is why it is stated here rather than inferred.
FATE_ORDER = (
    "destroyed", "punished_but_alive", "reconciled", "becomes_protagonist",
    "escapes", "no_clear_antagonist", "unknown",
)

# Quotation for analysis, bounded. See the module docstring.
MAX_QUOTES = 6
MAX_QUOTE_CHARS = 300

# Passed straight through from the skeleton. Everything else in the film record
# is either computed or comes from `films`.
SKELETON_TEXT_FIELDS = (
    "legitimacy_source", "opening_power", "closing_power", "what_is_restored",
    "what_is_overturned", "antagonist", "antagonist_origin", "antagonist_fate",
    "protagonist_flaw", "protagonist_change", "final_image",
    "final_spoken_line", "tonal_register", "endorsement_evidence",
    "source_text", "inverts_source_how",
)
SKELETON_LIST_FIELDS = (
    "interiority_granted", "interiority_withheld", "punished", "forgiven",
    "unsupported_fields",
)


def _trim_quotes(quotes: Any) -> list[str]:
    if not isinstance(quotes, list):
        return []
    out = []
    for quote in quotes[:MAX_QUOTES]:
        text = str(quote).strip()
        if len(text) > MAX_QUOTE_CHARS:
            text = text[:MAX_QUOTE_CHARS].rstrip() + "…"
        if text:
            out.append(text)
    return out


def _best_skeletons(con) -> dict[str, dict[str, Any]]:
    """The richest skeleton per film, tagged with the condition it came from.

    A film can hold several rows for the same condition, because the table is
    keyed by run and a re-run does not replace its predecessor. Richest
    condition wins; within one condition, the most recent run does. Ordering by
    `created_at` here rather than trusting row order is the difference between
    showing the current extraction and showing an arbitrary old one.
    """
    rank = {v: i for i, v in enumerate(VARIANT_PREFERENCE)}
    best: dict[str, tuple[int, str, dict[str, Any]]] = {}
    rows = con.execute(
        "SELECT film_id, variant, data, model, prompt_version, created_at "
        "FROM skeletons ORDER BY created_at"
    ).fetchall()
    for row in rows:
        order = rank.get(row["variant"])
        if order is None:
            continue
        created = row["created_at"] or ""
        current = best.get(row["film_id"])
        # Strictly better condition, or the same condition run more recently.
        if current and (current[0] < order
                        or (current[0] == order and current[1] > created)):
            continue
        try:
            data = json.loads(row["data"])
        except (TypeError, ValueError):
            continue
        data["_variant"] = row["variant"]
        data["_model"] = row["model"]
        data["_prompt_version"] = row["prompt_version"]
        data["_created_at"] = created
        best[row["film_id"]] = (order, created, data)
    return {film_id: data for film_id, (_, _, data) in best.items()}


def _variant_coverage(con) -> list[dict[str, Any]]:
    skeletons = {
        r["variant"]: r["n"] for r in con.execute(
            "SELECT variant, COUNT(DISTINCT film_id) n FROM skeletons GROUP BY variant")
    }
    scored = {
        r["variant"]: (r["films"], r["n"]) for r in con.execute(
            "SELECT variant, COUNT(DISTINCT film_id) films, COUNT(*) n "
            "FROM scores GROUP BY variant")
    }
    return [
        {
            "variant": variant,
            "label": VARIANT_LABELS[variant],
            "films_with_skeleton": skeletons.get(variant, 0),
            "films_scored": scored.get(variant, (0, 0))[0],
            "scores": scored.get(variant, (0, 0))[1],
        }
        for variant in VARIANT_ORDER
    ]


def _dimensions(con, dim_version: str, bank_version: str) -> list[dict[str, Any]]:
    """The named axes, each carrying how much of the bank actually lands on it."""
    dims = con.execute(
        "SELECT dim_id, name, question, pole_high, pole_low FROM dimensions "
        "WHERE dim_version=? ORDER BY dim_id", [dim_version],
    ).fetchall()
    counts = {
        r["dim_id"]: (r["n"], r["fit"]) for r in con.execute(
            "SELECT dim_id, COUNT(*) n, AVG(fit) fit FROM item_dimensions "
            "WHERE dim_version=? AND bank_version=? AND pass_name='main' "
            "GROUP BY dim_id", [dim_version, bank_version])
    }
    return [
        {
            "dim_id": d["dim_id"],
            "name": d["name"],
            "question": d["question"],
            "pole_high": d["pole_high"],
            "pole_low": d["pole_low"],
            "n_items": counts.get(d["dim_id"], (0, None))[0],
            "mean_fit": round(counts[d["dim_id"]][1], 3)
            if d["dim_id"] in counts and counts[d["dim_id"]][1] is not None else None,
        }
        for d in dims
    ]


def _profiles(con, dim_version: str, bank_version: str) -> dict[str, list[dict[str, Any]]]:
    """Where each film sits on each axis, from the widest scoring it has.

    Mirrors `dimensions.film_profiles` but in one pass over SQL, because this
    runs on every publish and the analysis path re-derives clustering it does
    not need here. `net` is the mean signed verdict of the items on that axis:
    +1 is every scored item affirming the high pole, -1 every item denying it.
    """
    assignments = {
        r["item_id"]: (r["dim_id"], r["polarity"]) for r in con.execute(
            "SELECT item_id, dim_id, polarity FROM item_dimensions "
            "WHERE dim_version=? AND bank_version=? AND pass_name='main'",
            [dim_version, bank_version])
    }
    rows = con.execute(
        "SELECT film_id, item_id, variant, value FROM scores WHERE bank_version=?",
        [bank_version],
    ).fetchall()

    by_variant: dict[tuple[str, str], list] = defaultdict(list)
    for row in rows:
        by_variant[(row["film_id"], row["variant"])].append(row)

    widest: dict[str, tuple[str, list]] = {}
    for (film_id, variant), scored in by_variant.items():
        if film_id not in widest or len(scored) > len(widest[film_id][1]):
            widest[film_id] = (variant, scored)

    out: dict[str, list[dict[str, Any]]] = {}
    for film_id, (variant, scored) in widest.items():
        buckets: dict[int, list[int]] = defaultdict(list)
        for row in scored:
            placement = assignments.get(row["item_id"])
            if placement is None:
                continue
            dim_id, polarity = placement
            buckets[dim_id].append(polarity * row["value"])
        profile = [
            {
                "dim_id": dim_id,
                "net": round(sum(values) / len(values), 3),
                "n_items": len(values),
                "variant": variant,
            }
            for dim_id, values in sorted(buckets.items())
        ]
        if profile:
            out[film_id] = profile
    return out


def build(dim_version: str = "d1", bank_version: str = "b1") -> dict[str, Any]:
    """The whole document. Never raises on a half-run pipeline — it reports it."""
    with db.connect(read_only=True) as con:
        films = con.execute(
            "SELECT film_id, title, year, seed_note, description "
            "FROM films ORDER BY year, title"
        ).fetchall()
        skeletons = _best_skeletons(con)
        dimensions = _dimensions(con, dim_version, bank_version)
        profiles = _profiles(con, dim_version, bank_version)
        coverage = _variant_coverage(con)
        totals = {
            "films": len(films),
            "films_with_skeleton": len(skeletons),
            "films_with_full_skeleton": sum(
                1 for s in skeletons.values() if s["_variant"] == "full"),
            "films_profiled": len(profiles),
            "bank_items": con.execute(
                "SELECT COUNT(*) n FROM item_bank WHERE bank_version=? AND active=1",
                [bank_version]).fetchone()["n"],
            "scores": con.execute(
                "SELECT COUNT(*) n FROM scores WHERE bank_version=?",
                [bank_version]).fetchone()["n"],
            "dimensions": len(dimensions),
            "propositions": con.execute(
                "SELECT COUNT(*) n FROM propositions_raw").fetchone()["n"],
        }
        spend = con.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) c FROM runs").fetchone()["c"]

    fate_rank = {fate: i for i, fate in enumerate(FATE_ORDER)}
    records = []
    for film in films:
        skeleton = skeletons.get(film["film_id"])
        record: dict[str, Any] = {
            "id": film["film_id"],
            "title": film["title"],
            "year": film["year"],
            "note": film["seed_note"],
            "description": film["description"],
            "profile": profiles.get(film["film_id"], []),
        }
        if skeleton is None:
            record["skeleton"] = None
            records.append(record)
            continue

        record["variant"] = skeleton["_variant"]
        record["variant_label"] = VARIANT_LABELS[skeleton["_variant"]]
        record["model"] = skeleton["_model"]
        record["prompt_version"] = skeleton["_prompt_version"]
        record["extracted_at"] = skeleton["_created_at"]
        record["skeleton"] = {
            **{field: skeleton.get(field, "") for field in SKELETON_TEXT_FIELDS},
            **{field: list(skeleton.get(field) or []) for field in SKELETON_LIST_FIELDS},
            "antagonist_origin_given": bool(skeleton.get("antagonist_origin_given")),
            "depicts_but_does_not_endorse": bool(
                skeleton.get("depicts_but_does_not_endorse")),
            "confidence": skeleton.get("confidence"),
            "evidence_quotes": _trim_quotes(skeleton.get("evidence_quotes")),
        }
        record["fate_rank"] = fate_rank.get(
            skeleton.get("antagonist_fate", "unknown"), len(FATE_ORDER))
        records.append(record)

    return {
        "generated_at": db.now(),
        "prompt_version": PROMPT_VERSION,
        "dim_version": dim_version,
        "bank_version": bank_version,
        "totals": totals,
        "spend_usd": round(float(spend or 0), 2),
        "coverage": coverage,
        "fate_order": list(FATE_ORDER),
        "variant_order": list(VARIANT_ORDER),
        "variant_labels": dict(VARIANT_LABELS),
        "dimensions": dimensions,
        "films": records,
    }


def write(out_path: str | Path, dim_version: str = "d1",
          bank_version: str = "b1") -> tuple[Path, dict[str, Any]]:
    payload = build(dim_version, bank_version)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return path, payload
