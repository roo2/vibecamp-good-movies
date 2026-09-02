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
export function filmPositions(factors) {
  const list = (factors || []).slice(0, 2)
  const out = new Map()
  if (list.length < 2) return out
  list.forEach((factor, k) => {
    for (const row of factor.distribution || []) {
      const seen = out.get(row.film_id) || []
      // Taste-adjusted, matching the plane and the axis tables. A set centre
      // computed from raw positions while the dots were drawn from adjusted
      // ones would put the crosshair somewhere no film is.
      seen[k] = row.score_adjusted ?? row.score
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
  const mean = [0, 1, 2].map((k) => found.reduce((a, v) => a + v[k], 0) / found.length)
  return { mean, n: found.length }
}

// The points and pole labels for the film plane, in either space.
//
// Lives here rather than in a page because two pages draw it. The corpus page
// and the atlas already drifted apart once — one defaulted to the reading with
// the most verdicts and the other to the reading the product uses, so the same
// film showed different numbers depending on which page you opened.
export function planePoints(factors, taste, space = 'moral') {
  if (space === 'taste') {
    const dims = (taste?.dimensions || []).filter((d) => d.status === 'named').slice(0, 2)
    if (dims.length < 2) return null
    const [dx, dy] = dims
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
    }
  }

  // The axes the app reads a person on, when the server says which they are.
  // Taking the first two by position instead means taking the MARGIN order,
  // which stopped matching the product the moment axis selection also asked
  // whether an axis can place a person: the plot drew "Intrinsic vs
  // Utilitarian", which places nobody above noise, while the compass beside it
  // drew a different axis and nothing on either said why. Readings the product
  // does not use carry no flag, and those still fall back to the first two.
  const all = factors?.factors || []
  const flagged = all.filter((f) => f.product)
  const list = (flagged.length >= 2 ? flagged : all).slice(0, 2)
  if (list.length < 2) return null
  const byFilm = new Map()
  list.forEach((factor, k) => {
    for (const row of factor.distribution || []) {
      const seen = byFilm.get(row.film_id) || { title: row.title, v: [] }
      // Taste-adjusted where it exists. A raw position confounds what a film
      // argues with what kind of film it is.
      seen.v[k] = row.score_adjusted ?? row.score
      byFilm.set(row.film_id, seen)
    }
  })
  const points = [...byFilm.entries()]
    .filter(([, f]) => f.v.length === 2 && f.v.every((n) => typeof n === 'number'))
    .map(([id, f]) => ({ id, title: f.title, x: f.v[0], y: f.v[1] }))
  const label = (f, end) => f?.[`pole_${end}_label`] || f?.name || ''
  return {
    points,
    xAxis: { high: label(list[0], 'high'), low: label(list[0], 'low') },
    yAxis: { high: label(list[1], 'high'), low: label(list[1], 'low') },
  }
}
