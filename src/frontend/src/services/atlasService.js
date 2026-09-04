// The dataset the explorer reads: the API, and only the API.
//
// There used to be a second source — a JSON file `atlas dataset` wrote into
// `public/` and `vite build` copied into the published site — tried FIRST, so
// on any machine that actually had the store the page showed whatever state
// that file was last built in. That cost a real bug: a section was added here,
// the store held everything it needed, and the page rendered nothing, because a
// snapshot from an earlier state answered first and won.
//
// Reordering fixed the symptom and left the cause: a build step that has to be
// remembered, and a file that is wrong by default between pipeline runs. So the
// step is gone. `/api/atlas` reads the store per request and caches against a
// fingerprint of its contents, which makes the page correct by construction
// rather than by discipline.
//
// The trade is availability for correctness, and it is worth naming. If the API
// is unreachable this page shows an error instead of stale numbers. That is the
// intended behaviour — a moral atlas quietly serving last week's corpus is
// worse than one that admits it is offline — but it does mean the published
// site now depends on the runner being up, where before it could limp along on
// the bundled file.

const LIVE_PATH = '/api/atlas'

async function fetchJson(path, timeoutMs) {
  const controller = timeoutMs ? new AbortController() : null
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null
  let response
  try {
    response = await fetch(path, {
      headers: { Accept: 'application/json' },
      signal: controller?.signal,
    })
  } finally {
    if (timer) clearTimeout(timer)
  }
  if (!response.ok) throw new Error(`${path} responded ${response.status}`)
    const body = await response.json()
  if (!body || !Array.isArray(body.films)) throw new Error(`${path} is not the atlas dataset`)
  return body
}

export async function loadAtlas() {
  try {
    return await fetchJson(LIVE_PATH)
  } catch (cause) {
    throw new Error(
      'The atlas API is not answering. Start it with `uvicorn moral_atlas.web.app:app`, '
      + 'or check the runner — this page reads the store directly and has no cached copy '
      + 'to fall back to.',
      { cause },
    )
  }
}

// A film's source text — plot, themes, reception, dialogue. Fetched only when
// somebody opens that film: it averages ~80KB and the dialogue tracks run to
// 170KB, which is not something to put in front of every visitor to the index.
export async function loadFilmEvidence(filmId) {
  // Same rule as the index: the store, not a snapshot. A published evidence
  // file went stale in exactly the same way, and silently — the reader is being
  // shown "the text every claim about this film was read from", so serving a
  // copy from before the last ingest is the one thing it must not do.
  const id = encodeURIComponent(filmId)
  const response = await fetch(`/api/atlas/films/${id}`, { headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error('No source text is available for this film.')
  const body = await response.json()
  if (!Array.isArray(body?.layers)) throw new Error('No source text is available for this film.')
  return body
}

// Everything below is presentation arithmetic over the payload. It lives here
// rather than in the components so the numbers on screen have one definition.

export function fateDistribution(atlas) {
  const counts = new Map((atlas.fate_order || []).map((fate) => [fate, 0]))
  for (const film of atlas.films) {
    const fate = film.skeleton?.antagonist_fate
    if (fate && counts.has(fate)) counts.set(fate, counts.get(fate) + 1)
  }
  return [...counts].map(([fate, n]) => ({ fate, n })).filter((row) => row.n > 0)
}

// Where every film sits on one axis, strongest position first. `net` is the mean
// signed verdict of that film's scored items on the axis: +1 is every item
// affirming the high pole, -1 every item denying it.
export function filmsOnAxis(atlas, dimId) {
  return atlas.films
    .map((film) => {
      const row = film.profile?.find((entry) => entry.dim_id === dimId)
      return row ? { film, ...row } : null
    })
    .filter(Boolean)
    .sort((a, b) => b.net - a.net)
}

// The 2x2 the explorer called the hard case: whether a film supplies a backstory
// that mitigates, against what it then does to the antagonist.
export function originByFate(atlas) {
  const fates = ['destroyed', 'punished_but_alive', 'reconciled', 'escapes']
  const rows = [true, false].map((originGiven) => ({
    originGiven,
    cells: fates.map((fate) => ({
      fate,
      films: atlas.films.filter(
        (film) => film.skeleton
          && film.skeleton.antagonist_origin_given === originGiven
          && film.skeleton.antagonist_fate === fate,
      ),
    })),
  }))
  return { fates, rows }
}

export function ironyFilms(atlas) {
  return atlas.films.filter((film) => film.skeleton?.depicts_but_does_not_endorse)
}

export const FATE_LABELS = {
  destroyed: 'Destroyed',
  punished_but_alive: 'Punished, alive',
  reconciled: 'Reconciled',
  becomes_protagonist: 'Becomes protagonist',
  escapes: 'Escapes',
  no_clear_antagonist: 'No clear antagonist',
  unknown: 'Unknown',
}

const FILTERS = {
  all: () => true,
  irony: (film) => film.skeleton?.depicts_but_does_not_endorse,
  origin: (film) => film.skeleton?.antagonist_origin_given,
  destroyed: (film) => film.skeleton?.antagonist_fate === 'destroyed',
  reconciled: (film) => film.skeleton?.antagonist_fate === 'reconciled',
  escapes: (film) => film.skeleton?.antagonist_fate === 'escapes',
}

export function filterFilms(atlas, { query = '', filter = 'all' } = {}) {
  const predicate = FILTERS[filter] || FILTERS.all
  const needle = query.trim().toLowerCase()
  return atlas.films.filter((film) => {
    if (!predicate(film)) return false
    if (!needle) return true
    const haystack = [
      film.title, String(film.year || ''), film.description,
      ...Object.values(film.skeleton || {}).map((value) => (Array.isArray(value) ? value.join(' ') : String(value ?? ''))),
    ].join(' ').toLowerCase()
    return haystack.includes(needle)
  })
}

// Where every film sits on all three axes, joined from the per-axis
// distributions the factors payload already carries.
// The two axes every view of this reading uses: the ones the server flags as
// the product's, falling back to the first two by margin for readings the
// product does not use.
//
// Exported because three things need the SAME answer — the plane, the set
// centroids, and the labels the page prints beside them. They each had their
// own `.slice(0, 2)`, which is the margin order, and the moment axis selection
// started asking whether an axis can place a person those stopped agreeing
// with the compass and with each other.
export function plotAxes(factors) {
  const all = (factors?.factors || factors || [])
  const flagged = all.filter((f) => f && f.product)
  return flagged.length >= 2 ? flagged : all
}

// Which TWO of them a plane draws. Separate from the ordering above because
// they answer different questions: `plotAxes` says which axes the product
// reads, this says which pair the reader is currently looking at.
//
// The default is the first two, which is the support order — margin over the
// null first. Deliberately NOT the two that separate ideological lists best:
// this project reports that those lists separate, and picking the axes for
// doing so would make the finding a consequence of the choice.
export function axisPair(axes, pair) {
  const list = axes || []
  if (list.length < 2) return list
  if (!pair) return list.slice(0, 2)
  const find = (id) => list.find((f) => f.factor_id === id)
  const x = find(pair[0]) || list[0]
  const y = find(pair[1]) || list.find((f) => f !== x) || list[1]
  return x === y ? list.slice(0, 2) : [x, y]
}

export function filmPositions(factors, space = 'moral', pair = null) {
  const list = axisPair(plotAxes(factors), pair)
  const out = new Map()
  if (list.length < 2) return out
  list.forEach((factor, k) => {
    for (const row of factor.distribution || []) {
      const seen = out.get(row.film_id) || []
      // The SAME quantity the plane draws in this space. The rule used to be
      // `score_adjusted ?? score` unconditionally, which is what the plane did
      // too — so when the plane moved to the raw position the centres would
      // have gone on being computed from residuals, and a set's crosshair would
      // sit where none of its dots are. Its own comment warned about exactly
      // that; the two just have to be told the same thing.
      seen[k] = space === 'adjusted' ? row.score_adjusted : row.score
      out.set(row.film_id, seen)
    }
  })
  for (const [id, v] of out) {
    if (v.length !== 2 || v.some((n) => typeof n !== 'number')) out.delete(id)
  }
  return out
}

// The average position of a set, in the axes' own units. One implementation,
// used both to draw the marker and to print the numbers beside it, so the two
// cannot drift apart and quietly disagree about where a set is.
export function setCentroid(positions, filmIds) {
  const found = (filmIds || []).map((id) => positions.get(id)).filter(Boolean)
  if (!found.length) return null
  // Over the axes actually present, not a hard-coded three. Two are plotted, so
  // the third index was undefined for every set and printed as "−NaN".
  const width = Math.min(...found.map((v) => v.length))
  const mean = Array.from({ length: width },
    (_, k) => found.reduce((a, v) => a + v[k], 0) / found.length)
  return { mean, n: found.length }
}

// The points and pole labels for the film plane, in either space.
//
// Lives here rather than in a page because two pages draw it. The corpus page
// and the atlas already drifted apart once — one defaulted to the reading with
// the most verdicts and the other to the reading the product uses, so the same
// film showed different numbers depending on which page you opened.
// The named taste dimensions in the order everything shows them: by how
// reliably each places a PERSON, not by how much of the corpus it covers. The
// plot sorted by variance and the side panel by readability, so the same
// dimension was first in one and third in the other — and took a different
// colour in each.
export function tasteAxes(taste) {
  return (taste?.dimensions || [])
    .filter((d) => d.status === 'named')
    .slice()
    .sort((a, b) => (b.profile_reliability ?? 0) - (a.profile_reliability ?? 0))
}

export function planePoints(factors, taste, space = 'moral', pair = null) {
  if (space === 'taste') {
    const dims = tasteAxes(taste)
    if (dims.length < 2) return null
    // Honour the chosen pair, the way the moral plane does. This took the first
    // two dimensions and ignored `pair` entirely, so the taste plot had no axis
    // picker and could only ever draw one view of sixteen dimensions.
    const at = (id, fallback) => {
      const found = dims.findIndex((d) => d.dim_id === id)
      return found < 0 ? fallback : found
    }
    const xi = at(pair?.[0], 0)
    const yi = at(pair?.[1], xi === 1 ? 0 : 1)
    const dx = dims[xi]
    const dy = dims[yi]
    const points = (taste.films || []).flatMap((f) => {
      const x = f.position?.[String(dx.dim_id)]
      const y = f.position?.[String(dy.dim_id)]
      return typeof x === 'number' && typeof y === 'number'
        ? [{ id: f.film_id, title: f.title, x, y }] : []
    })
    return {
      points,
      xAxis: { high: dx.pole_high, low: dx.pole_low },
      yAxis: { high: dy.pole_high, low: dy.pole_low },
      // Which dimensions these are, in the order the palette indexes by, so the
      // plot's pole labels take the same colours the side panel gives the same
      // dimensions. They disagreed because the plot took the first two by
      // VARIANCE and the panel the first five by how well each places a person.
      index: [xi, yi],
    }
  }

  // The axes the app reads a person on, when the server says which they are.
  // Taking the first two by position instead means taking the MARGIN order,
  // which stopped matching the product the moment axis selection also asked
  // whether an axis can place a person: the plot drew "Intrinsic vs
  // Utilitarian", which places nobody above noise, while the compass beside it
  // drew a different axis and nothing on either said why. Readings the product
  // does not use carry no flag, and those still fall back to the first two.
  const list = axisPair(plotAxes(factors), pair)
  if (list.length < 2) return null
  const byFilm = new Map()
  list.forEach((factor, k) => {
    for (const row of factor.distribution || []) {
      const seen = byFilm.get(row.film_id) || { title: row.title, v: [] }
      // THE RAW POSITION, which is what the axis labels name and what every
      // other screen reports for the same film.
      //
      // This drew `score_adjusted` — the residual after removing the part of a
      // film's moral position that its taste position predicts. That is a real
      // and useful quantity, but it answers a different question: not "how
      // deterministic is this film" but "how much more deterministic than its
      // taste predicts". Plotted under poles reading Redemption and
      // Determinism it was read as the first, and it disagreed with the film's
      // own panel for 19% of films on the leading axis and 32% on the second.
      // Forrest Gump sat at the far Determinism end of the plot at +1.11 while
      // its panel said -0.45, Redemption; The Godfather flipped the other way.
      //
      // Nothing on either screen said one was adjusted. Showing the adjustment
      // is worth doing, but it needs its own labels rather than borrowing these.
      // In the adjusted space, the residual — and the labels below say so.
      seen.v[k] = space === 'adjusted' ? row.score_adjusted : row.score
      byFilm.set(row.film_id, seen)
    }
  })
  const points = [...byFilm.entries()]
    .filter(([, f]) => f.v.length === 2 && f.v.every((n) => typeof n === 'number'))
    .map(([id, f]) => ({ id, title: f.title, x: f.v[0], y: f.v[1] }))
  // A residual is not a position, so it must not wear a position's label. The
  // ends are "further toward this pole than taste predicts", which is what the
  // qualifier says in the space where that is what is drawn.
  const qualify = (text) => (space === 'adjusted' && text ? `${text}, beyond taste` : text)
  const label = (f, end) => qualify(f?.[`pole_${end}_label`] || f?.name || '')
  return {
    points,
    xAxis: { high: label(list[0], 'high'), low: label(list[0], 'low') },
    yAxis: { high: label(list[1], 'high'), low: label(list[1], 'low') },
  }
}
