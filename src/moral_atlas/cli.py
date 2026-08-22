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
from .analysis import dimensions as dim_mod
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


@app.command("populate-artwork")
def populate_artwork(force: bool = typer.Option(False, help="Refresh URLs that are already present.")) -> None:
    """Populate remote lead-image URLs from Wikipedia; no API key required."""
    from .sources import wikipedia as wiki_mod
    result = wiki_mod.populate_artwork(force=force)
    console.print(f"[green]artwork ready[/] updated {result['updated']}, missing {result['missing']}, skipped {result['skipped']}")


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
    scorers: str = typer.Option("grok,deepseek", help="Comma-separated aliases; see `atlas models`."),
    bank: str = typer.Option("b1"),
    variant: str = typer.Option("spine", help="Evidence condition; the same one for every scorer."),
    limit: Optional[int] = typer.Option(None, help="Score only the first N films."),
    films: str = typer.Option("", help="Only these films (ids or title fragments, comma-separated)."),
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
        stats = model_bias.scan(alias, film_ids, bank, variant, progress=console.print)
        console.print(f"  scored {stats['scored']}, refused [yellow]{stats['refused']}[/], "
                      f"failed [red]{stats['failed']}[/]  {json.dumps(stats['usage'])}")


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
        profile = moral_profile(user_id, version, bank)
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
        "src/frontend/public/api/atlas.json",
        help="Where to write. The default is the path the interface reads, and "
             "is copied into the published site by `vite build`."),
    version: str = typer.Option("d1", help="Dimension version."),
    bank: str = typer.Option("b1", help="Item bank version."),
    evidence: bool = typer.Option(
        True, "--evidence/--no-evidence",
        help="Write each film's source text — plot, themes, reception, dialogue "
             "— as its own file beside the index, so the explorer can show what "
             "every claim was read from."),
) -> None:
    """Build the JSON the interface visualises, from what the store holds now.

    Safe to run at any stage: a pipeline that has not reached scoring produces
    a document that says so rather than one that fails.
    """
    from .analysis import dataset as dataset_mod
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
    console.print("[dim]the interface reads this at /api/atlas.json[/]")


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
