"""The public dataset the interface visualises.

One JSON document, derived from the store, shaped for reading rather than for
transfer — `export.py` is the transfer format and keeps the tables as they are;
this is the opposite trade, denormalised so the browser does no joins.

It is built to be published. The demo site's pages come from an S3 bucket, and
the visualisation cannot query anything at run time: whatever it shows has to be
on disk before the deploy. It is written under `/data` rather than `/api`,
because CloudFront routes `/api/*` to the runner — a published file under that
prefix would be answered by an API with no route for it. Two consequences
follow, and both are deliberate.

**The index is small; evidence is beside it.** Every claim in the corpus is
supposed to be checkable against the text it was read from, so the evidence
travels — plot, themes, reception and the dialogue track. It is 3MB against an
index of 240KB, though, and making every visitor download a subtitle track for
forty films to read one chart would be a poor trade. So `write` emits an index
plus one file per film, and the interface fetches a film's evidence when
somebody opens that film. The short `evidence_quotes` a skeleton cites stay in
the index, because those are what the charts are annotated with.

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

# Quotation for analysis, bounded. These annotate the charts, so they live in
# the index rather than in the per-film evidence files.
MAX_QUOTES = 6
MAX_QUOTE_CHARS = 300

# The null for the permutation tests. A published number should rest on a
# thousand regroupings; a test asserting the field exists should not pay for
# them, so this is a module constant a test can lower rather than a literal.
PERMUTATIONS = 1000

# Thinnest first: this is the order the evidence reads in, and roughly the order
# of how much of it there is.
EVIDENCE_LAYERS = ("plot", "themes", "reception", "subtitles")

EVIDENCE_LABELS = {
    "plot": "Plot summary",
    "themes": "Themes and analysis",
    "reception": "Critical reception",
    "subtitles": "Dialogue track",
}

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


def _evidence_index(con) -> dict[str, list[dict[str, Any]]]:
    """What each film has, without the text — enough to label a closed panel."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = con.execute(
        "SELECT film_id, layer, word_count, LENGTH(content) chars FROM evidence"
    ).fetchall()
    order = {layer: i for i, layer in enumerate(EVIDENCE_LAYERS)}
    for row in rows:
        if row["layer"] not in order:
            continue
        out[row["film_id"]].append({
            "layer": row["layer"],
            "label": EVIDENCE_LABELS[row["layer"]],
            "words": row["word_count"],
            "chars": row["chars"],
        })
    for layers in out.values():
        layers.sort(key=lambda layer: order[layer["layer"]])
    return out


def _film_axes(con, film_id: str, dim_version: str, bank_version: str) -> list[dict[str, Any]]:
    """Why this film sits where it does, axis by axis.

    A position on an axis is a mean over item verdicts, and a mean is not an
    argument. This returns the verdicts it was made of: the proposition, whether
    the film affirmed or denied it, and the grounding the scorer gave — so the
    number on the page can be read back to the sentences that produced it.

    Read from the widest scoring the film has, and that condition is named,
    because a film scored on plot alone is making a thinner case than one scored
    on its dialogue.
    """
    rows = con.execute(
        "SELECT s.variant, s.item_id, s.value, s.confidence, s.evidence, "
        "       b.text, d.dim_id, d.polarity, d.fit "
        "FROM scores s "
        "JOIN item_dimensions d ON d.item_id = s.item_id "
        "     AND d.bank_version = s.bank_version AND d.pass_name = 'main' "
        "     AND d.dim_version = ? "
        "JOIN item_bank b ON b.item_id = s.item_id AND b.bank_version = s.bank_version "
        "WHERE s.film_id = ? AND s.bank_version = ?",
        [dim_version, film_id, bank_version],
    ).fetchall()
    if not rows:
        return []

    by_variant: dict[str, list] = defaultdict(list)
    for row in rows:
        by_variant[row["variant"]].append(row)
    variant, widest = max(by_variant.items(), key=lambda kv: len(kv[1]))

    by_dim: dict[int, list] = defaultdict(list)
    for row in widest:
        by_dim[row["dim_id"]].append(row)

    out = []
    for dim_id, scored in sorted(by_dim.items()):
        # Signed toward the axis's high pole, which is what `net` means.
        signed = [row["polarity"] * row["value"] for row in scored]
        items = [
            {
                "item_id": row["item_id"],
                "text": row["text"],
                # What the film did with the proposition, before polarity is
                # applied — "affirms" is about the statement, not the axis.
                "verdict": "affirms" if row["value"] > 0 else
                           "denies" if row["value"] < 0 else "not addressed",
                "toward": "high" if row["polarity"] * row["value"] > 0 else
                          "low" if row["polarity"] * row["value"] < 0 else None,
                "confidence": row["confidence"],
                "evidence": row["evidence"],
                "fit": row["fit"],
            }
            for row in sorted(scored, key=lambda r: -abs(r["value"] * (r["confidence"] or 0)))
        ]
        out.append({
            "dim_id": dim_id,
            "net": round(sum(signed) / len(signed), 3),
            "n_items": len(signed),
            "variant": variant,
            "variant_label": VARIANT_LABELS.get(variant, variant),
            "items": items,
        })
    return out


def film_evidence(film_id: str, dim_version: str = "d1",
                  bank_version: str = "b1") -> dict[str, Any] | None:
    """One film in full: what it was read from, and why it sits where it does.

    Returned as its own document because it is large and only wanted when
    somebody asks for that film. `None` if the film does not exist; a film that
    exists with no evidence yet returns an empty `layers`, which the interface
    can say plainly rather than treating as an error.
    """
    with db.connect(read_only=True) as con:
        film = con.execute(
            "SELECT film_id, title, year FROM films WHERE film_id=?", [film_id],
        ).fetchone()
        if film is None:
            return None
        rows = con.execute(
            "SELECT layer, content, source_url, word_count FROM evidence "
            "WHERE film_id=?", [film_id],
        ).fetchall()
        axes = _film_axes(con, film_id, dim_version, bank_version)

    order = {layer: i for i, layer in enumerate(EVIDENCE_LAYERS)}
    layers = sorted(
        ({
            "layer": row["layer"],
            "label": EVIDENCE_LABELS[row["layer"]],
            "content": row["content"],
            "source_url": row["source_url"],
            "words": row["word_count"],
        } for row in rows if row["layer"] in order),
        key=lambda layer: order[layer["layer"]],
    )
    return {
        "id": film["film_id"], "title": film["title"], "year": film["year"],
        "axes": axes,
        "layers": layers,
    }


def _reduction(con, bank_version: str, n_dimensions: int) -> dict[str, Any]:
    """The funnel from raw statements to axes, with the count at every step.

    The headline of this project is a reduction — hundreds of propositions to a
    handful of axes — and a reduction is only believable if you can see what was
    dropped and where. Every number here is counted from the store rather than
    quoted from a write-up.
    """
    propositions = con.execute("SELECT COUNT(*) n FROM propositions_raw").fetchone()["n"]
    source_films = con.execute(
        "SELECT COUNT(DISTINCT film_id) n FROM propositions_raw").fetchone()["n"]
    bank_total = con.execute(
        "SELECT COUNT(*) n FROM item_bank WHERE bank_version=?", [bank_version],
    ).fetchone()["n"]
    bank_active = con.execute(
        "SELECT COUNT(*) n FROM item_bank WHERE bank_version=? AND active=1",
        [bank_version]).fetchone()["n"]
    scored = con.execute(
        "SELECT COUNT(*) n FROM scores WHERE bank_version=?", [bank_version],
    ).fetchone()["n"]
    placed = con.execute(
        "SELECT COUNT(*) n FROM item_dimensions WHERE bank_version=? AND pass_name='main'",
        [bank_version]).fetchone()["n"]

    # Only statements belong on this ladder. The scoring pass is a much larger
    # number in a different unit — verdicts, not claims — and putting it on the
    # same scale makes the reduction it is evidence for look trivial.
    return {
        "stages": [
            {"key": "propositions", "n": propositions,
             "label": "Propositions harvested",
             "detail": f"free-text moral claims read out of {source_films} films, "
                       f"before anything was merged"},
            {"key": "bank", "n": bank_active,
             "label": "Items in the bank",
             "detail": "clustered, canonicalised and pruned to one statement per claim"
                       + ("" if bank_active == bank_total
                          else f"; {bank_total - bank_active} retired")},
            {"key": "dimensions", "n": n_dimensions,
             "label": "Axes",
             "detail": f"{placed} items placed, each on exactly one axis"},
        ],
        "scored": scored,
        "source_films": source_films,
    }


def _per_axis_agreement(con, dim_version: str, bank_version: str) -> dict[int, dict[str, Any]]:
    """How often an independent pass put an axis's items back on that axis.

    Overall kappa can look healthy while one axis quietly does all the work, so
    the reliability of each axis is reported separately as well as in aggregate.
    """
    rows = con.execute(
        "SELECT m.dim_id, m.item_id, m.fit, r.dim_id AS other_dim, "
        "       m.polarity, r.polarity AS other_polarity "
        "FROM item_dimensions m "
        "LEFT JOIN item_dimensions r "
        "  ON r.item_id = m.item_id AND r.dim_version = m.dim_version "
        "     AND r.bank_version = m.bank_version AND r.pass_name != 'main' "
        "WHERE m.dim_version=? AND m.bank_version=? AND m.pass_name='main'",
        [dim_version, bank_version],
    ).fetchall()

    by_dim: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"n_items": 0, "fits": [], "rechecked": 0, "same_axis": 0,
                 "same_polarity": 0})
    for row in rows:
        bucket = by_dim[row["dim_id"]]
        bucket["n_items"] += 1
        if row["fit"] is not None:
            bucket["fits"].append(row["fit"])
        if row["other_dim"] is not None:
            bucket["rechecked"] += 1
            if row["other_dim"] == row["dim_id"]:
                bucket["same_axis"] += 1
            if row["other_polarity"] == row["polarity"]:
                bucket["same_polarity"] += 1

    out: dict[int, dict[str, Any]] = {}
    for dim_id, bucket in by_dim.items():
        fits = sorted(bucket["fits"])
        rechecked = bucket["rechecked"]
        out[dim_id] = {
            "n_items": bucket["n_items"],
            "median_fit": fits[len(fits) // 2] if fits else None,
            "rechecked": rechecked,
            "same_axis": round(bucket["same_axis"] / rechecked, 3) if rechecked else None,
            "same_polarity": (round(bucket["same_polarity"] / rechecked, 3)
                              if rechecked else None),
        }
    return out


def _split_half(settings_obj=None) -> dict[str, Any] | None:
    """The two axis sets derived from disjoint halves of the corpus.

    This is the audit that can most cleanly embarrass the taxonomy: derive twice
    from film sets sharing no propositions, and if the two halves disagree the
    axes came from the prompt rather than the corpus. `dimensions.split_half`
    does not persist — it needs an LLM and is a test rather than a layer — so
    this reads the run's output if it is on disk and says nothing if it is not.

    No number is computed from it. Whether two axes named by different runs are
    the same axis is a reading, and dressing a reading up as a correlation would
    be worse than leaving the reader to do it themselves.
    """
    from ..config import settings

    path = (settings_obj or settings()).data_dir / "dimensions-splithalf.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return None

    def axes(key_variants):
        for key in key_variants:
            value = raw.get(key)
            if isinstance(value, list):
                return [{"dim_id": str(a.get("dim_id", "")), "name": a.get("name", ""),
                         "question": a.get("question", "")}
                        for a in value if isinstance(a, dict)]
        return []

    half_a = axes(("half_a", "HALF A"))
    half_b = axes(("half_b", "HALF B"))
    if not half_a or not half_b:
        return None
    return {
        "half_a": half_a,
        "half_b": half_b,
        "half_a_films": len(raw.get("half_a_films") or []),
        "half_b_films": len(raw.get("half_b_films") or []),
        "seed": raw.get("seed"),
    }


def _reliability(dim_version: str, bank_version: str,
                 permutations: int | None = None) -> dict[str, Any] | None:
    """The evidence that the axes are in the corpus rather than in the prompt.

    Runs the same battery `atlas dimensions-validate` prints, so a number on the
    page is the number that command produces — same seed, same result. It is a
    few seconds of pure arithmetic with no API call, which is cheap enough to do
    on every publish and keeps the page from quoting a stale figure.

    Returns None when the pipeline has not got far enough to have an answer;
    the page then simply does not claim one.
    """
    from . import dimensions as dim_mod

    try:
        report = dim_mod.validate(
            dim_version, bank_version,
            permutations=PERMUTATIONS if permutations is None else permutations,
            seed=3)
    except Exception:                 # a half-run pipeline, not a fault
        return None

    passes = []
    for name, agreement in report.get("agreement", {}).items():
        passes.append({
            "pass": name,
            "model": agreement.get("model"),
            "n": agreement["n"],
            "raw": agreement["raw"],
            "chance": agreement["chance"],
            "kappa": agreement["kappa"],
            "polarity_agreement": agreement.get("polarity_agreement"),
        })

    tests = []
    for key, label, reads in (
        ("co_engagement", "Co-engagement",
         "films that engage one item on an axis tend to engage its others"),
        ("coherence", "Stance coherence",
         "a film's verdicts within an axis point the same way rather than cancelling"),
    ):
        result = report.get(key)
        if not result:
            continue
        tests.append({
            "key": key, "label": label, "reads": reads,
            "observed": result["observed"],
            "null_mean": result["null_mean"],
            "null_sd": result["null_sd"],
            "z": result["z"],
            "permutations": result["permutations"],
            "n_at_least_observed": result["n_at_least_observed"],
            "n_cells": result.get("n_cells"),
        })

    return {
        "seed": report["seed"],
        "n_items": report["n_items"],
        "median_fit": report["coverage"]["median_fit"],
        "share_fit_ge_0_4": report["coverage"]["share_fit_ge_0_4"],
        "n_packets": report.get("n_packets"),
        "n_engagements": report.get("n_engagements"),
        "exclude_own_film": report.get("exclude_own_film"),
        "passes": passes,
        "tests": tests,
    }


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
        evidence = _evidence_index(con)
        coverage = _variant_coverage(con)
        agreement = _per_axis_agreement(con, dim_version, bank_version)
        reduction = _reduction(con, bank_version, len(dimensions))
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

    for dimension in dimensions:
        dimension["agreement"] = agreement.get(dimension["dim_id"])

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
            # What text exists for this film, but not the text itself: it is
            # fetched per film, so the index stays small enough to open on a
            # phone. See the module docstring.
            "evidence_layers": evidence.get(film["film_id"], []),
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
        "reduction": reduction,
        "reliability": _reliability(dim_version, bank_version),
        "split_half": _split_half(),
        "dimensions": dimensions,
        "films": records,
    }


def _dump(path: Path, payload: Any) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text)
    return len(text.encode())


def write(out_path: str | Path, dim_version: str = "d1", bank_version: str = "b1",
          include_evidence: bool = True) -> tuple[Path, dict[str, Any]]:
    """Write the index, and one evidence file per film beside it.

    The evidence files go in a directory named for the index — `atlas.json`
    gets `atlas/<film_id>.json` — so a static host serves them from the same
    prefix the interface asks for, with no routing to configure.
    """
    payload = build(dim_version, bank_version)
    path = Path(out_path)
    index_bytes = _dump(path, payload)

    written, evidence_bytes = 0, 0
    if include_evidence:
        directory = path.with_suffix("")
        for film in payload["films"]:
            if not film["evidence_layers"]:
                continue
            document = film_evidence(film["id"], dim_version, bank_version)
            if document is None:
                continue
            evidence_bytes += _dump(directory / f"{film['id']}.json", document)
            written += 1

    payload["_written"] = {
        "index_path": str(path), "index_bytes": index_bytes,
        "evidence_files": written, "evidence_bytes": evidence_bytes,
    }
    return path, payload
