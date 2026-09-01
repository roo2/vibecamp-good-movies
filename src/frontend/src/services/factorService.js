// The axes as the films produced them, per model.
//
// Read live from the store, like everything else on this page. There is no
// snapshot to fall back to and that is deliberate: a committed copy of an
// analysis is wrong by default the moment the next scoring run lands, and this
// page exists to show what the data says now.

async function get(path) {
  const response = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`${path} responded ${response.status}`)
  return response.json()
}

// Which models have been run. The toggle is built from this rather than a
// hardcoded list, so a model appears exactly when it has something to show.
export async function loadModels() {
  const body = await get('/api/factors')
  // Withdrawn models ride along: a scorer that was tried and could not do the
  // job is a result, and dropping it silently reads as never having asked.
  return { models: body.models || [], withdrawn: body.withdrawn || [] }
}

// One film on the axes the product itself reads. No scorer argument on purpose:
// which model backs the product is a server setting, and a phone screen that
// hard-coded 'deepseek' would silently keep reading the old model the day that
// setting changed.
// One film on one READING's axes. A reading is {scorer, variant, bank_version}
// and all three matter: the endpoint falls back to the bank a scorer wrote for
// itself, so dropping the bank silently answers a different question. Two
// components built this URL by hand and both omitted it, which put the axes of
// one reading beside the films of another on the same screen.
export async function loadFilmAxes(reading, filmId) {
  const query = new URLSearchParams({
    variant: reading?.variant || 'subs',
    ...(reading?.bank_version ? { bank: reading.bank_version } : {}),
  })
  return get(`/api/factors/${encodeURIComponent(reading.scorer)}/films/`
             + `${encodeURIComponent(filmId)}?${query}`)
}

export async function loadFilmSets() {
  return get('/api/factors/sets')
}

export async function loadProductFilmAxes(filmId) {
  return get(`/api/factors/product/films/${encodeURIComponent(filmId)}`)
}

export async function loadFactors(scorer, variant = 'subs', bank = '') {
  const query = new URLSearchParams({ variant })
  if (bank) query.set('bank', bank)
  return get(`/api/factors/${encodeURIComponent(scorer)}?${query}`)
}

// A factor's margin is how far its eigenvalue cleared the 95th percentile of a
// null built by permuting each item's own column. 5% is the bar the analysis
// itself applies, and now the only one: a 25% threshold used to sit on top of
// it, which was a layout convenience deciding what counted as a finding.
export const CLEAR_MARGIN = 0.05

export function isClear(factor) {
  return (factor.margin ?? 0) >= CLEAR_MARGIN
}

// The dimensions of taste, and where each film sits on them. Separate from the
// moral axes on purpose: they are a different measurement of the same films —
// who enjoys this, rather than what it argues — and the page shows the
// relationship between the two rather than merging them into one list.
//
// Returns empty when nothing has been derived, so the section hides itself
// rather than the page failing on a database that predates it.
export async function loadTaste() {
  try {
    const body = await get('/api/factors/taste')
    return { dimensions: body.dimensions || [], films: body.films || [] }
  } catch {
    return { dimensions: [], films: [] }
  }
}
