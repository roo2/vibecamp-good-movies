# Parable — where things stand

Two people, one evening, and the argument about what to watch. The bet is that
the useful thing to match strangers or partners on is not genre or mood but
**what a story argues** — and that this is measurable from the film's own text.

The project is in two halves that meet at one seam.

| | Where | State |
|---|---|---|
| **The atlas** — discovering moral structure from film text | `src/moral_atlas/`, see `README.md` | Ingestion and scoring built and verified on 40 films. Factor analysis not yet. |
| **The interface** — capturing two people and matching them | `design/`, see `design/README.md` | Fourteen screens designed. Nothing built. |
| **The seam** | `design/INTERFACE-CONTRACT.md` | Specified, with a working fixture. |

## Start here

```bash
open design/parable-screen-flow.html      # the fourteen screens, offline
```

Then read, in this order:

1. `design/DESIGN.md` — why the interface is shaped this way, and the six open
   questions. Arguing with this is the point.
2. `design/INTERFACE-CONTRACT.md` — what the UI needs from the atlas. This is the
   most useful document in the repo if you are picking up the front end, because
   it means **you can build the entire interface today** against
   `design/fixtures/session.json` without the pipeline running.
3. `README.md` — the atlas machine: setup, the CLI, the phase-0 experiment.

## What the design is waiting on

One number decides a real design question. The compass and overlap screens exist
in two forms — stacked bars and a 2-D map — and `variance_explained` from the
factor analysis picks the winner. If the top two factors explain most of the
spread, the map is right and it is much the better screen. If they explain
little, the plane is a flattering lie and the bars are the honest choice. Don't
pick on looks.

Five things the interface needs that the atlas doesn't produce yet are listed at
the top of `INTERFACE-CONTRACT.md`, in blocking order. The first — a one-sentence
spoiler-free statement of each film's moral question — is the single most
important string in the product and currently nothing generates it.

## Ground rules that are easy to break by accident

- **Amber is you, teal is the other person.** Everywhere, no exceptions, no third
  accent colour. It is why no screen needs a legend.
- **An unread film never borrows a read film's confident presentation.** Subtitle
  coverage will be patchy; the design admits that rather than hiding it.
- **Posters are fetched at render time and never stored or modelled.** TMDB's
  terms bar using its content as ML input — this is a licensing constraint, not a
  preference.
- **No genre filters.** The whole pitch is that genre is the wrong axis.

## Suggested split

The two halves are genuinely independent right now, which is the good news. The
front end can be built end to end against the fixture; the atlas can reach factor
analysis without knowing anything about screens. The only real coordination is
the five gaps in the contract, and the `variance_explained` number.
