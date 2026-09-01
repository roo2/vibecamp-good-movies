"""atlas — command line for the Moral Atlas pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import db
from .analysis import ab as ab_mod
from .analysis import bank as bank_mod
from .analysis import dimensions as dim_mod
from .config import PROMPT_VERSION, settings
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
    """Create the database, apply curated data migrations, and report credentials."""
    db.init_db()
    # `atlas-update` runs this command before restarting the deployed API. That
    # makes edits to the curated seed descriptions reach existing database rows
    # without replacing film metadata or requiring a one-off server command.
    from .sources import seed as seed_mod
    migration = seed_mod.sync_seed_films()
    s = settings()
    console.print(f"[green]database ready[/] {s.db_path}")
    console.print(
        "[green]curated films ready[/] "
        f"inserted {migration['inserted']}, updated {migration['updated']}, "
        f"unchanged {migration['unchanged']}"
    )

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
    """Insert curated films and migrate their descriptions without downloading evidence."""
    from .sources import seed as seed_mod
    result = seed_mod.sync_seed_films(seeds)
    console.print(
        "[green]ready[/] "
        f"inserted {result['inserted']}, updated {result['updated']}, "
        f"unchanged {result['unchanged']}"
    )


@app.command("migrate-descriptions")
def migrate_descriptions(
    seeds: str = typer.Option("seeds/phase0.yaml", help="Seed YAML file."),
) -> None:
    """Apply the current curated descriptions to new and existing film rows."""
    from .sources import seed as seed_mod
    result = seed_mod.sync_seed_films(seeds)
    console.print(
        "[green]descriptions migrated[/] "
        f"inserted {result['inserted']}, updated {result['updated']}, "
        f"unchanged {result['unchanged']}"
    )


@app.command("populate-artwork")
def populate_artwork(force: bool = typer.Option(False, help="Refresh URLs that are already present.")) -> None:
    """Populate remote lead-image URLs from Wikipedia; no API key required."""
    from .sources import wikipedia as wiki_mod
    result = wiki_mod.populate_artwork(force=force)
    console.print(f"[green]artwork ready[/] updated {result['updated']}, missing {result['missing']}, skipped {result['skipped']}")


@app.command("audit-verdicts")
def audit_verdicts(
    scorer: str = typer.Option("deepseek"),
    bank: str = typer.Option("dolphin-subs"),
    variant: str = typer.Option("subs"),
    limit: Optional[int] = typer.Option(None, help="Only this many, for a costed trial."),
    batch_size: int = typer.Option(40, help="Verdicts per call."),
    apply: bool = typer.Option(False, help="Write the corrections. Off by default."),
    redo: bool = typer.Option(False, help="Re-check rows already audited."),
) -> None:
    """Check each verdict against the reason the model gave for it.

    Every verdict carries a one-line justification written in the same reply.
    Occasionally the model writes the reasoning for one answer and records the
    other — Life of Brian "strongly denies" that belief in one's own superiority
    leads to oppression, justified by the film "showing it leads to oppression".

    A few percent, which is not ignorable: a flipped verdict enters the
    correlation matrix with the wrong sign, so it pulls apart two propositions
    that belong together rather than merely adding noise to one film.
    """
    from .analysis import verdict_audit
    from .llm.providers import client_for

    client = client_for(scorer)
    result = verdict_audit.audit(scorer, bank, variant, client, batch_size=batch_size,
                                 limit=limit, apply=apply, redo=redo,
                                 progress=lambda m: console.print(f"[dim]{m}[/]"))
    console.print(
        f"\n  checked [bold]{result['checked']}[/], "
        f"contradicted [yellow]{result['contradicted']}[/]"
        + (f" ({result['contradicted'] / result['checked']:.1%})" if result["checked"] else "")
        + f", corrected [green]{result['corrected']}[/]"
        + (f", flagged but unreadable {result['unreadable']}" if result["unreadable"] else ""))
    console.print(f"  {json.dumps(client.usage.as_dict())}")
    if not apply and result["contradicted"]:
        console.print("[yellow]nothing written[/] — pass --apply to correct them")


@app.command("compare-film")
def compare_film(
    film: str = typer.Argument(..., help="Film id, or a fragment of its title."),
    scorers: str = typer.Option("deepseek,dolphin", help="Two or more aliases."),
    bank: str = typer.Option("deepseek-subs", help="The bank BOTH read against."),
    variant: str = typer.Option("subs"),
    show: int = typer.Option(12, help="How many disagreements to print."),
) -> None:
    """Two readers on one film, and every proposition they answer differently.

    The corpus-level comparison asks whether scorers recover the same axes,
    which needs hundreds of films. This asks the smaller question that turned
    out to be hiding inside it: handed the SAME propositions, where do two
    readers actually differ, and does the difference have a shape?
    """
    from .analysis import film_compare

    aliases = [a.strip() for a in scorers.split(",") if a.strip()]
    matches = _match_films(film)
    if not matches:
        console.print(f"[red]no film matched {film!r}[/]")
        raise typer.Exit(1)
    result = film_compare.compare(matches[0], aliases, bank, variant)

    console.print(f"\n[bold]{result['title']}[/] — {result['bank_size']} propositions "
                  f"({result['bank_version']})")
    table = Table("reader", "engaged", "only it", "affirms", box=None)
    for alias in aliases:
        table.add_row(alias, str(result["engaged"][alias]),
                      str(result["only"].get(alias, 0)),
                      f"{result['affirm_rate'][alias]:.0%}")
    console.print(table)
    shared, agreed = result["shared"], result["agreed"]
    console.print(f"  both answered [bold]{shared}[/]; same side on [bold]{agreed}[/]"
                  + (f" ({agreed / shared:.0%})" if shared else ""))

    if not result["split"]:
        console.print("[dim]  no disagreements[/]")
        return
    console.print(f"\n[bold]{len(result['split'])} propositions they read differently[/]")
    for row in result["split"][:show]:
        console.print(f"\n  [italic]{row['text']}[/]")
        for alias in aliases:
            v = row["by"][alias]
            colour = "green" if v["value"] > 0 else "yellow"
            console.print(f"    [{colour}]{alias:<9} {v['value']:+d}[/] {v['evidence'][:96]}")


@app.command("sample-films")
def sample_films(
    n: int = typer.Option(100, help="How many films to pick."),
    scorer: str = typer.Option("deepseek", help="Whose harvest already exists."),
    variant: str = typer.Option("subs"),
    show: int = typer.Option(15, help="How many of the picks to print."),
) -> None:
    """Pick the next films to harvest propositions from, by coverage rather than by chance.

    The first harvest took whichever films had subtitles first: 122 of 135 in
    English, 119 in the US or UK. Everything downstream inherits that, because
    the films that write the propositions decide what the instrument can ask.
    """
    from .analysis import sampling

    films = sampling.corpus()
    done = sampling.already_harvested(scorer, variant)
    picks = sampling.select(films, n, already=done)
    before = sampling.coverage([f for f in films if f["film_id"] in done])
    after = sampling.coverage([f for f in films if f["film_id"] in done] + picks)

    console.print(f"[bold]{len(films)}[/] films with subtitles, [bold]{len(done)}[/] already harvested")
    table = Table("facet", "distinct now", "distinct after", "largest share now",
                  "after", box=None)
    for facet in sorted(before["distinct"]):
        table.add_row(facet, str(before["distinct"][facet]), str(after["distinct"].get(facet, 0)),
                      f"{before['dominance'][facet]:.0%}", f"{after['dominance'].get(facet, 0):.0%}")
    console.print(table)
    console.print(f"\n[bold]first {min(show, len(picks))} picks[/]")
    for film in picks[:show]:
        console.print(f"  {film['title'][:44]:<44} {film['year']}  {film['original_language'] or '-'}")
    ids = ",".join(f["film_id"] for f in picks)
    console.print(f"\n[dim]atlas model-propose --films \"{ids}\"[/]")


@app.command("semantic-bank")
def semantic_bank_cmd(
    scorer: str = typer.Option("deepseek"),
    variant: str = typer.Option("subs"),
    prefix: str = typer.Option("", help="Bank version prefix; defaults to <alias>-semantic."),
    distance: float = typer.Option(0.45, help="Cosine distance for topical neighbourhoods."),
    write: bool = typer.Option(False, help="Persist the bank. Off by default: writing a bank "
                                          "invalidates every verdict scored against that version."),
) -> None:
    """Cut the harvest into an item bank by meaning rather than by wording.

    Embeddings propose topical neighbourhoods, polarity blocks them, and a model
    reads the MEMBER sentences and says how many distinct claims each really
    holds. The lexical cut it replaces merged "the ends justify the means when
    the end is the collective good" with "the ends do not justify immoral
    means", then canonicalised from the representative alone and produced a
    hedge that nearly every film affirms.
    """
    from .analysis import semantic_bank
    from .llm.providers import client_for

    rows = semantic_bank.harvest(scorer, variant)
    if not rows:
        console.print(f"[yellow]{scorer} has no {variant!r} harvest[/]")
        raise typer.Exit(1)
    client = client_for(scorer)
    report = semantic_bank.build(rows, client, distance=distance,
                                 progress=lambda m: console.print(f"[dim]{m}[/]"))
    console.print(f"\n[bold]{report['n_propositions']}[/] propositions → "
                  f"[bold]{report['n_neighbourhoods']}[/] neighbourhoods → "
                  f"[bold]{report['n_claims']}[/] distinct claims")
    console.print(f"  {json.dumps(client.usage.as_dict())}")

    if not write:
        console.print("[yellow]not written[/] — pass --write to persist, which discards "
                      "every verdict scored against that bank version")
        return
    version = f"{prefix or scorer}-semantic"
    run_id = db.start_run("bank", client.model, PROMPT_VERSION,
                          {"bank_version": version, "semantic": True,
                           "n_claims": report["n_claims"]})
    invalidated = semantic_bank.write_bank(version, report["claims"], client.model, run_id)
    db.finish_run(run_id, client.usage.as_dict())
    console.print(f"[green]bank {version}[/] {report['n_claims']} items")
    if invalidated:
        console.print(f"[yellow]discarded {invalidated}[/]")


@app.command("backfill-metadata")
def backfill_metadata(
    limit: Optional[int] = typer.Option(None, help="Only this many films; omit for all."),
) -> None:
    """Fill genre, country, language, director and source from Wikidata.

    The subtitle-corpus ingest never called TMDB, so most films arrived with an
    IMDb id and twelve empty columns. This fills the ones that can group films
    for an analysis or filter them in the app, from a CC0 source — TMDB's terms
    forbid using their content to develop a model, which the factor analysis is.
    No API key needed.
    """
    from .sources import wikidata as wd
    result = wd.backfill(limit=limit, progress=lambda m: console.print(f"[dim]{m}[/]"))
    console.print(
        f"[green]metadata[/] looked at {result['looked_at']}, matched {result['matched']}, "
        f"updated {result['updated']} films across {result['columns']} column writes")


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
def dimensions(
    version: str = typer.Option("d1", help="Dimension set version label."),
    bank: str = typer.Option("b1", help="Bank version to place on the axes."),
    n_dims: int = typer.Option(8, help="How many axes to derive (aim for 5-10)."),
    replicate: int = typer.Option(
        150, help="Items to re-assign blind, as a reliability check. 0 skips it."),
    cross_model: str = typer.Option(
        "", help="Also assign with this model, to separate a real distinction "
                 "from one model's taste. e.g. claude-sonnet-5"),
    reuse: bool = typer.Option(
        False, help="Keep the stored axes and only redo the assignment."),
) -> None:
    """Name the moral axes the bank measures, and place every item on one.

    The audit passes are part of the same command on purpose: an assignment
    nobody checked is an opinion, and the check costs a few percent of the run.
    """
    import random as _random

    client = _client()
    db.init_db()

    if reuse:
        dims = dim_mod.load_dimensions(version)
        if not dims:
            console.print(f"[red]no dimension set {version!r} to reuse[/]")
            raise typer.Exit(1)
        console.print(f"reusing [bold]{len(dims)}[/] stored dimensions")
    else:
        dims = dim_mod.derive(version, client, n_dims, bank_version=bank,
                              progress=console.print)

    table = Table("#", "dimension", "the question it poses", box=None)
    for d in dims:
        table.add_row(str(d["dim_id"]), d["name"], d["question"])
    console.print(table)

    items = dim_mod.bank_items(bank)
    dim_mod.assign(version, bank, dims, client, items=items,
                   progress=console.print)

    if replicate:
        sample = _random.Random(11).sample(items, min(replicate, len(items)))
        dim_mod.assign(version, bank, dims, client, items=sample,
                       pass_name=dim_mod.REPLICATE_PASS, shuffle_seed=11,
                       progress=console.print)

    if cross_model:
        from .llm.client import LLMClient
        other = LLMClient(model=cross_model)
        sample = _random.Random(11).sample(items, min(replicate or 150, len(items)))
        dim_mod.assign(version, bank, dims, other, items=sample,
                       pass_name=f"crossmodel:{cross_model}", progress=console.print)
        console.print(f"[dim]{cross_model} usage {json.dumps(other.usage.as_dict())}[/]")

    console.print(f"\n{json.dumps(client.usage.as_dict())}")
    console.print("[dim]now: atlas dimensions-validate[/]")


@app.command("dimensions-validate")
def dimensions_validate(
    version: str = typer.Option("d1"),
    bank: str = typer.Option("b1"),
    permutations: int = typer.Option(1000, help="Permutations for the null."),
    seed: int = typer.Option(3, help="Fixed, so a published number can be re-run."),
    threshold: float = typer.Option(
        0.45, help="Clustering threshold the bank was cut with — needed to trace "
                   "each item back to its source film."),
    include_own_film: bool = typer.Option(
        False, help="Let a film vote on items harvested from itself. Inflates "
                    "the result; off by default."),
    variants: str = typer.Option("", help="Restrict to these evidence conditions."),
    as_json: bool = typer.Option(False, "--json", help="Emit the raw report."),
) -> None:
    """Is this set of axes in the corpus, or did we impose it?

    Prints the evidence rather than a verdict: coverage, agreement between
    independent assignment passes, and two permutation tests against scores that
    were produced before the axes existed.
    """
    report = dim_mod.validate(
        version, bank, permutations=permutations, seed=seed,
        exclude_own_film=not include_own_film, threshold=threshold,
        variants=[v for v in variants.split(",") if v] or None,
        progress=console.print,
    )
    if as_json:
        console.print(json.dumps(report, indent=2))
        return

    cov = report["coverage"]
    console.print(f"\n[bold]coverage[/]  {report['n_items']} items, median fit "
                  f"{cov['median_fit']:.2f}, "
                  f"{cov['share_fit_ge_0_4']:.0%} at fit >= 0.4")
    t = Table("dimension", "items", box=None)
    for name, n in cov["sizes"].items():
        t.add_row(name, str(n))
    console.print(t)

    if report["agreement"]:
        console.print("\n[bold]independent assignment passes[/]")
        t = Table("pass", "model", "n", "same axis", "chance", "kappa",
                  "same polarity", box=None)
        for name, a in report["agreement"].items():
            colour = ("green" if a["kappa"] and a["kappa"] >= 0.7 else
                      "yellow" if a["kappa"] and a["kappa"] >= 0.4 else "red")
            t.add_row(name, a.get("model") or "-", str(a["n"]),
                      f"{a['raw']:.0%}" if a["raw"] is not None else "-",
                      f"{a['chance']:.0%}" if a["chance"] is not None else "-",
                      f"[{colour}]{a['kappa']:.2f}[/]" if a["kappa"] is not None else "-",
                      f"{a['polarity_agreement']:.0%}"
                      if a["polarity_agreement"] is not None else "-")
        console.print(t)

    if "co_engagement" in report:
        mode = ("own-film verdicts excluded" if report["exclude_own_film"]
                else "[yellow]own-film verdicts INCLUDED[/]")
        console.print(f"\n[bold]behavioural tests[/]  {report['n_engagements']} "
                      f"engagements over {report['n_packets']} packets, {mode}")
        t = Table("test", "observed", "null", "z", "perms >= observed", box=None)
        for key, label in (("co_engagement", "co-engagement (pairs sharing an axis)"),
                           ("coherence", "stance coherence (|net| per film x axis)")):
            r = report[key]
            t.add_row(label, f"{r['observed']:.3f}",
                      f"{r['null_mean']:.3f} (sd {r['null_sd']:.3f})",
                      f"[bold]{r['z']:+.1f}[/]" if r["z"] is not None else "-",
                      f"{r['n_at_least_observed']}/{r['permutations']}")
        console.print(t)
        console.print("[dim]The scoring run never saw the axes and the assignment "
                      "never saw the scores, so shared structure is not an artefact "
                      "of either.[/]")


@app.command("dimensions-split-half")
def dimensions_split_half(
    n_dims: int = typer.Option(8),
    seed: int = typer.Option(7, help="Which way the corpus is cut."),
) -> None:
    """Derive the axes twice, from film sets that share no propositions.

    Axes that recur across two disjoint halves are a property of the corpus.
    Axes that do not are a property of the prompt. Nothing is written — read the
    two lists side by side and judge.
    """
    client = _client()
    out = dim_mod.split_half(client, n_dims, seed, progress=console.print)
    for half in ("half_a", "half_b"):
        films = len(out[f"{half}_films"])
        console.print(f"\n[bold]{half.replace('_', ' ').upper()}[/] ({films} films)")
        t = Table("#", "dimension", "the question it poses", box=None)
        for d in out[half]:
            t.add_row(str(d["dim_id"]), d["name"], d["question"])
        console.print(t)
    console.print(f"\n{json.dumps(client.usage.as_dict())}")


@app.command()
def profile(
    version: str = typer.Option("d1"),
    bank: str = typer.Option("b1"),
    top: int = typer.Option(3, help="Axes to show per film."),
    film: str = typer.Option("", help="Just this film."),
) -> None:
    """Where each film sits on the axes — the human-readable output."""
    profiles = dim_mod.film_profiles(version, bank, top)
    if not profiles:
        console.print("[yellow]nothing to profile — score against the bank first[/]")
        raise typer.Exit()
    for name, rows in profiles.items():
        if film and film not in name:
            continue
        console.print(f"\n[bold]{name}[/]")
        t = Table("dimension", "pole", "net", "items", box=None)
        for r in rows:
            pole = "HIGH" if r["net"] > 0 else "LOW"
            colour = "green" if abs(r["net"]) >= 0.6 else "yellow"
            t.add_row(r["dimension"], f"[{colour}]{pole}[/]",
                      f"{r['net']:+.2f}", str(r["n_items"]))
        console.print(t)


@app.command()
def provenance(
    bank: Optional[str] = typer.Option(None, help="Restrict to one bank version."),
) -> None:
    """Which model produced each layer of the atlas.

    The question this answers is "whose judgement am I looking at?", and until
    the bank step was stamped it could not be answered for the one layer whose
    wording every score depends on.
    """
    rows = db.provenance(bank)
    if not rows:
        console.print("[yellow]nothing derived yet[/]")
        raise typer.Exit()

    table = Table("layer", "table", "model", "prompt", "rows", box=None)
    for row in rows:
        model = row["model"] or "[red]unrecorded[/]"
        table.add_row(row["layer"], row["table"], model,
                      row["prompt_version"] or "-", f"{row['rows']:,}")
    console.print(table)

    layers = {row["layer"] for row in rows}
    mixed = {layer for layer in layers
             if len({row["model"] for row in rows if row["layer"] == layer}) > 1}
    if mixed:
        console.print(f"\n[yellow]more than one model in:[/] {', '.join(sorted(mixed))}")
        console.print("[dim]Fine deliberately, misleading by accident — a layer built "
                      "by two models is not one instrument.[/]")
    if any(row["model"] is None for row in rows):
        console.print("\n[yellow]some rows predate provenance[/] — "
                      "`atlas backfill-provenance --model <the model that ran>`")


@app.command("backfill-provenance")
def backfill_provenance(
    model: Optional[str] = typer.Option(
        None, help="Model to assert for rows whose run was never recorded."),
) -> None:
    """Stamp older rows with the model that produced them.

    Rows carrying a run_id are filled from `runs`, which is lossless. The bank
    is the exception: `build_bank` never opened a run, so the model that wrote
    those canonical sentences was never recorded and must be asserted by
    whoever remembers running it.
    """
    filled = db.backfill_provenance(model)
    table = Table("table", "was blank", "from runs", "asserted", "still blank", box=None)
    for name, row in filled.items():
        table.add_row(name, str(row["was_null"]), str(row["from_runs"]),
                      f"[yellow]{row['asserted']}[/]" if row["asserted"] else "0",
                      f"[red]{row['still_null']}[/]" if row["still_null"] else "0")
    console.print(table)
    if any(row["still_null"] for row in filled.values()) and not model:
        console.print("\n[dim]Rows with no run to read from need --model.[/]")


@app.command("models")
def models_cmd() -> None:
    """The scorers available for the bias study, and which have credentials."""
    from .llm.providers import PROVIDERS, SCORERS, available

    table = Table("alias", "provider", "model", "posture", "key", box=None)
    for alias, scorer in SCORERS.items():
        ready = available(alias)
        table.add_row(alias, scorer.provider, scorer.model, scorer.posture,
                      "[green]set[/]" if ready else "[yellow]missing[/]")
    console.print(table)
    console.print("\n[bold]where the keys come from[/]")
    for name, provider in PROVIDERS.items():
        console.print(f"  {name:<12} {provider.env_var:<20} {provider.console}")
    console.print("\n[dim]Notes[/]")
    for alias, scorer in SCORERS.items():
        console.print(f"  [bold]{alias}[/]: {scorer.note}")


@app.command("model-scan")
def model_scan(
    scorers: str = typer.Option("deepseek", help="Comma-separated aliases; see `atlas models`. DeepSeek by default: at roughly a hundredth of the cost per film it is what makes a corpus this size affordable to score at all."),
    bank: str = typer.Option("b1"),
    variant: str = typer.Option("spine", help="Evidence condition; the same one for every scorer."),
    limit: Optional[int] = typer.Option(None, help="Score only the first N films."),
    films: str = typer.Option("", help="Only these films (ids or title fragments, comma-separated)."),
    batch_size: Optional[int] = typer.Option(
        None, help="Propositions per call. Omit to send the whole bank in one call, which is "
                   "right for a small bank. Set it for a large one: a call asked for hundreds "
                   "of verdicts at once spends little attention on each, and batching puts the "
                   "film in the cached prefix so its evidence is not resent per slice."),
) -> None:
    """Score films again with other models, to see whose morals the scores are.

    `--films` is how a newly added film joins the comparison: it is scored by
    every scorer against the EXISTING bank, so no new propositions are harvested
    and the instrument the earlier films were measured with does not change
    underneath them. Adding to the bank instead would silently re-cut the ruler.

    Writes to `model_verdicts`, never to `scores` — the product's film positions
    must not move because an audit ran.
    """
    from .analysis import model_bias
    from .llm.providers import missing_credentials

    aliases = [a.strip() for a in scorers.split(",") if a.strip()]
    missing = missing_credentials(aliases)
    for alias, provider in missing.items():
        console.print(f"[yellow]skipping {alias}[/] — set {provider.env_var} ({provider.console})")
    aliases = [a for a in aliases if a not in missing]
    if not aliases:
        console.print("[red]no scorers with credentials[/] — see `atlas models`")
        raise typer.Exit(1)

    film_ids = _match_films(films) if films.strip() else _film_ids(limit)
    if not film_ids:
        console.print("[red]no films matched[/]")
        raise typer.Exit(1)
    for alias in aliases:
        console.print(f"\n[bold]{alias}[/] over {len(film_ids)} films ({variant})")
        stats = model_bias.scan(alias, film_ids, bank, variant, progress=console.print,
                                batch_size=batch_size)
        # lost_slices and unanswered were counted and never shown, which made a
        # run that silently dropped most of its work report "failed 0". A
        # partial result that looks complete is worse than a failure.
        lost = stats.get("lost_slices", 0)
        missed = stats.get("unanswered", 0)
        console.print(f"  scored {stats['scored']}, refused [yellow]{stats['refused']}[/], "
                      f"failed [red]{stats['failed']}[/]"
                      + (f", [red]{lost} slices lost[/]" if lost else "")
                      + (f", [yellow]{missed} propositions never answered[/]" if missed else "")
                      + f"  {json.dumps(stats['usage'])}")
        if lost:
            console.print(f"  [red]{lost} slices were dropped[/] — this run is INCOMPLETE, "
                          f"and the films above are missing propositions they were never "
                          f"asked about. Re-run it. The reason is in the failure lines: a "
                          f"burst of provider errors is the common one, and it clears.")


@app.command()
def discover(
    start: int = typer.Option(1970, help="First year to sample."),
    end: int = typer.Option(2024, help="Last year, inclusive."),
    per_year: int = typer.Option(10, help="Best-documented films to take from each year."),
    ingest: bool = typer.Option(True, help="Also fetch their Wikipedia evidence."),
) -> None:
    """Enlarge the corpus by enumeration rather than by hand.

    The corpus size is what limits every question about how many moral
    dimensions there are: with forty films the correlation matrix has rank at
    most 39 and the marginal factors move when the null is resampled. These
    films get plot evidence and no blind-story description, which is what keeps
    them out of the product's pairs while counting as respondents.
    """
    from .sources import discover as discover_mod

    existing = {film["film_id"] for film in db.list_films()}
    found = discover_mod.discover(range(start, end + 1), per_year, progress=console.print)
    entries = discover_mod.as_seed_entries(found, existing)
    console.print(f"\n[bold]{len(found)}[/] candidates, [bold]{len(entries)}[/] new to the corpus")
    if not ingest:
        raise typer.Exit()

    stats = discover_mod.bulk_ingest(entries, progress=console.print)
    console.print(f"\n[green]ingested {stats['ingested']}[/], "
                  f"[yellow]{stats['no_plot']} had no plot section[/], "
                  f"[red]{stats['failed']} failed[/]")
    films = db.list_films()
    eligible = sum(1 for f in films if (f.get("description") or "").strip())
    console.print(f"corpus now {len(films)} films — {eligible} product-eligible, "
                  f"{len(films) - eligible} research-only")


@app.command("dimension-count")
def dimension_count(
    scorers: str = typer.Option("", help="Also run per model, e.g. grok,deepseek."),
    bank: str = typer.Option("b1"),
    iterations: int = typer.Option(200, help="Permutations for the parallel-analysis null."),
    min_films: int = typer.Option(3, help="Drop items scored on fewer films than this."),
) -> None:
    """How many dimensions the FILMS support — discovered, not supplied.

    Every other route to the axes asks a model to name N of them, so the count
    was always an input. This reads how films actually responded to the items
    and keeps only the factors that beat a null built by permuting each item's
    own column.
    """
    from .analysis import latent

    aliases = [None] + [a.strip() for a in scorers.split(",") if a.strip()]
    reports = []
    for alias in aliases:
        try:
            reports.append(latent.analyse(alias, bank, n_iter=iterations, min_films=min_films))
        except RuntimeError as error:
            console.print(f"[yellow]{alias or 'opus'}: {error}[/]")

    for report in reports:
        console.print(f"\n[bold]{report['scorer']}[/] — {report['films']} films x "
                      f"{report['items']} items ({report['density']:.0%} dense, "
                      f"{report['dropped_items']} items dropped, of which "
                      f"{report.get('unanimous_items', 0)} because no film disagreed)")
        table = Table("factor", "eigenvalue", "null 95th", "margin", box=None)
        for index, (observed, threshold) in enumerate(
                zip(report["eigenvalues"][:14], report["null_threshold"][:14]), start=1):
            margin = (observed - threshold) / threshold if threshold else 0
            colour = ("green" if margin >= 0.05 else "yellow" if margin > 0 else "dim")
            table.add_row(str(index), f"{observed:.3f}", f"{threshold:.3f}",
                          f"[{colour}]{margin:+.1%}[/]")
        console.print(table)
        console.print(f"  clears the null at all: [bold]{report['n_factors']}[/]   "
                      f"clears it by >=5%: [bold]{report['n_clear_factors']}[/]   "
                      f"[dim](at most {report['max_recoverable']} recoverable "
                      f"from {report['films']} films)[/]")
        console.print(f"  group sizes: {report['group_sizes']}")

    if len(reports) > 1:
        found = latent.convergence(reports)
        console.print("\n[bold]do the scorers converge?[/]")
        console.print(f"  counts: {found['counts']}   spread: {found['spread']}")
        table = Table("pair", "items", "ARI", "chance", box=None)
        for pair, row in found["grouping_agreement"].items():
            table.add_row(pair, str(row["n_items"]), f"{row['ari']:+.3f}",
                          f"{row['null_ari_mean']:+.4f}")
        console.print(table)
        console.print("[dim]Agreeing on the count is not agreeing on the grouping — "
                      "two scorers can both say eight and cut the material differently.[/]")


@app.command("model-bank")
def model_bank(
    scorers: str = typer.Option("deepseek", help="Comma-separated aliases."),
    variant: str = typer.Option("subs", help="Which harvest to cut from."),
    threshold: float = typer.Option(
        0.78, help="Clustering distance threshold. Higher merges harder — worth it on a "
                   "large harvest, where 0.45 leaves near-duplicates as separate items."),
    min_support: int = typer.Option(
        2, help="Keep only propositions at least this many films raised independently. "
                "An item one film engages cannot discriminate between films, and the "
                "factor analysis drops it anyway."),
    prefix: str = typer.Option("", help="Bank version prefix; defaults to the alias."),
) -> None:
    """Cut a model's OWN propositions into its OWN item bank.

    The shared b1 bank is Claude's: Claude wrote those propositions and Claude
    canonicalised them, so every model scored against it is answering Claude's
    questions. A model that writes its own bank, scores films against it and
    then has the factors named from its own verdicts is measured end to end in
    its own terms — which is the only way a difference between models can be a
    difference about films rather than about whose questions were asked.

    The bank lands in `item_bank` under its own version, so everything
    downstream — scoring, the response matrix, the factor analysis — works on it
    unchanged.
    """
    from .analysis import bank as bank_module
    from .llm.providers import client_for

    for alias in _ready_scorers(scorers):
        rows = bank_module.model_propositions(alias, variant)
        if not rows:
            console.print(f"[yellow]{alias} has no {variant!r} harvest — "
                          f"run `atlas model-propose --variant {variant}` first[/]")
            continue

        version = f"{prefix or alias}-{variant}"
        clusters = bank_module.cluster_propositions(threshold, rows)
        console.print(f"\n[bold]{alias}[/] {len(rows)} propositions → "
                      f"{len(clusters)} clusters")
        result = bank_module.build_bank(version, clusters, client_for(alias),
                                        min_support=min_support, progress=console.print)
        console.print(f"  bank [bold]{version}[/]: {result['n_items']} items, "
                      f"{result['n_dropped']} dropped, "
                      f"{result['n_inversions_split']} inversions split")
        if result.get("invalidated"):
            gone = ", ".join(f"{n} {table}" for table, n in result["invalidated"].items())
            console.print(f"  [yellow]discarded {gone}[/] — item ids are positional, so "
                          f"anything scored against the old bank was measuring other sentences")


@app.command("name-factors")
def name_factors_cmd(
    scorers: str = typer.Option("deepseek", help="Comma-separated aliases."),
    variant: str = typer.Option("subs", help="Evidence condition to read. One, not a mix."),
    bank: str = typer.Option("b1"),
    iterations: int = typer.Option(200, help="Permutations for the parallel-analysis null."),
    min_films: int = typer.Option(3, help="Drop items scored on fewer films than this."),
    # Literal rather than factor_names.NAMING_RUNS: typer evaluates option
    # defaults at import time and this module imports the analysis packages
    # inside the commands, to keep numpy off the path of every --help.
    runs: int = typer.Option(
        3, help="Name this many times and keep the most representative answer. "
                "1 names once, as it used to."),
) -> None:
    """Name the axes the FILMS produced, rather than asking a model for eight.

    The statistics decide how many factors there are and which propositions load
    onto each; a model is then asked only to read a finished group and say what
    it is about. Names will differ between scorers, and should: two models that
    engaged different items measured different corpora, so the groups handed to
    the namer are not the same groups.
    """
    from .analysis import factor_names, latent

    texts = factor_names.bank_texts(bank)
    for alias in _ready_scorers(scorers):
        try:
            report = latent.analyse(None if alias == "opus" else alias, bank,
                                    n_iter=iterations, min_films=min_films,
                                    variant=variant)
        except RuntimeError as error:
            console.print(f"[yellow]{alias}: {error}[/]")
            continue

        console.print(f"\n[bold]{alias}[/] — {report['films']} films × {report['items']} items "
                      f"({variant}) → [bold]{report['n_clear_factors']}[/] factors clearing "
                      f"the null by >=5% (of {report['n_factors']} clearing it at all)")
        client = None
        from .llm.providers import client_for
        client = client_for(alias)
        named = factor_names.name_factors(report, texts, client=client, alias=alias,
                                          runs=runs,
                                          progress=console.print)
        factor_names.persist(alias, report, named, bank, usage=client.usage.as_dict())

        # Best-supported first, the same order the atlas, the film pages and a
        # person's own compass use. This printed in factor_id order — which is
        # a k-means label, means nothing, and put an axis clearing chance by
        # 127% below one clearing it by 11%.
        table = Table("axis", "items", "margin", "question", box=None)
        for row in sorted(named, key=factor_names.by_support):
            colour = "green" if row["margin"] and row["margin"] >= 0.05 else "yellow"
            name = row["name"] if row["coherent"] else f"[dim]{row['name']}?[/]"
            table.add_row(name, str(row["n_items"]),
                          f"[{colour}]{row['margin']:+.1%}[/]" if row["margin"] else "-",
                          row["question"][:70])
        console.print(table)
        incoherent = [r["name"] for r in named if not r["coherent"]]
        if incoherent:
            console.print(f"[yellow]{len(incoherent)} factor(s) the namer would not call "
                          f"coherent:[/] {', '.join(incoherent)}")
            console.print("[dim]A statistical factor that resists naming is a result, not a "
                          "failure — it means those items co-occur without sharing a question.[/]")


@app.command("film-sets")
def film_sets_cmd(
    seeds: str = typer.Option("", help="Seed YAML. Defaults to seeds/film-sets.yaml."),
) -> None:
    """Rebuild the named film sets the atlas can highlight.

    Every set carries the source it came from. A set is somebody's claim that
    these films belong together, made without reference to the axes — which is
    what makes agreement between a set and a region of the space evidence
    rather than construction.
    """
    from pathlib import Path as _Path

    from .analysis import film_sets

    report = film_sets.load(_Path(seeds) if seeds else None, progress=console.print)
    console.print(f"\n[bold]{report['sets']}[/] sets, {report['members']} memberships")
    for set_id, missing in report["missing"].items():
        console.print(f"[yellow]{set_id}[/]: {len(missing)} titles not in the corpus — "
                      f"{', '.join(missing[:6])}" + (" ..." if len(missing) > 6 else ""))


@app.command("model-propose")
def model_propose(
    scorers: str = typer.Option("deepseek", help="Comma-separated aliases. DeepSeek by default, on cost."),
    variant: str = typer.Option("full", help="Evidence condition, the same for every model."),
    limit: Optional[int] = typer.Option(None),
    films: str = typer.Option("", help="Only these films (ids or title fragments)."),
) -> None:
    """Harvest moral propositions again, under other models.

    The prompt and the evidence are unchanged: if the propositions differ, the
    model is the only thing that could have caused it.
    """
    from .analysis import model_structure
    from .llm.providers import missing_credentials

    aliases = _ready_scorers(scorers)
    film_ids = _match_films(films) if films.strip() else _film_ids(limit)
    for alias in aliases:
        console.print(f"\n[bold]{alias}[/] harvesting from {len(film_ids)} films ({variant})")
        stats = model_structure.harvest(alias, film_ids, variant, progress=console.print)
        console.print(f"  {stats['propositions']} propositions, "
                      f"[red]{stats['failed']}[/] failed  {json.dumps(stats['usage'])}")


@app.command("model-axes")
def model_axes(
    scorers: str = typer.Option("deepseek", help="Comma-separated aliases. DeepSeek by default, on cost."),
    k: str = typer.Option("8", help="Axis counts to derive, e.g. 4,6,8,10,12."),
    bank: str = typer.Option("b1"),
    assign: bool = typer.Option(True, help="Also sort the shared bank onto each model's axes."),
) -> None:
    """Have each model name the axes in its OWN harvest, then sort the shared bank.

    Its own harvest deliberately: asking a model to find axes in Claude's
    propositions would test reading comprehension, not moral structure. The
    shared bank is what makes the resulting partitions comparable.
    """
    from .analysis import model_structure

    aliases = _ready_scorers(scorers)
    for n_dims in [int(x) for x in k.split(",") if x.strip()]:
        dim_version = f"k{n_dims}"
        for alias in aliases:
            dims = model_structure.derive_axes(alias, dim_version, n_dims,
                                               progress=console.print)
            table = Table("axis", "question", box=None)
            for d in dims:
                table.add_row(d["name"], d["question"][:88])
            console.print(table)
            if assign:
                n = model_structure.assign_shared(alias, dim_version, bank,
                                                  progress=console.print)
                console.print(f"  [dim]{alias} placed {n} shared items on its {dim_version} axes[/]")


@app.command("model-structure")
def model_structure_cmd(
    version: str = typer.Option("k8", help="Which axis count to report on."),
    bank: str = typer.Option("b1"),
    sweep: str = typer.Option("", help="Compare across counts, e.g. 4,6,8,10,12."),
    worst: int = typer.Option(0, help="Show the N least stable items."),
) -> None:
    """Do different models carve the same moral space, and is eight the joint?"""
    from .analysis import model_structure, structure_stats

    if sweep.strip():
        by_k = {}
        for n in [int(x) for x in sweep.split(",") if x.strip()]:
            parts = model_structure.partitions(f"k{n}", bank)
            if len(parts) > 1:
                by_k[n] = parts
        rows = structure_stats.k_sweep(by_k)
        if not rows:
            console.print("[yellow]need at least two models at two counts[/]")
            raise typer.Exit(1)
        table = Table("k", "models", "pairs", "mean ARI", "min", "max", "chance", box=None)
        for row in rows:
            table.add_row(str(row["k"]), str(row["models"]), str(row["pairs"]),
                          f"[bold]{row['mean_ari']:+.3f}[/]", f"{row['min_ari']:+.3f}",
                          f"{row['max_ari']:+.3f}", f"{row['null']:+.4f}")
        console.print("\n[bold]how much do independent models agree, at each number of axes?[/]")
        console.print(table)
        peak = structure_stats.best_k(rows)
        if peak:
            verdict = ("[yellow]flat — the count came from the prompt, not the material[/]"
                       if peak["flat"] else
                       f"[green]peaks at k={peak['k']}[/] (margin {peak['margin']:+.3f})")
            console.print(f"\n{verdict}")
        raise typer.Exit()

    parts = model_structure.partitions(version, bank)
    if len(parts) < 2:
        console.print(f"[yellow]only {len(parts)} model(s) have {version} assignments[/] — "
                      "run `atlas model-axes` for more")
        raise typer.Exit(1)

    table = Table("pair", "items", "raw", "ARI", "NMI", "chance ARI", "z", box=None)
    for pair, row in structure_stats.pairwise(parts).items():
        colour = ("green" if row["ari"] >= 0.5 else "yellow" if row["ari"] >= 0.25 else "red")
        table.add_row(pair, str(row["n_items"]), f"{row['raw']:.2f}",
                      f"[{colour}]{row['ari']:+.3f}[/]", f"{row['nmi']:.3f}",
                      f"{row['null_ari_mean']:+.4f}",
                      f"{row['z']:.0f}" if row["z"] is not None else "-")
    console.print("\n[bold]do the models group the same items together?[/]")
    console.print(table)
    console.print("[dim]ARI is chance-corrected: two random partitions of this shape "
                  "score about zero, while raw agreement does not.[/]")

    aliases = sorted(parts)
    for i, a in enumerate(aliases):
        for b in aliases[i + 1:]:
            names_a = model_structure.axis_names(a, version)
            names_b = model_structure.axis_names(b, version)
            matched = structure_stats.match_axes(parts[a], parts[b], names_a, names_b)
            if not matched:
                continue
            table = Table(f"{a} axis", f"{b} axis", "shared", "Jaccard", box=None)
            for row in matched:
                colour = ("green" if row["jaccard"] >= 0.5 else
                          "yellow" if row["jaccard"] >= 0.25 else "red")
                table.add_row(row["a_name"][:34], row["b_name"][:34],
                              str(row["shared_items"]), f"[{colour}]{row['jaccard']:.2f}[/]")
            console.print(f"\n[bold]which axis is which — {a} vs {b}[/] "
                          f"[dim](matched by item overlap, not by name)[/]")
            console.print(table)

    if worst:
        rows = structure_stats.item_stability(parts)
        console.print(f"\n[bold]least stable items[/] [dim](their neighbours change with "
                      f"the model — read these before trusting the axis)[/]")
        items = {it["item_id"]: it["text"] for it in dim_mod.bank_items(bank)}
        table = Table("item", "stability", "text", box=None)
        for row in rows[-worst:]:
            table.add_row(row["item_id"], f"[red]{row['stability']:.2f}[/]",
                          items.get(row["item_id"], "")[:76])
        console.print(table)


def _ready_scorers(scorers: str) -> list[str]:
    """Aliases with credentials, having said plainly which were skipped and why."""
    from .llm.providers import missing_credentials

    aliases = [a.strip() for a in scorers.split(",") if a.strip()]
    missing = missing_credentials(aliases)
    for alias, provider in missing.items():
        console.print(f"[yellow]skipping {alias}[/] — set {provider.env_var} ({provider.console})")
    aliases = [a for a in aliases if a not in missing]
    if not aliases:
        console.print("[red]no scorers with credentials[/] — see `atlas models`")
        raise typer.Exit(1)
    return aliases


@app.command("model-bias")
def model_bias_cmd(
    bank: str = typer.Option("b1"),
    version: str = typer.Option("d1", help="Dimension set naming the axes."),
    top: int = typer.Option(12, help="Largest per-axis divergences to show."),
) -> None:
    """Where the scorers agree, where they refuse, and which way each one leans."""
    from .analysis import model_bias

    report = model_bias.report(bank, version)

    t = Table("scorer", "posture", "films", "verdicts", "items/film", "affirm%", "refused", box=None)
    for alias, row in report["scorers"].items():
        t.add_row(alias, row["posture"], str(row["films"]), str(row["verdicts"]),
                  str(row["items_per_film"]),
                  f"{row['affirm_share']:.0%}" if row["affirm_share"] is not None else "-",
                  f"[yellow]{row['refusals']}[/]" if row["refusals"] else "0")
    console.print("\n[bold]what each scorer did with the same bank[/]")
    console.print(t)

    if report["agreement"]:
        t = Table("pair", "shared cells", "raw", "kappa", box=None)
        for pair, row in report["agreement"].items():
            kappa = row["kappa"]
            colour = "green" if kappa and kappa >= 0.6 else "yellow" if kappa and kappa >= 0.4 else "red"
            t.add_row(pair, str(row["shared_cells"]), f"{row['raw']:.2f}",
                      f"[{colour}]{kappa:+.2f}[/]" if kappa is not None else "-")
        console.print("\n[bold]do they agree on the same films and items?[/]")
        console.print(t)
        console.print("[dim]kappa corrects for chance: the verdicts run about two "
                      "affirms per denial, so raw agreement flatters everybody.[/]")

    if report["divergence"]:
        t = Table("scorer", "axis", "gap vs opus", "scorer", "opus", "items", box=None)
        for row in report["divergence"][:top]:
            colour = "red" if abs(row["gap"]) >= 0.2 else "yellow" if abs(row["gap"]) >= 0.1 else "dim"
            t.add_row(row["scorer"], row["axis"], f"[{colour}]{row['gap']:+.2f}[/]",
                      f"{row['scorer_lean']:+.2f}", f"{row['incumbent_lean']:+.2f}", str(row["n"]))
        console.print("\n[bold]same films, different verdict: per-axis lean[/]")
        console.print(t)
        console.print("[dim]The films were identical, so a gap here is the scorer, "
                      "not the corpus.[/]")


@app.command("user-profile")
def user_profile(
    user: str = typer.Option("", help="User id or name captured by the web app."),
    loved: str = typer.Option("", help="Comma-separated titles, scored as if loved."),
    disliked: str = typer.Option("", help="Comma-separated titles, scored as if rejected."),
    version: str = typer.Option("d1"),
    bank: str = typer.Option("b1"),
) -> None:
    """Where a viewer sits on the axes, from their film preferences.

    With `--user` this reads what the person actually told the web app. With
    `--loved`/`--disliked` it scores a hypothetical viewer instead, which is how
    you sanity-check the instrument without needing a real session.
    """
    from .analysis import user_scores as us

    dims = us.load_dimensions(version)
    if not dims:
        console.print(f"[yellow]no dimension set {version!r} — run `atlas dimensions` first[/]")
        raise typer.Exit(1)

    if user:
        from .web.profile_service import moral_profile
        user_id = _resolve_user(user)
        profile = moral_profile(user_id)
        rows = profile.scores
        header = f"{user} — {profile.evidence.films_used} films used"
        if profile.is_provisional:
            header += "  [yellow](provisional)[/]"
    else:
        prefs = ([us.Preference(f, 1.0, "rating", "loved_it") for f in _match_films(loved)]
                 + [us.Preference(f, -1.0, "rating", "not_for_me") for f in _match_films(disliked)])
        if not prefs:
            console.print("[yellow]pass --user, or --loved/--disliked film titles[/]")
            raise typer.Exit(1)
        rows = us.score_preferences(prefs, dims, us.film_stances(version, bank))
        header = f"hypothetical viewer — {len({p.film_id for p in prefs})} films"

    console.print(f"\n[bold]{header}[/]")
    t = Table("axis", "leaning", "score", "items", "films", "conf", box=None)
    for r in rows:
        colour = {"high": "green", "low": "magenta"}.get(r.leaning, "dim")
        t.add_row(r.name, f"[{colour}]{r.leaning.upper()}[/]", f"{r.score:+.2f}",
                  f"{r.evidence_items:g}", str(r.films), f"{r.confidence:.2f}")
    console.print(t)
    for r in rows:
        if r.leaning != "balanced":
            console.print(f"[dim]{r.name}:[/] {r.stance}")


def _resolve_user(user: str) -> str:
    with db.connect(read_only=True) as con:
        row = con.execute(
            "SELECT user_id FROM users WHERE user_id=? OR name=? ORDER BY created_at DESC",
            [user, user],
        ).fetchone()
    if row is None:
        console.print(f"[red]no user {user!r}[/]")
        raise typer.Exit(1)
    return row["user_id"]


def _match_films(titles: str) -> list[str]:
    """Film ids for a comma-separated list of titles, matched loosely on title."""
    if not titles.strip():
        return []
    films = db.list_films()
    out = []
    for wanted in (t.strip() for t in titles.split(",") if t.strip()):
        hit = next((f for f in films if f["film_id"] == wanted
                    or wanted.lower() in f["title"].lower()), None)
        if hit is None:
            console.print(f"[yellow]no film matching {wanted!r} — skipped[/]")
        else:
            out.append(hit["film_id"])
    return out


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


@app.command("dataset")
def dataset_cmd(
    out: str = typer.Option(
        "src/frontend/public/data/atlas.json",
        help="Where to write. The default is the path the interface reads, and "
             "is copied into the published site by `vite build`."),
    version: str = typer.Option("d1", help="Dimension version."),
    bank: str = typer.Option("b1", help="Item bank version."),
    evidence: bool = typer.Option(
        True, "--evidence/--no-evidence",
        help="Write each film's source text — plot, themes, reception, dialogue "
             "— as its own file beside the index, so the explorer can show what "
             "every claim was read from."),
    check: bool = typer.Option(
        False, "--check",
        help="Write nothing; exit non-zero if the built file is behind the store. "
             "For CI and pre-commit, so a snapshot cannot be published stale."),
) -> None:
    """Build the JSON the interface visualises, from what the store holds now.

    Safe to run at any stage: a pipeline that has not reached scoring produces
    a document that says so rather than one that fails.
    """
    from .analysis import dataset as dataset_mod

    # "Safe to run at any stage" means any stage of the pipeline, not "before
    # there is a database". Without this the failure is a raw OperationalError
    # about a missing table, which tells you nothing about what to do next.
    if not settings().db_path.exists():
        console.print(f"[red]no store at[/] {settings().db_path}")
        console.print("[dim]run `atlas init`, then ingest, before building the dataset[/]")
        raise typer.Exit(1)

    # The published site serves a committed snapshot, so "somebody forgot to
    # rebuild it" is a silent, arbitrarily large error. This turns it into a
    # failing check: the store's mtime against the file's.
    if check:
        target = Path(out)
        if not target.exists():
            console.print(f"[red]no dataset at[/] {out} — run `atlas dataset`")
            raise typer.Exit(1)

        # Counts rather than mtimes. The store runs in WAL mode, so writes land
        # in atlas.sqlite-wal and the main file's timestamp barely moves until a
        # checkpoint — an mtime comparison reports "current" while a sweep is
        # actively writing, which is the precise reassurance this must not give.
        built = json.loads(target.read_text()).get("totals") or {}
        current = dataset_mod.totals(version, bank)
        drift = {key: (built.get(key), value) for key, value in current.items()
                 if built.get(key) != value}
        if drift:
            console.print(f"[red]{out} is behind the store[/]")
            table = Table("layer", "in the file", "in the store", box=None)
            for key, (was, now) in sorted(drift.items()):
                table.add_row(key, str(was), f"[bold]{now}[/]")
            console.print(table)
            console.print("[dim]run `atlas dataset` and commit the result[/]")
            raise typer.Exit(1)
        console.print(f"[green]{out} matches the store[/] ({current.get('films')} films, "
                      f"{current.get('scores')} scores)")
        raise typer.Exit()

    path, payload = dataset_mod.write(out, version, bank, evidence)
    totals = payload["totals"]

    table = Table("in the bundle", "n", box=None)
    table.add_row("films", str(totals["films"]))
    table.add_row("with a skeleton", f"{totals['films_with_skeleton']}/{totals['films']}")
    table.add_row("read under 'full'", f"{totals['films_with_full_skeleton']}/{totals['films']}")
    table.add_row("placed on the axes", f"{totals['films_profiled']}/{totals['films']}")
    table.add_row("named dimensions", str(totals["dimensions"]))
    table.add_row("active bank items", str(totals["bank_items"]))
    table.add_row("scores", str(totals["scores"]))
    console.print(table)

    written = payload["_written"]
    console.print(f"\n[green]wrote[/] {path} "
                  f"[dim]({written['index_bytes'] / 1024:.0f} KB index)[/]")
    if written["evidence_files"]:
        console.print(
            f"[green]wrote[/] {path.with_suffix('')}/ [dim]"
            f"({written['evidence_files']} films, "
            f"{written['evidence_bytes'] / 1024 / 1024:.1f} MB of source text, "
            f"fetched only when a film is opened)[/]")
    if not totals["dimensions"] or not totals["films_profiled"]:
        console.print(
            "[yellow]No axes or no placements[/] — the interface will show the "
            "extraction stage only, which is honest but not the whole story. "
            "Run `atlas dimensions` and `atlas score` to fill it in.")
    console.print("[dim]the interface reads this at /data/atlas.json[/]")


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


@app.command("taste-null")
def taste_null_cmd(
    scorers: str = typer.Option("deepseek", help="Comma-separated aliases."),
    variant: str = typer.Option("subs", help="Evidence condition to read."),
    banks: str = typer.Option("", help="Comma-separated banks. Default: every bank "
                                       "the scorer has verdicts for."),
    iterations: int = typer.Option(200, help="Permutations for the null."),
) -> None:
    """Re-run the permutation test on verdicts with taste subtracted out.

    Run this after ANY reanalysis that moves the verdicts, the taste dimensions
    or the film placements. The stored answer carries a fingerprint of those
    three, and the atlas draws no adjusted chart at all while it disagrees —
    which is the failure everybody wants, rather than a chart quietly showing
    last month's corpus.
    """
    from .analysis import taste_null
    from . import db as _db

    for alias in _ready_scorers(scorers):
        wanted = [b.strip() for b in banks.split(",") if b.strip()]
        if not wanted:
            with _db.connect(read_only=True) as con:
                wanted = [r["bank_version"] for r in con.execute(
                    "SELECT DISTINCT bank_version FROM model_verdicts "
                    "WHERE scorer=? AND variant=?", [alias, variant])]
        for bank in wanted:
            console.print(f"[bold]{alias}[/] · {bank} — residualising and permuting…")
            try:
                result = taste_null.compute(alias, bank_version=bank, variant=variant,
                                            n_iter=iterations)
            except Exception as error:
                console.print(f"  [yellow]failed: {type(error).__name__}: {error}[/]")
                continue
            if not result:
                console.print("  [yellow]skipped — no taste positions for these films[/]")
                continue
            taste_null.store(alias, variant, bank, result)
            console.print(
                f"  {result['films']} films · taste in {result['control_n_factors']} factors"
                f" · taste out {result['n_factors']} factors")
