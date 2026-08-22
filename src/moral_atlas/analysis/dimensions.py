"""Name the axes the item bank is measuring, and prove they are in the corpus.

The bank is an instrument, not an answer: 694 propositions is a fine thing to
score against and a useless thing to hand a person. What a reader wants is a
handful of moral axes they can hold in their head — and what this project needs
is for those axes to be a finding about the films rather than a taxonomy we
brought with us.

Two questions are easy to conflate, and only the first is a clustering problem:

    DEDUP      are these two items the same proposition?
    DIMENSION  which axis of moral disagreement does this item sit on?

The TF-IDF clustering in `bank.py` answers the first and cannot answer the
second. It compares vocabulary, not meaning: items average ~16 words over a
6,000-term vocabulary, so the typical nearest-neighbour cosine similarity is
about 0.12 and the merge threshold of 0.45 demands 0.55. Two of 694 items clear
it, which is why a 696-proposition pool produced 694 clusters. Worse, the
canonicalisation pass deliberately rewrites each cluster into distinctive
general prose, so two items expressing one idea are pushed further apart in
exactly the space the clustering measures. Forcing small k does not rescue it:
LSA to 100 components then k-means gives a silhouette of ~0.03 at k=6/8/10,
which is another way of spelling "no lexical structure".

So the axes are derived semantically, by an LLM reading the whole bank. That
buys the right answer and a fair objection: an LLM asked for eight moral
dimensions will always produce eight moral dimensions, and they may say more
about the model's priors than about these films. Hence `validate()`, which is
the real content of this module. Four of its five tests can fail:

    SPLIT-HALF     derive twice from disjoint halves of the CORPUS. Axes that
                   recur across films that share no propositions are a property
                   of the material, not of the prompt.
    REPLICATE      re-assign items with the item order shuffled and the
                   dimensions renumbered. Low agreement means items have no
                   determinate home and the axes are decorative.
    CROSS-MODEL    re-assign with a different model. Agreement here is what
                   separates "a real distinction" from "one model's taste".
    CO-ENGAGEMENT  scoring never saw the dimensions and the assignment never saw
                   the scores. If films nonetheless engage items from one axis
                   together more than chance, the axis exists in how the corpus
                   behaves, not only in how it reads.
    COHERENCE      within a film and an axis, do polarity-adjusted verdicts
                   agree? A real axis has films landing on a POLE; a decorative
                   one has them scattered.

The last two are permutation-tested against a null that shuffles which item
belongs to which axis while holding the axis sizes and each item's polarity
fixed, so a "significant" result cannot be manufactured by lopsided groups. Both
also run in a strict mode that discards each film's verdicts on items harvested
from that same film, because almost every item traces to one source film and a
film voting on its own propositions would inflate the signal for free.
"""
from __future__ import annotations

import json
import random
import statistics as st
import uuid
from collections import defaultdict
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .. import db
from ..config import PROMPT_VERSION
from . import bank as bank_mod

# Passes live side by side in item_dimensions under these names.
MAIN_PASS = "main"
REPLICATE_PASS = "replicate"


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class Dimension(BaseModel):
    dim_id: int
    name: str = Field(description="2-4 words, plain English, no jargon.")
    question: str = Field(
        description="The moral question this axis poses, as one sentence."
    )
    pole_high: str = Field(description="What a film at the HIGH pole asserts.")
    pole_low: str = Field(description="What a film at the LOW pole asserts.")


class DimensionSet(BaseModel):
    dimensions: list[Dimension]


class Assignment(BaseModel):
    item_id: str
    dim_id: int
    polarity: int = Field(
        description="+1 if affirming the item pushes toward pole_high, -1 toward pole_low."
    )
    fit: float = Field(description="0-1, how squarely the item belongs on this axis.")


class AssignmentSet(BaseModel):
    assignments: list[Assignment]


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

def derive_system(n_dims: int) -> str:
    return (
        "You are designing a compact measuring instrument for the moral content "
        "of films.\n\n"
        "You are given moral propositions harvested from a film corpus. Identify "
        f"exactly {n_dims} underlying moral DIMENSIONS that this material is "
        "really measuring.\n\n"
        "Requirements:\n"
        "  - Each dimension is a genuine axis of moral disagreement, with two "
        "poles a thoughtful person could sit at. Not a topic label — an axis.\n"
        "  - Together they should cover the great majority of the material, and "
        "overlap as little as possible.\n"
        "  - Name them in plain English a non-specialist would understand at a "
        "glance.\n"
        f"  - Number them 1..{n_dims} in dim_id."
    )


def assign_system(dims: list[dict[str, Any]]) -> str:
    """The dimension block is byte-identical across every batch: the cache prefix."""
    block = "\n".join(
        f"{d['dim_id']}. {d['name']} — {d['question']} "
        f"HIGH: {d['pole_high']} LOW: {d['pole_low']}"
        for d in dims
    )
    return (
        "You assign each moral proposition to exactly one of a fixed set of "
        "moral dimensions, and record which pole affirming it points to.\n\n"
        "Set fit below 0.4 when the item does not really belong on any axis; "
        "pick the closest one anyway so every item is placed.\n\n"
        f"THE DIMENSIONS\n\n{block}"
    )


# --------------------------------------------------------------------------
# Reading the store
# --------------------------------------------------------------------------

def bank_items(bank_version: str) -> list[dict[str, Any]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, text, cluster_id FROM item_bank "
            "WHERE bank_version=? AND active=1 ORDER BY item_id",
            [bank_version],
        ).fetchall()
    return [dict(r) for r in rows]


def raw_propositions(films: Iterable[str] | None = None) -> list[tuple[str, str]]:
    with db.connect(read_only=True) as con:
        rows = con.execute("SELECT film_id, text FROM propositions_raw").fetchall()
    keep = set(films) if films is not None else None
    return [(r["film_id"], r["text"]) for r in rows
            if keep is None or r["film_id"] in keep]


def item_source_films(bank_version: str, threshold: float = 0.45) -> dict[str, set[str]]:
    """Which film each bank item was harvested from.

    Recovered by re-running the same deterministic clustering the bank was cut
    from and joining on cluster_id, rather than stored at build time — the banks
    that already exist predate this module. `threshold` must therefore match the
    one used for `atlas bank`, or the cluster ids will not line up; a mismatch
    shows up immediately as items with no source film, which `validate` reports.
    """
    clusters = bank_mod.cluster_propositions(threshold)
    by_cluster = {c["cluster_id"]: {m[1] for m in c["members"]} for c in clusters}
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, cluster_id FROM item_bank WHERE bank_version=?",
            [bank_version],
        ).fetchall()
    return {r["item_id"]: by_cluster.get(r["cluster_id"], set()) for r in rows}


def load_dimensions(dim_version: str) -> list[dict[str, Any]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT dim_id, name, question, pole_high, pole_low FROM dimensions "
            "WHERE dim_version=? ORDER BY dim_id", [dim_version],
        ).fetchall()
    return [dict(r) for r in rows]


def load_assignments(dim_version: str, bank_version: str,
                     pass_name: str = MAIN_PASS) -> dict[str, dict[str, Any]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, dim_id, polarity, fit FROM item_dimensions "
            "WHERE dim_version=? AND bank_version=? AND pass_name=?",
            [dim_version, bank_version, pass_name],
        ).fetchall()
    return {r["item_id"]: dict(r) for r in rows}


def list_passes(dim_version: str, bank_version: str) -> list[tuple[str, str, int]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT pass_name, model, COUNT(*) n FROM item_dimensions "
            "WHERE dim_version=? AND bank_version=? GROUP BY pass_name, model "
            "ORDER BY pass_name", [dim_version, bank_version],
        ).fetchall()
    return [(r["pass_name"], r["model"], r["n"]) for r in rows]


# --------------------------------------------------------------------------
# Derivation and assignment
# --------------------------------------------------------------------------

def derive(
    dim_version: str, client, n_dims: int = 8, bank_version: str | None = None,
    films: Iterable[str] | None = None, persist: bool = True, progress=None,
) -> list[dict[str, Any]]:
    """Derive `n_dims` moral axes from the bank, or from raw propositions.

    Deriving from raw propositions (`bank_version=None`) is what makes the
    split-half audit possible: propositions carry a film_id, canonical bank
    items no longer do.
    """
    if bank_version:
        texts = [it["text"] for it in bank_items(bank_version)]
        source = f"bank:{bank_version}"
    else:
        rows = raw_propositions(films)
        texts = [t for _f, t in rows]
        source = f"propositions:{len({f for f, _ in rows})}films"
    if not texts:
        raise RuntimeError("nothing to derive from — run `atlas propose` first")

    listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    res = client.parse(
        system=derive_system(n_dims),
        user=f"The propositions:\n\n{listing}",
        output_model=DimensionSet,
        max_tokens=16000,
    )
    dims = [d.model_dump() for d in res.dimensions]
    if progress:
        progress(f"derived [bold]{len(dims)}[/] dimensions from {len(texts)} "
                 f"propositions ({source})")

    if persist:
        run_id = db.new_run_id("dimensions")
        with db.connect() as con:
            con.execute("DELETE FROM dimensions WHERE dim_version=?", [dim_version])
            for d in dims:
                con.execute(
                    "INSERT INTO dimensions (dim_version, dim_id, name, question, "
                    "pole_high, pole_low, n_dims, source, run_id, model, "
                    "prompt_version, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    [dim_version, d["dim_id"], d["name"], d["question"],
                     d["pole_high"], d["pole_low"], len(dims), source, run_id,
                     client.model, PROMPT_VERSION, db.now()],
                )
    return dims


def assign(
    dim_version: str, bank_version: str, dims: list[dict[str, Any]], client,
    items: list[dict[str, Any]] | None = None, batch_size: int = 60,
    pass_name: str = MAIN_PASS, shuffle_seed: int | None = None,
    persist: bool = True, progress=None,
) -> list[dict[str, Any]]:
    """Place every item on one axis, in parallel batches.

    `shuffle_seed` drives the blind replicate: it shuffles the item order AND
    renumbers the dimensions, so a second pass cannot agree with the first by
    reproducing a position in a list. Answers are mapped back before they are
    stored, which is the only reason the two passes are comparable at all.
    """
    items = items if items is not None else bank_items(bank_version)
    dims_used, back = dims, {d["dim_id"]: d["dim_id"] for d in dims}

    if shuffle_seed is not None:
        rng = random.Random(shuffle_seed)
        items = list(items)
        rng.shuffle(items)
        order = list(range(len(dims)))
        rng.shuffle(order)
        dims_used, back = [], {}
        for new_id, old_ix in enumerate(order, start=1):
            d = dict(dims[old_ix])
            back[new_id] = dims[old_ix]["dim_id"]
            d["dim_id"] = new_id
            dims_used.append(d)

    system = assign_system(dims_used)
    batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
    valid = {d["dim_id"] for d in dims_used}
    got: list[Assignment] = []

    def work(batch):
        listing = "\n".join(f"{it['item_id']}. {it['text']}" for it in batch)
        return client.parse(
            system=system, user=f"Assign these items:\n\n{listing}",
            output_model=AssignmentSet, max_tokens=16000,
        )

    def ok(_batch, res):
        got.extend(res.assignments)
        if progress:
            progress(f"{pass_name:<12} {len(got)}/{len(items)} assigned")

    def failed(batch, e):
        if progress:
            progress(f"[red]FAILED[/] {pass_name} batch of {len(batch)}: "
                     f"{type(e).__name__}: {e}")

    client.map(batches, work, on_result=ok, on_error=failed)

    known = {it["item_id"] for it in items}
    out = [
        {"item_id": a.item_id, "dim_id": back[a.dim_id],
         "polarity": 1 if a.polarity >= 0 else -1, "fit": a.fit}
        for a in got if a.dim_id in valid and a.item_id in known
    ]

    if persist:
        run_id = db.new_run_id("dimensions")
        with db.connect() as con:
            con.execute(
                "DELETE FROM item_dimensions WHERE dim_version=? AND bank_version=? "
                "AND pass_name=?", [dim_version, bank_version, pass_name],
            )
            for a in out:
                con.execute(
                    "INSERT INTO item_dimensions (dim_version, bank_version, item_id, "
                    "dim_id, polarity, fit, pass_name, run_id, model, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [dim_version, bank_version, a["item_id"], a["dim_id"],
                     a["polarity"], a["fit"], pass_name, run_id, client.model,
                     db.now()],
                )
    return out


def split_half(
    client, n_dims: int = 8, seed: int = 7, progress=None,
) -> dict[str, Any]:
    """Derive twice, from film sets that share no propositions.

    This is the audit that can most cleanly embarrass the taxonomy: if the two
    halves disagree, the axes came from the prompt rather than the corpus.
    Nothing is persisted — it is a test, not a layer.
    """
    with db.connect(read_only=True) as con:
        films = sorted({r["film_id"] for r in
                        con.execute("SELECT DISTINCT film_id FROM propositions_raw")})
    if len(films) < 4:
        raise RuntimeError("need at least 4 films with propositions to split")
    rng = random.Random(seed)
    shuffled = list(films)
    rng.shuffle(shuffled)
    half_a = set(shuffled[:len(shuffled) // 2])
    half_b = set(shuffled[len(shuffled) // 2:])
    if progress:
        progress(f"half A: {len(half_a)} films, half B: {len(half_b)} films (disjoint)")
    return {
        "seed": seed,
        "half_a_films": sorted(half_a),
        "half_b_films": sorted(half_b),
        "half_a": derive("_splithalf_a", client, n_dims, films=half_a,
                         persist=False, progress=progress),
        "half_b": derive("_splithalf_b", client, n_dims, films=half_b,
                         persist=False, progress=progress),
    }


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def cohens_kappa(a: dict[str, int], b: dict[str, int]) -> dict[str, Any]:
    """Agreement between two assignments, corrected for agreement by chance.

    Raw agreement flatters any labelling with one dominant category, which is
    exactly the failure mode here — an axis that swallowed half the bank would
    look reliable. Kappa prices that in.
    """
    both = [k for k in a if k in b]
    n = len(both)
    if not n:
        return {"n": 0, "agree": 0, "raw": None, "chance": None, "kappa": None}
    agree = sum(1 for k in both if a[k] == b[k])
    m1: dict[int, int] = defaultdict(int)
    m2: dict[int, int] = defaultdict(int)
    for k in both:
        m1[a[k]] += 1
        m2[b[k]] += 1
    p_obs = agree / n
    p_exp = sum((m1[c] / n) * (m2[c] / n) for c in set(m1) | set(m2))
    kappa = (p_obs - p_exp) / (1 - p_exp) if p_exp < 1 else None
    return {"n": n, "agree": agree, "raw": p_obs, "chance": p_exp, "kappa": kappa}


def _packets(
    bank_version: str, assignments: dict[str, dict[str, Any]],
    exclude_own_film: bool, source_films: dict[str, set[str]] | None,
    variants: Iterable[str] | None = None,
) -> dict[tuple[str, str], list[tuple[str, int]]]:
    """{(film, variant): [(item_id, value)]} for items that carry an assignment."""
    q = "SELECT film_id, variant, item_id, value FROM scores WHERE bank_version=?"
    args: list[Any] = [bank_version]
    with db.connect(read_only=True) as con:
        rows = con.execute(q, args).fetchall()
    keep = set(variants) if variants else None
    out: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    for r in rows:
        if r["item_id"] not in assignments:
            continue
        if keep and r["variant"] not in keep:
            continue
        if exclude_own_film and source_films is not None:
            if r["film_id"] in source_films.get(r["item_id"], set()):
                continue
        out[(r["film_id"], r["variant"])].append((r["item_id"], r["value"]))
    return out


def _co_engagement(packets, assign_map: dict[str, int]) -> float:
    """Share of co-engaged item pairs that sit on the same axis."""
    same = total = 0
    for pairs in packets.values():
        ds = [assign_map[i] for i, _v in pairs]
        for x in range(len(ds)):
            for y in range(x + 1, len(ds)):
                total += 1
                if ds[x] == ds[y]:
                    same += 1
    return same / total if total else 0.0


def _coherence(packets, assign_map: dict[str, int], polarity: dict[str, int],
               min_items: int = 3) -> tuple[float, int]:
    """Mean |net stance| over film x axis cells carrying at least `min_items`."""
    vals = []
    for pairs in packets.values():
        by: dict[int, list[int]] = defaultdict(list)
        for item, value in pairs:
            by[assign_map[item]].append(polarity[item] * value)
        for signs in by.values():
            if len(signs) >= min_items:
                vals.append(abs(sum(signs)) / len(signs))
    return (st.mean(vals) if vals else 0.0), len(vals)


def _permutation(observed: float, fn, item_ids: list[str], labels: list[int],
                 n: int, seed: int) -> dict[str, Any]:
    """Null: shuffle which item belongs to which axis, holding sizes fixed."""
    rng = random.Random(seed)
    null = []
    pool = list(labels)
    for _ in range(n):
        rng.shuffle(pool)
        null.append(fn(dict(zip(item_ids, pool))))
    mean, sd = st.mean(null), st.pstdev(null)
    return {
        "observed": observed,
        "null_mean": mean,
        "null_sd": sd,
        "z": (observed - mean) / sd if sd else None,
        "permutations": n,
        "n_at_least_observed": sum(1 for x in null if x >= observed),
    }


def validate(
    dim_version: str, bank_version: str, permutations: int = 1000,
    seed: int = 3, exclude_own_film: bool = True, threshold: float = 0.45,
    variants: Iterable[str] | None = None, progress=None,
) -> dict[str, Any]:
    """The whole battery, as data rather than as a claim.

    Everything here is deterministic given `seed`, so a number in a write-up can
    be reproduced by re-running the command that produced it.
    """
    dims = load_dimensions(dim_version)
    if not dims:
        raise RuntimeError(f"no dimension set {dim_version!r} — run `atlas dimensions`")
    main = load_assignments(dim_version, bank_version, MAIN_PASS)
    if not main:
        raise RuntimeError(f"no '{MAIN_PASS}' assignments for {dim_version}/{bank_version}")

    names = {d["dim_id"]: d["name"] for d in dims}
    fits = [a["fit"] for a in main.values()]
    sizes: dict[int, int] = defaultdict(int)
    for a in main.values():
        sizes[a["dim_id"]] += 1

    report: dict[str, Any] = {
        "dim_version": dim_version,
        "bank_version": bank_version,
        "seed": seed,
        "n_items": len(main),
        "coverage": {
            "median_fit": st.median(fits) if fits else None,
            "share_fit_ge_0_4": (sum(1 for f in fits if f >= 0.4) / len(fits)
                                 if fits else None),
            "sizes": {names[d]: sizes[d] for d in sorted(sizes)},
        },
        "agreement": {},
    }

    # -- agreement between passes (replicate, cross-model, anything else) ----
    main_dims = {i: a["dim_id"] for i, a in main.items()}
    main_pol = {i: a["polarity"] for i, a in main.items()}
    for pass_name, model, _n in list_passes(dim_version, bank_version):
        if pass_name == MAIN_PASS:
            continue
        other = load_assignments(dim_version, bank_version, pass_name)
        k = cohens_kappa(main_dims, {i: a["dim_id"] for i, a in other.items()})
        shared = [i for i in other if i in main]
        k["model"] = model
        k["polarity_agreement"] = (
            sum(1 for i in shared if other[i]["polarity"] == main_pol[i]) / len(shared)
            if shared else None
        )
        report["agreement"][pass_name] = k

    # -- behavioural tests against the scores -------------------------------
    source_films = item_source_films(bank_version, threshold) if exclude_own_film else None
    if source_films is not None:
        unmapped = sum(1 for i in main if not source_films.get(i))
        report["unmapped_items"] = unmapped
        if progress and unmapped:
            progress(f"[yellow]{unmapped} items had no source film — check that "
                     f"--threshold matches the bank[/]")

    packets = _packets(bank_version, main, exclude_own_film, source_films, variants)
    report["n_packets"] = len(packets)
    report["n_engagements"] = sum(len(p) for p in packets.values())

    if report["n_engagements"]:
        item_ids = list(main)
        labels = [main[i]["dim_id"] for i in item_ids]
        report["co_engagement"] = _permutation(
            _co_engagement(packets, main_dims),
            lambda a: _co_engagement(packets, a),
            item_ids, labels, permutations, seed,
        )
        obs_coh, n_cells = _coherence(packets, main_dims, main_pol)
        report["coherence"] = _permutation(
            obs_coh, lambda a: _coherence(packets, a, main_pol)[0],
            item_ids, labels, permutations, seed + 1,
        )
        report["coherence"]["n_cells"] = n_cells
        report["exclude_own_film"] = exclude_own_film
    return report


def film_profiles(
    dim_version: str, bank_version: str, top: int = 3,
    variants: Iterable[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Each film's strongest axes — the face-validity check, and the product view."""
    dims = load_dimensions(dim_version)
    names = {d["dim_id"]: d["name"] for d in dims}
    main = load_assignments(dim_version, bank_version, MAIN_PASS)
    packets = _packets(bank_version, main, False, None, variants)

    widest: dict[str, tuple[str, list[tuple[str, int]]]] = {}
    for (film, variant), pairs in packets.items():
        if film not in widest or len(pairs) > len(widest[film][1]):
            widest[film] = (variant, pairs)

    out: dict[str, list[dict[str, Any]]] = {}
    for film, (variant, pairs) in sorted(widest.items()):
        by: dict[int, list[int]] = defaultdict(list)
        for item, value in pairs:
            by[main[item]["dim_id"]].append(main[item]["polarity"] * value)
        rows = [
            {"dimension": names.get(d, str(d)), "dim_id": d,
             "net": sum(s) / len(s), "n_items": len(s), "variant": variant}
            for d, s in by.items()
        ]
        rows.sort(key=lambda r: -abs(r["net"] * r["n_items"]))
        out[film] = rows[:top]
    return out
