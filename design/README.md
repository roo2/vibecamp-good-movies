# design/

The interface for Parable: fourteen phone artboards, the reasoning behind them,
and the tokens to build from.

| File | What it is |
|---|---|
| `parable-screen-flow.html` | **The canvas.** Open in a browser — all fourteen screens on one pan/zoom surface, with notes. |
| `*.dc.html` | One artboard each. Plain HTML with inline styles: the source the canvas is built from, and directly liftable as markup. |
| `canvas.json` | Layout — positions, page split, the sticky notes. |
| `DESIGN.md` | Why the design is this way, and the open questions. **Read this first.** |
| `INTERFACE-CONTRACT.md` | What the UI needs from the atlas, and the five things it doesn't produce yet. |
| `tokens.css` | Real palette, type ramp, spacing, control sizes. |
| `fixtures/session.json` | Sample payload matching the contract — build against this today. |

## Seeing it

```bash
open design/parable-screen-flow.html
```

That is the whole thing, offline, no install. Pan with a drag, zoom with a
pinch or wheel, and there are two pages — **Flow** and **Alternates** — in the
toolbar. Screen 7 is live: tap the vote buttons and the deck advances.

There is also a hosted copy at
<https://claude.ai/code/artifact/99431e20-ef0f-4daa-8fb7-f2d7bcefca3a>, which is
editable in place if you have access to it. Access is not guaranteed outside the
owning account, so **the file in this repo is the canonical copy** — if the two
ever disagree, the repo wins.

## Changing a screen

The artboards are ordinary HTML. Edit the `.dc.html` file, then rebuild the
canvas from this folder:

```bash
cd design
node "<claude-design-skill>/seed-canvas.mjs" \
  --template "<claude-design-skill>/payload.template.html" \
  --out parable-screen-flow.html --title "Parable Screen Flow" \
  --artboard Welcome.dc.html --artboard SeenIt.dc.html --artboard Fork.dc.html \
  --artboard Compass.dc.html --artboard PairUp.dc.html --artboard CommonGround.dc.html \
  --artboard Main.dc.html --artboard Match.dc.html --artboard Tiebreak.dc.html \
  --artboard Limits.dc.html --artboard Map.dc.html --artboard MapPair.dc.html \
  --artboard DirectionB.dc.html --artboard DirectionC.dc.html \
  --canvas canvas.json
```

The helper ships with Claude Code's `design` skill — ask Claude to `/design` and
it will re-seed for you, which is easier than finding the path. If you'd rather
not deal with any of that: **edit the `.dc.html` files and ignore the canvas.**
They render standalone in a browser and they are the real source.

## Building from it

Start at `tokens.css` and `INTERFACE-CONTRACT.md`, not at the canvas. The
artboards are inline-styled on purpose — that made them editable in the visual
canvas, but it means you should lift *values* from them, not markup patterns.
Componentise as you would normally.

Two rules worth carrying into the real build, because they are easy to break by
accident and the whole design leans on them:

- **Amber is the viewer, teal is the other person, everywhere.** No exceptions,
  and no third accent.
- **An unread film never gets a read film's presentation.** See card 4 on
  screen 7.
