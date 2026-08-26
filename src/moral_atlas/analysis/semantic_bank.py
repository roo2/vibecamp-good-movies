"""Cut the harvest into an item bank by meaning rather than by wording.

WHAT WAS WRONG WITH THE LEXICAL CUT. `bank.cluster_propositions` scores
similarity with TF-IDF over word and character n-grams, which measures shared
vocabulary. Two consequences were measured on the deepseek harvest:

  Over-merge. The largest cluster held 25 propositions including both "the ends
  justify the means when the end is the collective good" and "the ends do not
  justify immoral means" — opposite claims, merged because they share four
  words. `build_bank` then canonicalised the cluster from its REPRESENTATIVE
  alone, never seeing the members, so what reached the bank was a hedge:
  "whether the ends justify the means depends on the justness of the cause."
  It carried the highest support in the bank and almost no power to separate
  films, because nearly every film affirms it.

  Under-merge. "Redemption" survived as seven near-duplicate items, because the
  same claim phrased in different words has little vocabulary in common.

WHY NOT JUST SWAP IN EMBEDDINGS. Because they do not solve the half of the
problem that matters most. Measured on the pairs above, all-MiniLM-L6-v2 scores
the two OPPOSITE claims at 0.59 and puts the same claim reworded at 0.38 — the
wrong way round. Sentence embedders encode what a sentence is ABOUT, not what it
asserts; a static model (potion-base-8M) was worse still at 0.70 versus 0.39.
There is no threshold that fixes this, so nothing here asks an embedder to
decide whether two claims are the same.

THE ARRANGEMENT THAT DOES WORK. Each stage is given the job it is good at:

  1. Embeddings propose TOPICAL neighbourhoods — what these models are reliable
     at, and it is only a recall step, so a generous threshold is correct.
  2. `bank.polarity_class` blocks the neighbourhoods, so a negation and an
     assertion can never land in the same group whatever the geometry says.
  3. A model reads the neighbourhood's MEMBER SENTENCES and returns the distinct
     claims it actually contains — one, or several. This is the step the old
     pipeline had no equivalent of: deciding sameness is a judgement about
     meaning, and it is made by the only component that can read.

So a neighbourhood is a question put to the model, not a decision already taken.
Merging and splitting are the same operation here, which is why an over-merged
cluster and an under-merged pair are both repaired by one pass.

Support is recorded but not used to drop anything: how many films happened to
PHRASE a claim similarly is not evidence about the claim. Whether an item can
separate films is decided after scoring, by `latent.MIN_FILMS_PER_ITEM`, on the
verdicts themselves.
"""
from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, Field

from .. import db
from . import bank as lexical

# Small, CPU-only, and used solely to propose neighbourhoods — nothing about the
# result depends on it being a strong model, because it never decides sameness.
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Cosine DISTANCE for agglomerative linkage. Deliberately generous: a
# neighbourhood that is too broad costs a few tokens when the model splits it,
# while one that is too narrow hides a duplicate the model never gets to see.
NEIGHBOUR_DISTANCE = 0.45

# How many member sentences the model is shown. Long enough to see the spread of
# a real cluster, short enough that the judgement stays sharp.
MAX_MEMBERS_SHOWN = 18


class Claim(BaseModel):
    text: str = Field(
        description="One canonical moral proposition: a general claim about how to "
                    "live or how the world is morally ordered. No proper nouns, no "
                    "plot specifics. Phrased so a thoughtful person on EITHER side "
                    "would accept it as a fair statement of the question.")
    members: list[int] = Field(
        description="Line numbers from the supplied list that assert THIS claim.")


class ClaimSet(BaseModel):
    claims: list[Claim] = Field(
        description="Every distinct claim present in the group. One if they all "
                    "assert the same thing; several if they do not.")
    discard: list[int] = Field(
        default_factory=list,
        description="Line numbers that are not moral propositions at all — plot "
                    "summary, genre observation, a remark about craft.")


SPLIT_SYSTEM = """\
You are building a fixed measuring instrument out of moral propositions
harvested from films, and your job on each group is to decide how many DISTINCT
claims it contains.

These sentences were grouped because software found them similar. That software
matches subject matter, not meaning, so a group routinely contains claims that
argue with each other. Treat the grouping as a question, never as an answer.

TWO SENTENCES ARE THE SAME CLAIM only when a film could not possibly affirm one
and deny the other. Same topic is not the same claim.

  Same claim, different words — return ONE:
    "A person should be judged by what they do, not where they were born."
    "An individual's worth rests on their actions rather than their social rank."

  Same topic, opposing claims — return TWO, one for each side:
    "The ends justify the means when the end is the collective good."
    "The ends do not justify immoral means."

  Same words, different claims — return TWO:
    "Sacrifice for the greater good is noble."
    "Deception is justified when it serves a greater good."

DO NOT HEDGE. When a group holds both sides of a question, the answer is two
opposed propositions — never one compromise sentence that concedes both. A
proposition beginning "whether X depends on..." is a failure: nearly every film
affirms it, so it measures nothing. Write the claim each side actually makes.

STATE EACH CLAIM POSITIVELY, so that a film can affirm or deny it, and never
build the verdict into the wording. Assign every line to exactly one claim, or
to `discard` if it is not a moral proposition at all.
"""


def embed(texts: list[str]):
    """Unit-normalised sentence vectors. Imported lazily: torch is a heavy import."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBED_MODEL)
    return model.encode(list(texts), normalize_embeddings=True,
                        batch_size=128, show_progress_bar=False)


def neighbourhoods(rows: list[Any], distance: float = NEIGHBOUR_DISTANCE,
                   progress=None) -> list[dict[str, Any]]:
    """Topical groups, blocked so polarity can never be crossed.

    Clustering runs INSIDE each polarity class rather than over everything at
    once. Doing it globally and repairing afterwards is what the lexical
    pipeline attempted, and a repair step cannot recover a distinction the
    geometry has already dissolved.
    """
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    texts = [r["text"] for r in rows]
    if progress:
        progress(f"embedding {len(texts)} propositions")
    vectors = embed(texts)

    blocks: dict[str, list[int]] = {}
    for i, text in enumerate(texts):
        blocks.setdefault(lexical.polarity_class(text), []).append(i)

    groups: list[dict[str, Any]] = []
    for polarity, index in sorted(blocks.items()):
        if len(index) == 1:
            groups.append({"polarity": polarity, "members": [rows[index[0]]]})
            continue
        sub = np.asarray([vectors[i] for i in index])
        labels = AgglomerativeClustering(
            n_clusters=None, distance_threshold=distance,
            metric="cosine", linkage="average",
        ).fit_predict(sub)
        by_label: dict[int, list[int]] = {}
        for position, label in enumerate(labels):
            by_label.setdefault(int(label), []).append(index[position])
        for label in sorted(by_label):
            groups.append({"polarity": polarity,
                           "members": [rows[i] for i in by_label[label]]})
        if progress:
            progress(f"  {polarity:<8} {len(index):>5} propositions → {len(by_label)} neighbourhoods")
    return groups


def _listing(members: list[Any]) -> str:
    return "\n".join(f"{n}. {m['text']}" for n, m in enumerate(members[:MAX_MEMBERS_SHOWN], 1))


def _films_of(row: dict[str, Any]) -> set[str]:
    """Which films stand behind a row, whether it is a proposition or a claim."""
    if row.get("films"):
        return set(row["films"])
    return {row["film_id"]} if row.get("film_id") else set()


def distinct_claims(group: dict[str, Any], client) -> list[dict[str, Any]]:
    """Ask the model what claims this neighbourhood actually contains."""
    members = group["members"][:MAX_MEMBERS_SHOWN]
    if len(members) == 1:
        only = members[0]
        films = _films_of(only)
        return [{"text": only["text"], "support": max(len(films), 1),
                 "films": films, "polarity": group["polarity"]}]

    result = client.parse(
        system=SPLIT_SYSTEM,
        user=f"Group of {len(members)} sentences:\n\n{_listing(members)}",
        output_model=ClaimSet,
        max_tokens=4000,
    )
    out: list[dict[str, Any]] = []
    for claim in result.claims:
        picked = [members[n - 1] for n in claim.members if 1 <= n <= len(members)]
        if not claim.text.strip():
            continue
        films: set[str] = set()
        for m in picked:
            films |= _films_of(m)
        out.append({
            "text": claim.text.strip(),
            # Support counts distinct FILMS, not sentences: two propositions
            # from one film are one film's opinion however they are worded.
            "films": films,
            "support": len(films),
            "polarity": group["polarity"],
        })
    return out


def consolidate(claims: list[dict[str, Any]], client,
                distance: float = NEIGHBOUR_DISTANCE, progress=None) -> list[dict[str, Any]]:
    """A second pass over the claims, because the first one only sees locally.

    Each neighbourhood is adjudicated on its own, so a claim in one and its twin
    in another never meet — which is why the first pass left sixteen separate
    items about revenge, several of them saying the same thing. Re-embedding the
    OUTPUT and adjudicating again puts those twins in the same group, and the
    same "are these one claim or several?" question resolves them.

    This does not simply shrink the bank. The pass is free to split as well as
    merge, and both are the same operation: it is asked what is there, not to
    reduce anything.
    """
    rows = [{"text": c["text"], "films": _films_of(c), "film_id": None} for c in claims]
    groups = neighbourhoods(rows, distance, progress=progress)
    plural = [g for g in groups if len(g["members"]) > 1]
    if progress:
        progress(f"consolidating: {len(groups)} neighbourhoods, {len(plural)} to re-read")

    out: list[dict[str, Any]] = []
    done = 0
    for g in groups:
        try:
            out.extend(distinct_claims(g, client))
        except Exception as error:
            if progress:
                progress(f"  group of {len(g['members'])} failed: {error}")
            out.extend({"text": m["text"], "films": _films_of(m),
                        "support": max(len(_films_of(m)), 1), "polarity": g["polarity"]}
                       for m in g["members"])
        if len(g["members"]) > 1:
            done += 1
            if progress and done % 25 == 0:
                progress(f"  re-read {done}/{len(plural)} — {len(out)} claims so far")
    return out


def build(rows: list[Any], client, distance: float = NEIGHBOUR_DISTANCE,
          progress=None) -> dict[str, Any]:
    """Harvest -> distinct claims. Returns a report; writes nothing."""
    groups = neighbourhoods(rows, distance, progress=progress)
    singles = [g for g in groups if len(g["members"]) == 1]
    plural = [g for g in groups if len(g["members"]) > 1]
    if progress:
        progress(f"{len(groups)} neighbourhoods ({len(plural)} to adjudicate, "
                 f"{len(singles)} single-member)")

    claims: list[dict[str, Any]] = []
    for g in singles:
        claims.extend(distinct_claims(g, client))

    done = 0
    for g in plural:
        try:
            claims.extend(distinct_claims(g, client))
        except Exception as error:            # a bad group must not lose the run
            if progress:
                progress(f"  group of {len(g['members'])} failed: {error}")
            claims.extend({"text": m["text"], "films": {m["film_id"]},
                           "support": 1, "polarity": g["polarity"]}
                          for m in g["members"])
        done += 1
        if progress and done % 25 == 0:
            progress(f"  adjudicated {done}/{len(plural)} — {len(claims)} claims so far")

    return {
        "n_propositions": len(rows),
        "n_neighbourhoods": len(groups),
        "n_adjudicated": len(plural),
        "n_claims": len(claims),
        "claims": claims,
    }


def build_unreduced(rows: list[Any], sample: int | None = None,
                    distance: float = NEIGHBOUR_DISTANCE,
                    seed: int = 11, progress=None) -> dict[str, Any]:
    """Every distinct proposition as its own item, labelled with its neighbourhood.

    The alternative to merging, and the reason it is worth preferring: deciding
    that two propositions are "the same" is the factor analysis's job, and it
    makes that decision from how films RESPOND rather than from how the
    sentences read. Merging beforehand pre-empts it with a weaker criterion
    applied before any evidence exists — and near-duplicate items are not a
    problem for factor analysis, they are confirmation. Two items that load on
    one factor are evidence the factor is there; collapsing them first replaces
    that evidence with an assumption.

    Measured on the deepseek harvest, the case is not close: of 2,392
    propositions only 5 were exact duplicates, so the old cut from 2,392 to 298
    was 87% judgement rather than deduplication, and one of those judgements
    produced the highest-support item in the bank — a hedge nearly every film
    affirms.

    So the neighbourhood is kept as a LABEL rather than applied as a merge. That
    turns an unfalsifiable decision into a prediction: if the factor analysis
    independently groups items that share a neighbourhood, both methods are
    corroborated; if it does not, the statistics win and nothing was lost.

    `sample` takes a random subset, for pilots where scoring the whole bank is
    not worth the money. Random rather than one-per-neighbourhood on purpose:
    picking a representative is the merge this exists to avoid, and redundancy
    is part of what a faithful miniature has to keep.
    """
    import numpy as np

    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = lexical._normalise(row["text"])
        if key and key not in seen:
            seen[key] = row
    unique = list(seen.values())
    if progress:
        progress(f"{len(rows)} propositions, {len(unique)} distinct "
                 f"({len(rows) - len(unique)} exact duplicates)")

    if sample and sample < len(unique):
        rng = np.random.default_rng(seed)
        unique = [unique[i] for i in
                  sorted(rng.choice(len(unique), sample, replace=False))]
        if progress:
            progress(f"sampled {len(unique)} for the pilot")

    groups = neighbourhoods(unique, distance, progress=progress)
    label: dict[int, int] = {}
    polarity: dict[int, str] = {}
    for index, group in enumerate(groups):
        for member in group["members"]:
            label[id(member)] = index
            polarity[id(member)] = group["polarity"]

    items = [{"item_id": f"I{n:04d}", "text": row["text"],
              "cluster_id": label.get(id(row), -1), "support": 1, "active": True,
              "note": f"{polarity.get(id(row), '')}|{row['film_id']}"}
             for n, row in enumerate(unique, 1)]
    return {"items": items, "n_propositions": len(rows),
            "n_distinct": len(seen), "n_neighbourhoods": len(groups)}


def write_bank(bank_version: str, claims: list[dict[str, Any]],
               model: str | None, run_id: str) -> dict[str, int]:
    """Persist claims as an item bank, in the shape the rest of the pipeline reads."""
    items = [{"item_id": f"I{n:04d}", "text": c["text"], "cluster_id": n,
              "support": c["support"], "active": True, "note": c.get("polarity", "")}
             for n, c in enumerate(sorted(claims, key=lambda c: -c["support"]), 1)]
    return lexical._write_items(bank_version, items, model, run_id)


def harvest(scorer: str, variant: str) -> list[dict[str, Any]]:
    """The model's own propositions, as plain dicts."""
    return [{"prop_id": r["prop_id"], "film_id": r["film_id"], "text": r["text"],
             "stance": r["stance"]}
            for r in lexical.model_propositions(scorer, variant)]
