// The dataset the explorer reads.
//
// Two sources, in this order, because the demo and the dev box are not the same
// machine. `/data/atlas.json` is a file `atlas dataset` writes into `public/`,
// which `vite build` copies into the published site; the demo serves it straight
// from the bucket, so the page renders whether or not the runner is up.
//
// It is deliberately NOT under /api. CloudFront routes /api/* to the runner and
// everything else to the bucket, so a published file under that prefix would be
// answered by the API — which has no route for it — rather than by S3.
//
// `/api/atlas` is the live API, which is what you want locally and on the
// runner: it re-reads the store on every request, so a pipeline run shows up on
// reload without a rebuild.
const STATIC_PATH = '/data/atlas.json'
const LIVE_PATH = '/api/atlas'

async function fetchJson(path) {
  const response = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`${path} responded ${response.status}`)
  // A static host answers a missing path with index.html and a 200, so the
  // status alone does not prove this is the dataset. Parsing does.
  const body = await response.json()
  if (!body || !Array.isArray(body.films)) throw new Error(`${path} is not the atlas dataset`)
  return body
}

export async function loadAtlas() {
  try {
    return await fetchJson(STATIC_PATH)
  } catch (staticError) {
    try {
      return await fetchJson(LIVE_PATH)
    } catch {
      throw new Error(
        'No dataset published yet. Run `atlas dataset` to build it, or start the API.',
        { cause: staticError },
      )
    }
  }
}

// A film's source text — plot, themes, reception, dialogue. Fetched only when
// somebody opens that film: it averages ~80KB and the dialogue tracks run to
// 170KB, which is not something to put in front of every visitor to the index.
export async function loadFilmEvidence(filmId) {
  const id = encodeURIComponent(filmId)
  try {
    const body = await fetch(`/data/atlas/${id}.json`, { headers: { Accept: 'application/json' } })
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
    if (!Array.isArray(body?.layers)) throw new Error('not an evidence document')
    return body
  } catch {
    return fetchEvidenceLive(id)
  }
}

async function fetchEvidenceLive(id) {
  const response = await fetch(`/api/atlas/films/${id}`, { headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error('No source text has been published for this film.')
  const body = await response.json()
  if (!Array.isArray(body?.layers)) throw new Error('No source text has been published for this film.')
  return body
}

// Everything below is presentation arithmetic over the payload. It lives here
// rather than in the components so the numbers on screen have one definition.

export function dimensionsByItems(atlas) {
  return [...(atlas.dimensions || [])].sort((a, b) => b.n_items - a.n_items)
}

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
