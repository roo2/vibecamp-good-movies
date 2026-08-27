"""Check every verdict against the reason the model gave for it.

Every verdict carries a one-line justification, written in the same reply that
chose the verdict. Usually they agree. Sometimes the model writes the reasoning
for one answer and records the other:

    "The belief in one's own superiority can lead to the oppression of others."
    verdict: strongly denies, confidence 0.95
    evidence: "The film ridicules the belief in superiority ... showing it
               leads to oppression and absurdity."

That justification affirms the proposition. The verdict denies it. Nothing
downstream can notice, because everything downstream reads the number and the
number is well-formed — a reader spotted this one on Life of Brian.

Audited at a few percent on a 120-verdict sample, which sounds ignorable and is
not. A flipped verdict does not merely add noise to one film's position: it
enters the correlation matrix with the wrong sign, so it actively pulls two
propositions apart that belong together. The axes that reproduce worst are
exactly where that would hurt most, so this is cheap insurance on the weakest
part of the result.

WHAT IT WILL AND WILL NOT DO. Only clear contradictions are corrected — the
auditor must say the justification supports the opposite verdict, not merely
that it is unclear. Ambiguity is counted and left alone, because a verdict the
auditor cannot read is not evidence that the original reader was wrong.

The original value is kept in `original_value` and the row is stamped, so a
correction is visible, reversible, and never silently overwrites the record of
what the scorer actually said.
"""
from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, Field

from .. import db

SYSTEM = """\
Each entry is a moral proposition, a verdict one reader recorded about one film,
and that reader's own one-line justification for it.

Your only question is whether the JUSTIFICATION SUPPORTS THE VERDICT. You are
not judging the film, you have not seen it, and whether the verdict is true of
the film is not what is being asked.

A justification saying the film SHOWS X leading to Y supports AFFIRMING "X leads
to Y". Recording that as a denial is the error being looked for — it is the
reasoning for one answer written beside the other.

Be conservative. `supports` is false only when the justification plainly argues
the opposite verdict. If the justification is vague, or describes the subject
without taking a side, or you cannot tell, set supports=true and reads_as
"unclear": a justification you cannot read is not evidence the reader was wrong.
"""


class Judgement(BaseModel):
    n: int = Field(description="The entry number, exactly as given.")
    supports: bool = Field(description="Does the justification support the recorded verdict?")
    reads_as: str = Field(description="What the justification actually argues: "
                                      "affirms, denies, or unclear.")


class Judgements(BaseModel):
    judgements: list[Judgement]


def pending(scorer: str, bank_version: str, variant: str,
            limit: int | None = None, redo: bool = False) -> list[dict[str, Any]]:
    """Verdicts with a justification long enough to be worth reading."""
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT v.film_id, v.item_id, v.value, v.evidence, i.text "
            "FROM model_verdicts v JOIN item_bank i "
            "  ON i.item_id = v.item_id AND i.bank_version = v.bank_version "
            "WHERE v.scorer=? AND v.bank_version=? AND v.variant=? "
            "  AND v.evidence IS NOT NULL AND length(v.evidence) > 25 "
            + ("" if redo else "AND v.audited_at IS NULL ")
            + ("LIMIT " + str(int(limit)) if limit else ""),
            [scorer, bank_version, variant],
        ).fetchall()
    return [dict(r) for r in rows]


def _block(batch: list[dict[str, Any]], offset: int) -> str:
    lines = []
    for n, row in enumerate(batch, offset + 1):
        verdict = "affirms" if row["value"] > 0 else "denies"
        if abs(row["value"]) > 1:
            verdict += " (strongly)"
        lines.append(f"{n}. PROPOSITION: {row['text']}\n"
                     f"   VERDICT: {verdict}\n"
                     f"   JUSTIFICATION: {row['evidence'][:220]}")
    return "\n".join(lines)


def audit(scorer: str, bank_version: str, variant: str, client,
          batch_size: int = 40, limit: int | None = None,
          apply: bool = False, redo: bool = False, progress=None) -> dict[str, int]:
    """Read every verdict against its own justification; optionally correct."""
    rows = pending(scorer, bank_version, variant, limit=limit, redo=redo)
    stats = {"checked": 0, "contradicted": 0, "corrected": 0, "unreadable": 0}
    if not rows:
        return stats

    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        try:
            result = client.parse(system=SYSTEM, user=_block(batch, start),
                                  output_model=Judgements, max_tokens=8000)
        except Exception as error:            # a bad batch must not lose the run
            if progress:
                progress(f"  batch at {start} failed: {type(error).__name__}")
            continue

        corrections = []
        for judgement in result.judgements:
            index = judgement.n - start - 1
            if not 0 <= index < len(batch):
                continue
            row = batch[index]
            stats["checked"] += 1
            reads = (judgement.reads_as or "").strip().lower()
            if judgement.supports:
                continue
            if reads not in ("affirms", "denies"):
                # Flagged as unsupported without saying what it supports
                # instead. Counted, never acted on.
                stats["unreadable"] += 1
                continue
            wanted = 1 if reads == "affirms" else -1
            if (row["value"] > 0) == (wanted > 0):
                continue
            stats["contradicted"] += 1
            # Magnitude is kept: the reader's confidence in HOW FIRMLY the film
            # holds the position is not what was contradicted, only which way.
            corrections.append((row["film_id"], row["item_id"],
                                -row["value"], row["value"]))

        if corrections and apply:
            with db.connect() as con:
                con.executemany(
                    "UPDATE model_verdicts SET value=?, original_value=?, "
                    "audited_at=? WHERE scorer=? AND bank_version=? AND variant=? "
                    "AND film_id=? AND item_id=?",
                    [(new, old, db.now(), scorer, bank_version, variant, film, item)
                     for film, item, new, old in corrections],
                )
            stats["corrected"] += len(corrections)

        if apply:
            with db.connect() as con:
                con.executemany(
                    "UPDATE model_verdicts SET audited_at=? WHERE scorer=? AND "
                    "bank_version=? AND variant=? AND film_id=? AND item_id=? "
                    "AND audited_at IS NULL",
                    [(db.now(), scorer, bank_version, variant, r["film_id"], r["item_id"])
                     for r in batch],
                )
        if progress and (start // batch_size) % 10 == 0:
            progress(f"  {stats['checked']} checked, {stats['contradicted']} contradicted")
    return stats
