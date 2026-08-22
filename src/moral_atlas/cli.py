"""atlas — command line for the Moral Atlas pipeline."""
from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import db
from .analysis import ab as ab_mod
from .analysis import bank as bank_mod
from .config import settings
from .sources import ingest as ingest_mod
from .sources import packet as packet_mod

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

DEFAULT_VARIANTS = "spine,spine_themes,subs,full"


def _client():
    from .llm.client import LLMClient
    try:
        return LLMClient()
    except RuntimeError as e:
        console.print(f"[red]{e}[/]")
        console.print("[dim]Everything up to `atlas status` runs without it.[/]")
        raise typer.Exit(1) from None


def _film_ids(limit: Optional[int] = None) -> list[str]:
    ids = [f["film_id"] for f in db.list_films()]
    return ids[:limit] if limit else ids


@app.command()
def init() -> None:
    """Create the database and report which credentials are present."""
    db.init_db()
    s = settings()
    console.print(f"[green]database ready[/] {s.db_path}")

    table = Table("credential", "status", "unlocks", box=None)
    table.add_row("ANTHROPIC_API_KEY", "[green]set[/]" if s.has_anthropic else "[red]missing[/]",
                  "all LLM stages")
    table.add_row("TMDB", "[green]set[/]" if s.has_tmdb else "[yellow]missing[/]",
                  "metadata + confound covariates")
    table.add_row("OpenSubtitles key", "[green]set[/]" if s.has_opensubtitles else "[yellow]missing[/]",
                  "subtitle search")
    table.add_row("OpenSubtitles login", "[green]set[/]" if s.can_download_subtitles else "[yellow]missing[/]",
                  "subtitle download")
    table.add_row("SUBTITLES_DIR", "[green]set[/]" if s.subtitles_dir else "[dim]unset[/]",
                  "hand-supplied .srt files (bypasses the API)")
    console.print(table)
    console.print("\n[dim]Wikipedia needs no credential — ingest works right now.[/]")


@app.command()
def ingest(
    seeds: str = typer.Option("seeds/phase0.yaml", help="Seed YAML file."),
    limit: Optional[int] = typer.Option(None, help="Ingest only the first N films."),
) -> None:
    """Fetch metadata and evidence layers for the seed corpus."""
    db.init_db()
    entries = ingest_mod.load_seeds(seeds)
    if limit:
        entries = entries[:limit]
    console.print(f"ingesting [bold]{len(entries)}[/] films from {seeds}\n")

    reports = []
    for seed in entries:
        reports.append(ingest_mod.ingest_one(seed, progress=console.print))

    console.print("\n[bold]evidence coverage[/]")
    table = Table("layer", "films with it", "median words", box=None)
    for layer in ("plot", "themes", "reception", "subtitles"):
        vals = [r["layers"].get(layer, 0) for r in reports]
        have = [v for v in vals if v]
        median = sorted(have)[len(have) // 2] if have else 0
        colour = "green" if len(have) == len(reports) else "yellow" if have else "red"
        table.add_row(layer, f"[{colour}]{len(have)}/{len(reports)}[/]", str(median))
    console.print(table)


@app.command("seed-films")
def seed_films(seeds: str = typer.Option("seeds/phase0.yaml", help="Seed YAML file.")) -> None:
    """Insert the curated seed films without downloading metadata or evidence."""
    from .sources import seed as seed_mod
    inserted = seed_mod.seed_films(seeds)
    console.print(f"[green]ready[/] inserted {inserted} missing seed films")


@app.command("opus-index")
def opus_index(
    version: str = typer.Option("v2024", help="OPUS release: v2018 or v2024."),
    lang: str = typer.Option("en"),
    force: bool = typer.Option(False, help="Rebuild even if cached."),
) -> None:
    """Index the OPUS subtitle archive (one-off ranged download of its directory).

    After this, individual films cost ~80 KB each with no account and no daily
    limit — instead of 20 downloads/day from the OpenSubtitles API.
    """
    from .sources import opus
    index = opus.build_index(version, lang, force, progress=console.print)
    console.print(f"[green]ready[/] {len(index):,} titles indexed")


@app.command()
def status() -> None:
    """Per-film evidence completeness and which variants can run."""
    films = db.list_films()
    if not films:
        console.print("[yellow]no films ingested yet — run `atlas ingest`[/]")
        raise typer.Exit()

    table = Table("film", "year", "plot", "themes", "recep", "subs", "score", "variants")
    for f in films:
        c = packet_mod.completeness(f["film_id"])
        mark = lambda ok: "[green]Y[/]" if ok else "[dim]-[/]"  # noqa: E731
        table.add_row(
            f["title"][:32], str(f.get("year") or ""),
            mark(c["layers"]["plot"]), mark(c["layers"]["themes"]),
            mark(c["layers"]["reception"]), mark(c["layers"]["subtitles"]),
            f"{c['score']:.2f}", ",".join(c["runnable_variants"]),
        )
    console.print(table)


@app.command()
def skeleton(
    variants: str = typer.Option(
        "full",
        help="Evidence conditions to extract for. Only `full` is read back "
             "(by `propose`) — the source A/B is measured at `score`, not here, "
             "so extracting all four costs ~4x for rows nothing consumes.",
    ),
    limit: Optional[int] = typer.Option(None),
) -> None:
    """Stage 1 — extract the moral skeleton under each evidence condition."""
    client = _client()
    run_id = __import__(
        "moral_atlas.llm.stages", fromlist=["extract_skeletons"]
    ).extract_skeletons(
        _film_ids(limit), variants.split(","), client, progress=console.print
    )
    console.print(f"\nrun [bold]{run_id}[/]  {json.dumps(client.usage.as_dict())}")


@app.command()
def propose(
    variant: str = typer.Option("full", help="Evidence condition to harvest from."),
    limit: Optional[int] = typer.Option(None),
) -> None:
    """Stage 2 — harvest free-form moral propositions from the corpus."""
    client = _client()
    run_id = __import__(
        "moral_atlas.llm.stages", fromlist=["generate_propositions"]
    ).generate_propositions(_film_ids(limit), client, variant, progress=console.print)
    console.print(f"\nrun [bold]{run_id}[/]  {json.dumps(client.usage.as_dict())}")


@app.command()
def bank(
    version: str = typer.Option("b1", help="Bank version label."),
    threshold: float = typer.Option(0.45, help="Clustering distance threshold."),
    no_llm: bool = typer.Option(False, help="Cluster only; skip canonicalisation."),
    min_support: int = typer.Option(1, help="Minimum distinct films per cluster."),
) -> None:
    """Cut the raw proposition pool into a versioned item bank."""
    clusters = bank_mod.cluster_propositions(threshold)
    if not clusters:
        console.print("[red]no raw propositions — run `atlas propose` first[/]")
        raise typer.Exit(1)
    console.print(f"clustered into [bold]{len(clusters)}[/] groups")

    client = None if no_llm else _client()
    result = bank_mod.build_bank(version, clusters, client, min_support,
                                 progress=console.print)
    console.print(json.dumps(result, indent=2))


@app.command("bank-export")
def bank_export(version: str = typer.Option("b1"),
                path: str = typer.Option("data/bank.jsonl")) -> None:
    """Write the bank out for the manual prune."""
    n = bank_mod.export_bank(version, path)
    console.print(f"wrote [bold]{n}[/] items to {path}")
    console.print("[dim]edit, set \"active\": false on the bad ones, "
                  "then: atlas bank-import[/]")


@app.command("bank-import")
def bank_import(version: str = typer.Option("b1"),
                path: str = typer.Option("data/bank.jsonl")) -> None:
    """Read a pruned bank back in."""
    console.print(f"updated [bold]{bank_mod.import_bank(version, path)}[/] items")


@app.command()
def score(
    version: str = typer.Option("b1", help="Bank version."),
    variants: str = typer.Option(DEFAULT_VARIANTS),
    limit: Optional[int] = typer.Option(None),
) -> None:
    """Stage 3 — score films against the bank under each evidence condition."""
    client = _client()
    run_id = __import__(
        "moral_atlas.llm.stages", fromlist=["score_films"]
    ).score_films(_film_ids(limit), variants.split(","), version, client,
                  progress=console.print)
    console.print(f"\nrun [bold]{run_id}[/]  {json.dumps(client.usage.as_dict())}")


@app.command()
def ab(
    version: str = typer.Option("b1"),
    reference: str = typer.Option("subs", help="Condition treated as ground truth."),
) -> None:
    """The source A/B — does cheaper evidence change the answer?"""
    report = ab_mod.compare(version, reference)
    if not report["variants"]:
        console.print("[yellow]nothing to compare — score at least two variants first[/]")
        raise typer.Exit()

    console.print(f"\n[bold]reference condition:[/] {reference}  "
                  f"({report['n_films']} films)\n")
    table = Table("variant", "both engaged", "agree", "flip", "flip rate",
                  "missed", "silence rate")
    for name, v in report["variants"].items():
        fr = v["flip_rate"]
        colour = "green" if fr is not None and fr < 0.10 else \
                 "yellow" if fr is not None and fr < 0.25 else "red"
        table.add_row(
            name, str(v["items_both_engaged"]), str(v["agree"]), str(v["flip"]),
            f"[{colour}]{fr:.1%}[/]" if fr is not None else "-",
            str(v["missed_by_this_variant"]),
            f"{v['silence_rate']:.1%}" if v["silence_rate"] is not None else "-",
        )
    console.print(table)

    for name, v in report["variants"].items():
        console.print(f"\n[bold]{name}[/]: {v['verdict']}")

    resistant = ab_mod.summary_resistant_items(report)
    if resistant:
        console.print("\n[bold]propositions the cheap sources get wrong most often[/]")
        t2 = Table("item", "flip rate", "proposition", box=None)
        for r in resistant[:12]:
            t2.add_row(r["item_id"], f"{r['flip_rate']:.0%}", r["text"][:74])
        console.print(t2)


@app.command()
def displacement(
    parent: str = typer.Argument(..., help="Source-text film_id."),
    child: str = typer.Argument(..., help="Revision film_id."),
    version: str = typer.Option("b1"),
) -> None:
    """Editor-bias probe: measure a revision's moral displacement per condition."""
    console.print(json.dumps(ab_mod.displacement(version, parent, child), indent=2))


@app.command("migrate-db")
def migrate_db(
    source: str = typer.Option("data/atlas.duckdb", help="Old DuckDB file."),
) -> None:
    """Copy an existing DuckDB store into the SQLite store, verifying counts."""
    from .analysis import migrate as migrate_mod
    console.print(f"migrating [bold]{source}[/] -> {settings().db_path}\n")
    report = migrate_mod.migrate(source, progress=console.print)
    console.print(f"\n[green]migrated {report['total_rows']} rows[/]")


@app.command("export")
def export_cmd(
    out: str = typer.Option("dist/export", help="Directory to write into."),
    include_evidence: bool = typer.Option(
        False, help="Include raw plot/subtitle text. Large, and fully "
                    "reproducible from public sources without it."),
    no_db: bool = typer.Option(False, help="Skip copying the .sqlite file."),
) -> None:
    """Export everything derived so far, for transfer to another machine."""
    from .analysis import export as export_mod
    console.print(f"exporting to [bold]{out}[/]")
    manifest = export_mod.export(out, include_evidence, not no_db,
                                 progress=console.print)

    sc = manifest["stage_completeness"]
    console.print(f"\n[bold]total spend so far:[/] ${manifest['total_cost_usd']}")
    table = Table("stage", "coverage", box=None)
    table.add_row("films ingested", str(sc["films_ingested"]))
    table.add_row("full skeletons", f"{sc['films_with_full_skeleton']}/{sc['films_ingested']}")
    table.add_row("propositions", f"{sc['films_with_propositions']}/{sc['films_ingested']}")
    table.add_row("scored", f"{sc['films_scored']}/{sc['films_ingested']}")
    console.print(table)
    if not sc["has_analysis_results"]:
        console.print(
            "\n[yellow]No analysis results yet.[/] This bundle holds extracted "
            "intermediates only — no item bank, no scores, no factors. Useful for "
            "moving work between machines, not for reading conclusions off.")


@app.command()
def packet(
    film_id: str = typer.Argument(...),
    variant: str = typer.Option("spine"),
    chars: int = typer.Option(2000, help="How much to print."),
) -> None:
    """Print an assembled packet — what the model will actually see."""
    p = packet_mod.build(film_id, variant)
    console.print(f"[bold]{p.title}[/] ({p.year})  variant={p.variant}  "
                  f"~{p.tokens} tokens")
    console.print(f"layers present: {p.layers_present}  missing: {p.layers_missing}\n")
    console.print(p.text[:chars])


if __name__ == "__main__":
    app()
