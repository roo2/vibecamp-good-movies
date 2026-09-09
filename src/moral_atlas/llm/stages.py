"""The three LLM stages, each writing versioned rows into the store."""
from __future__ import annotations

import json
import uuid
from typing import Any, Iterable

from .. import db
from ..config import PROMPT_VERSION
from ..sources import packet as packet_mod
from . import prompts
from .client import LLMClient
from .schemas import FilmDescription, MoralSkeleton, PropositionSet, ScoreSet


def _user_block(p: packet_mod.Packet, extra: str = "") -> str:
    missing = (
        f"\nLAYERS DELIBERATELY WITHHELD IN THIS CONDITION: "
        f"{', '.join(p.layers_missing)}\n" if p.layers_missing else "\n"
    )
    return (
        f"FILM IDENTIFIERS\n{p.header}\n"
        f"EVIDENCE CONDITION: {p.variant} "
        f"(layers supplied: {', '.join(p.layers_present) or 'none'})"
        f"{missing}{extra}\n"
        f"===== EVIDENCE =====\n\n{p.body}\n"
    )


# --------------------------------------------------------------------------
# Stage 1 — moral skeleton
# --------------------------------------------------------------------------

def extract_skeletons(
    film_ids: Iterable[str], variants: Iterable[str],
    client: LLMClient, progress=None,
) -> str:
    jobs = [
        packet_mod.build(fid, v)
        for fid in film_ids for v in variants
    ]
    jobs = [p for p in jobs if p.usable]

    run_id = db.start_run(
        "skeleton", client.model, PROMPT_VERSION,
        {"variants": list(variants), "n_jobs": len(jobs)},
    )

    def work(p: packet_mod.Packet) -> tuple[packet_mod.Packet, MoralSkeleton]:
        sk = client.parse(
            system=prompts.SKELETON_SYSTEM,
            user=_user_block(p),
            output_model=MoralSkeleton,
            max_tokens=16000,
        )
        return p, sk

    def save(_p, res) -> None:
        p, sk = res
        with db.connect() as con:
            con.execute(
                db.upsert("skeletons", ["film_id", "variant", "run_id", "data",
                                        "model", "prompt_version", "created_at"]),
                [p.film_id, p.variant, run_id, sk.model_dump_json(),
                 client.model, PROMPT_VERSION, db.now()],
            )
        if progress:
            progress(f"skeleton  {p.film_id:<28} {p.variant}")

    def failed(p, e) -> None:
        if progress:
            progress(f"FAILED    {p.film_id:<28} {p.variant}  {type(e).__name__}: {e}")

    client.map(jobs, work, on_result=save, on_error=failed)
    db.finish_run(run_id, client.usage.as_dict())
    return run_id


# --------------------------------------------------------------------------
# Stage 2 — free-form proposition generation
# --------------------------------------------------------------------------

def generate_propositions(
    film_ids: Iterable[str], client: LLMClient,
    variant: str = "full", progress=None,
) -> str:
    """Generate the raw statement pool the item bank is cut from.

    Run on the richest variant available: we want the widest possible vocabulary
    here. Which propositions survive on *thin* evidence is a separate question,
    answered later by scoring, not by generation.
    """
    run_id = db.start_run(
        "propositions", client.model, PROMPT_VERSION, {"variant": variant},
    )

    jobs = []
    for fid in film_ids:
        p = packet_mod.build(fid, variant)
        if not p.usable:
            p = packet_mod.build(fid, "spine")
        if p.usable:
            jobs.append(p)

    def work(p: packet_mod.Packet):
        skeleton = _latest_skeleton(p.film_id, p.variant) or _latest_skeleton(p.film_id)
        extra = (
            f"\nMORAL SKELETON ALREADY EXTRACTED FROM THIS EVIDENCE:\n"
            f"{json.dumps(skeleton, indent=2)}\n" if skeleton else ""
        )
        ps = client.parse(
            system=prompts.PROPOSITIONS_SYSTEM,
            user=_user_block(p, extra),
            output_model=PropositionSet,
            max_tokens=16000,
        )
        return p, ps

    def save(_p, res) -> None:
        p, ps = res
        with db.connect() as con:
            for prop in ps.propositions:
                con.execute(
                    db.upsert("propositions_raw", ["prop_id", "film_id", "variant",
                                                   "run_id", "text", "stance", "evidence",
                                                   "model", "prompt_version", "created_at"]),
                    [uuid.uuid4().hex[:16], p.film_id, p.variant, run_id,
                     prop.text, prop.stance, prop.evidence, client.model,
                     PROMPT_VERSION, db.now()],
                )
        if progress:
            progress(f"propose   {p.film_id:<28} {len(ps.propositions)} statements")

    def failed(p, e) -> None:
        if progress:
            progress(f"FAILED    {p.film_id:<28} {type(e).__name__}: {e}")

    client.map(jobs, work, on_result=save, on_error=failed)
    db.finish_run(run_id, client.usage.as_dict())
    return run_id


# --------------------------------------------------------------------------
# Stage 3 — score films against the item bank
# --------------------------------------------------------------------------

def score_films(
    film_ids: Iterable[str], variants: Iterable[str], bank_version: str,
    client: LLMClient, progress=None,
) -> str:
    items = _load_bank(bank_version)
    if not items:
        raise RuntimeError(f"item bank {bank_version!r} is empty — run `atlas bank` first")

    # Byte-identical across every call in the run: this is the cache prefix,
    # and it is most of the reason a full sweep costs tens rather than hundreds.
    bank_block = "\n".join(f"{i['item_id']}. {i['text']}" for i in items)
    system = prompts.scoring_system(bank_block)

    jobs = [packet_mod.build(fid, v) for fid in film_ids for v in variants]
    jobs = [p for p in jobs if p.usable]

    run_id = db.start_run(
        "scoring", client.model, PROMPT_VERSION,
        {"bank_version": bank_version, "n_items": len(items),
         "variants": list(variants), "n_jobs": len(jobs)},
    )
    valid_ids = {i["item_id"] for i in items}

    def work(p: packet_mod.Packet):
        ss = client.parse(
            system=system,
            user=_user_block(p),
            output_model=ScoreSet,
            max_tokens=16000,
        )
        return p, ss

    def save(_p, res) -> None:
        p, ss = res
        kept = 0
        with db.connect() as con:
            for sc in ss.scores:
                if sc.item_id not in valid_ids:
                    continue  # hallucinated id — drop rather than store
                con.execute(
                    db.upsert("scores", ["film_id", "item_id", "bank_version", "variant",
                                         "run_id", "value", "confidence", "evidence",
                                         "model", "prompt_version"]),
                    [p.film_id, sc.item_id, bank_version, p.variant, run_id,
                     1 if sc.verdict == "affirms" else -1, sc.confidence, sc.evidence,
                     client.model, PROMPT_VERSION],
                )
                kept += 1
        if progress:
            progress(f"score     {p.film_id:<28} {p.variant:<13} {kept}/{len(items)} engaged")

    def failed(p, e) -> None:
        if progress:
            progress(f"FAILED    {p.film_id:<28} {p.variant}  {type(e).__name__}: {e}")

    client.map(jobs, work, on_result=save, on_error=failed)
    db.finish_run(run_id, client.usage.as_dict())
    return run_id


# --------------------------------------------------------------------------

def _latest_skeleton(film_id: str, variant: str | None = None) -> dict[str, Any] | None:
    q = ("SELECT data FROM skeletons WHERE film_id=%s "
         + ("AND variant=%s " if variant else "")
         + "ORDER BY created_at DESC LIMIT 1")
    args = [film_id] + ([variant] if variant else [])
    with db.connect(read_only=True) as con:
        row = con.execute(q, args).fetchone()
    return json.loads(row[0]) if row else None


def _load_bank(bank_version: str) -> list[dict[str, Any]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, text FROM item_bank "
            "WHERE bank_version=%s AND active ORDER BY item_id",
            [bank_version],
        ).fetchall()
    return [{"item_id": r[0], "text": r[1]} for r in rows]


# --------------------------------------------------------------------------
# Blind story descriptions
# --------------------------------------------------------------------------

# The house style, enforced rather than requested. Every one of these was a rule
# a model broke on the first fifty-film pass.
#
# The fifty hand-written cards run 12 to 20 words, which is what the prompt asks
# for. The check allows 22, because a card rejected for a single word over is a
# good sentence thrown away and a second call bought — and the retry that
# follows a length rejection reliably comes back shorter AND flatter, having
# spent its attention on the word count rather than on the choice.
MIN_WORDS, MAX_WORDS = 11, 22

_VERDICT_WORDS = {
    "heroic", "heroically", "bravely", "cowardly", "wrongly", "rightly", "evil",
    "villainous", "noble", "nobly", "finally", "ultimately", "triumphs",
    "redeems himself", "redeems herself", "learns that he", "learns that she",
    "in the end",
}
_CRITIC_WORDS = {
    "subverts", "subversion", "narrative", "allegory", "allegorical", "themes",
    "meditation", "coming-of-age", "deconstructs", "explores", "examines",
    "poignant", "iconic", "acclaimed", "masterpiece",
}


def _proper_nouns(sentence: str) -> list[str]:
    """Capitalised words that are not sentence-initial.

    Crude on purpose. It over-reports (a sentence starting a clause after a
    dash) and the caller treats a hit as a retry prompt rather than a verdict,
    so a false positive costs one call and a missed name costs a leaked title.
    """
    import re
    words = re.findall(r"[A-Za-z][\w'-]*", sentence)
    return [w for i, w in enumerate(words)
            if i > 0 and w[0].isupper() and w not in {"I", "A"}]


def describe_problems(sentence: str, title: str) -> list[str]:
    """Every house-style rule this sentence breaks, in words the model can act on."""
    import re
    problems = []
    text = sentence.strip()
    words = text.split()
    if not text:
        return ["it is empty"]
    if len(words) < MIN_WORDS:
        problems.append(f"it is {len(words)} words; the card needs at least {MIN_WORDS}")
    if len(words) > MAX_WORDS:
        problems.append(f"it is {len(words)} words; the card allows at most {MAX_WORDS}")
    if not text.endswith("."):
        problems.append("it does not end in a full stop")
    if re.search(r"[.!?]\s+\S", text):
        problems.append("it is more than one sentence")
    names = _proper_nouns(text)
    if names:
        problems.append(f"it names {', '.join(sorted(set(names)))} — the card names nothing")
    # Two words, not one. The first version of this rule flagged any title word
    # over three letters and rejected three of the fifty hand-written cards —
    # "bicycle" in Bicycle Thieves, "life" in It's a Wonderful Life, "pride" in
    # Pride & Prejudice. Those are ordinary nouns doing ordinary work; what
    # gives a film away is the title's PHRASE coming back, and names are already
    # caught above.
    title_words = {w.lower().strip(":,'") for w in title.split() if len(w) > 3}
    hit = sorted(title_words & {w.lower().strip(".,'") for w in words})
    if len(hit) > 1:
        problems.append(f"it reuses the title's own words ({', '.join(hit)})")
    low = f" {text.lower()} "
    for banned, label in ((_VERDICT_WORDS, "it rates or resolves the story"),
                          (_CRITIC_WORDS, "it uses criticism vocabulary")):
        found = sorted(w for w in banned if f" {w} " in low or f" {w}," in low)
        if found:
            problems.append(f"{label} ({', '.join(found)})")
    return problems


def _describe_evidence(film: dict[str, Any], require_plot: bool = True) -> tuple[str, str] | None:
    """The text one card is written from, and which layer it came from.

    Plot first: it is six hundred editorially neutral words and it is what the
    card is a compression of. Where Wikipedia has no plot section, the opening
    and closing of the dialogue track stands in — enough to see the situation
    set up and the pressure it comes under, without paying for 20,000 words.
    """
    from ..sources import subtitles as subs_mod

    evidence = db.get_evidence(film["film_id"])
    plot = (evidence.get("plot") or "").strip()
    if plot:
        return plot[:12000], "plot"
    if require_plot:
        return None
    track = (evidence.get("subtitles") or "").strip()
    if track:
        cues = subs_mod.parse_any(track)
        if cues:
            opening = subs_mod.cues_to_text(subs_mod.slice_by_position(cues, 0.0, 0.12))
            middle = subs_mod.cues_to_text(subs_mod.slice_by_position(cues, 0.45, 0.55))
            return (f"[OPENING 12%]\n{opening[:6000]}\n\n[MIDDLE]\n{middle[:3000]}",
                    "subtitles")
    return None


def describe_films(
    film_ids: Iterable[str], client: LLMClient,
    overwrite: bool = False, require_plot: bool = True, progress=None,
) -> tuple[str, dict[str, int]]:
    """Write the blind story card for films that have no hand-written one.

    Curated descriptions are never touched. `films.description_source` records
    which is which, so a generated card can be found, audited and replaced by a
    hand-written one later without hunting for it.

    `require_plot` holds the corpus to one evidence tier. A card written from
    the opening and middle of a dialogue track is a guess at a film's situation;
    a card written from the plot section is a compression of one. Mixing the two
    silently would put both in the same deck under the same name, so the weaker
    tier has to be asked for. Run `atlas backfill-plots` first and there is
    usually nothing left to ask for.
    """
    run_id = db.start_run("describe", client.model, PROMPT_VERSION,
                          {"overwrite": overwrite, "require_plot": require_plot})
    stats = {"written": 0, "skipped": 0, "no_evidence": 0, "failed": 0, "retried": 0}

    jobs = []
    for film_id in film_ids:
        film = db.get_film(film_id)
        if film is None:
            continue
        has = bool((film.get("description") or "").strip())
        curated = (film.get("description_source") or "curated") == "curated"
        if has and (curated or not overwrite):
            stats["skipped"] += 1
            continue
        got = _describe_evidence(film, require_plot=require_plot)
        if got is None:
            stats["no_evidence"] += 1
            if progress:
                progress(f"[dim]no evidence[/] {film['title']}")
            continue
        jobs.append((film, got[0], got[1]))

    def work(job):
        film, evidence, layer = job
        year = film.get("year") or "unknown year"
        user = (
            f"EVIDENCE ({layer}) for a {year} film. Write its card.\n\n"
            f"===== EVIDENCE =====\n\n{evidence}\n"
        )
        result = client.parse(
            system=prompts.DESCRIBE_SYSTEM, user=user,
            output_model=FilmDescription, max_tokens=4000,
        )
        problems = describe_problems(result.description, film["title"])
        if problems:
            stats["retried"] += 1
            result = client.parse(
                system=prompts.DESCRIBE_SYSTEM,
                user=user + (
                    f"\nYOUR FIRST ATTEMPT WAS REJECTED.\n\nYou wrote:\n"
                    f"{result.description}\n\nIt breaks the house style: "
                    f"{'; '.join(problems)}. Write it again, keeping the same "
                    f"situation and the same restraint about the ending.\n"
                ),
                output_model=FilmDescription, max_tokens=4000,
            )
            problems = describe_problems(result.description, film["title"])
        return film, result.description.strip(), layer, problems

    def save(_job, res) -> None:
        film, description, layer, problems = res
        if problems:
            stats["failed"] += 1
            if progress:
                progress(f"[yellow]REJECTED[/] {film['title']}: {'; '.join(problems)}\n"
                         f"          {description}")
            return
        db.set_film_description(film["film_id"], description)
        db.set_film_description_source(
            film["film_id"], f"generated:{client.model}:{PROMPT_VERSION}:{layer}")
        stats["written"] += 1
        if progress:
            progress(f"{film['title'][:34]:<36} {description}")

    def failed(job, error) -> None:
        stats["failed"] += 1
        if progress:
            progress(f"[red]FAILED[/] {job[0]['title']}: {type(error).__name__}: {error}")

    client.map(jobs, work, on_result=save, on_error=failed)
    db.finish_run(run_id, client.usage.as_dict())
    return run_id, stats
