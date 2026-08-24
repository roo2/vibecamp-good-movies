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
  return body.models || []
}

// One film on the axes the product itself reads. No scorer argument on purpose:
// which model backs the product is a server setting, and a phone screen that
// hard-coded 'deepseek' would silently keep reading the old model the day that
// setting changed.
export async function loadProductFilmAxes(filmId) {
  return get(`/api/factors/product/films/${encodeURIComponent(filmId)}`)
}

export async function loadFactors(scorer, variant = 'subs', bank = '') {
  const query = new URLSearchParams({ variant })
  if (bank) query.set('bank', bank)
  return get(`/api/factors/${encodeURIComponent(scorer)}?${query}`)
}

// A factor's margin is how far its eigenvalue cleared the 95th percentile of a
// null built by permuting each item's own column. The server no longer sends
// anything below this — DISPLAY_MARGIN in factor_names.py — so the value here
// is the same bar, kept so the scree can still shade the factors that did not
// make it. A factor 13% clear of chance is real and is also thin, and shown
// beside one that cleared by 500% a reader weighs them the same.
export const CLEAR_MARGIN = 0.25

export function isClear(factor) {
  return (factor.margin ?? 0) >= CLEAR_MARGIN
}
