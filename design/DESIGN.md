# Parable — the design, and why it is this way

Fourteen artboards live in this folder. This file is the reasoning behind them,
so you can argue with the decisions instead of guessing at them.

## The problem the interface actually solves

A friend suggested swiping on posters. Swiping is a fine *verb* — people know it,
it is fast, it works one-handed on a couch. But posters are the wrong *noun*.
The thing this product knows that others don't is what a story argues, so the
interface has to capture what two people believe a good story should say, and it
has to do it without ever asking anyone an ethics question.

Four moves do that.

### 1. Infer from films, don't ask about values

Screen 2 is twelve familiar films with three buttons: loved it / not for me /
haven't seen. That is the whole capture mechanism, and it is invisible — nobody
experiences it as a personality test. It is also, deliberately, the same act as
the atlas's own labelling step: **every person who onboards is labelling films
for the model.** Onboarding and training are one motion, not two.

Screen 3 handles cold-start ties with a moral fork, shown **de-branded** — no
title, no poster, no cast, just two premises. The moment you show a poster you
are asking "do you like Disney", which is a different question. The pair on
screen 3 is The Lion King and Maleficent, the atlas's master anchors, written out
as prose.

### 2. Show people the read, and let them correct it

Screen 4 renders the profile as tension bars — a marker between two poles, each
pole anchored to a film so the axis explains itself in movie terms instead of
ethics vocabulary. The markers drag.

This screen is not decoration. If the app forms an opinion about your morality
and won't show it to you, it is doing something slightly sinister; if it shows
you and lets you argue, it is a mirror. That is the difference between the
product feeling insightful and feeling presumptuous, and it costs one screen.

### 3. Colour is identity, not decoration

**Amber is always you. Teal is always the other person.** It never varies. That
one rule means no screen with two opinions on it needs a legend, and a two-dot
chip on a film card tells you instantly whether a value matched you, them, or
both. A value matching neither renders in the border grey — there is no third
person, so there is no third hue.

### 4. Friction is the feature

Votes are blind until both are in, so neither person anchors the other. But the
overlap screens do not smooth disagreement away — they *name* it: "You want the
debt paid. Sam wants it repaired." That is the screenshot people send each other,
and it reframes the app from a compromise machine into a conversation starter.
An app that only finds agreement has no reason to exist beyond a shared watchlist.

## Two shapes for the same two screens

Screens 4 and 6 exist twice, as **bars** (4, 6) and as a **map** (4b, 6b).

The bars are right if factor analysis returns four or more factors. The map is
right if it returns two — and two dimensions was an explicit goal, so the map may
well win. On the map the shortlist is not a computed list, it is *visibly* the
films sitting in the gap between two points, which is a better explanation than
any sentence.

`variance_explained` decides it. If the top two factors account for something
like 70% of the spread, plot them. If it is 40%, the plane is a flattering lie
and the bars are more honest. **Do not pick on aesthetics** — the map is the
prettier screen and that is not a reason.

## What the mockups deliberately do not do

- **No fake status bar and no fake keyboard.** The real ones render on top; a
  painted one looks doubled. The 52px top padding is that space, left alone.
- **No third accent colour.** Adding one breaks the amber/teal rule silently.
- **No confident presentation for unread films.** Card 4 on screen 7 admits we
  haven't read it and that popularity is a weaker reason. The temptation to hide
  thin coverage behind confident UI is the main way this product could start
  lying to people.
- **No genre filters anywhere.** The pitch is that genre is the wrong axis. A
  genre filter on screen 1 would concede the argument.

## Open questions — the honest list

1. **Bars or map** — settled by `variance_explained`, not by taste. See above.
2. **The axis labels on screens 4 and 6 are placeholders.** They stand in for
   whatever the factor analysis names. If that unsettles you, relabel them
   `Factor 1 / Factor 2` until real names exist; the components don't care.
3. **The "why you're seeing this" line on a card** — is it insight or clutter?
   It's a tweak on artboard 7, so toggle it and judge.
4. **A post-watch screen doesn't exist yet.** "Did it land?" after the credits is
   the cheapest correction signal available — the film argued something and you
   either bought it or you didn't — and it would close the loop on the profile.
   Left out on purpose rather than added unasked. It is the first thing I'd build.
5. **Pass-the-phone mode is one card on screen 5, not a designed flow.** Two
   people on one couch with one device is probably the *common* case, and it
   currently has less design than the two-device case.
6. **Nothing is designed for the empty state** — a person whose taste sits far
   from everyone, or a pair with an empty shortlist. That will happen.

## Directions not taken

Page 2 of the canvas holds two low-fi alternates, kept because both drop the
swipe deck and so test whether it is load-bearing at all. **B** makes the value
dials the entire interface (fast, but people are poor at naming their own values
in the abstract). **C** poses one moral question per night and makes the answer
the shelf (a reason to open the app daily, but one question is a thin signal and
it only gets good after weeks). Neither is dead.
