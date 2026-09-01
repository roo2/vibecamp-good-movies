import React from 'react'

// Where a film sits on the dimensions of TASTE, shown beside its moral position.
//
// Both belong on the same screen, because the interesting fact about a film is
// often the gap between them: a film can be unremarkable on every moral axis
// and highly distinctive in what kind of film it is, or the reverse. Showing
// only the moral position invites a reader to attribute to morality whatever
// they can see about the film.
//
// Positions are shown as percentiles rather than raw scores. The underlying
// numbers are component scores whose units differ by an order of magnitude
// between dimensions, so "55.7" and "-3.3" are not comparable and reading them
// side by side would be actively misleading.

const SHOWN = 5

export default function FilmTaste({ taste, filmId }) {
  const rows = React.useMemo(() => {
    const dims = (taste?.dimensions || []).filter((d) => d.status === 'named').slice(0, SHOWN)
    const films = taste?.films || []
    if (!dims.length || !films.length) return []
    const mine = films.find((f) => f.film_id === filmId)
    if (!mine) return []

    return dims.map((d) => {
      const key = String(d.dim_id)
      const all = films.map((f) => f.position?.[key]).filter((v) => typeof v === 'number')
      const here = mine.position?.[key]
      if (typeof here !== 'number' || all.length < 20) return null
      const below = all.reduce((n, v) => n + (v < here ? 1 : 0), 0)
      return { dim: d, pct: Math.round((below / all.length) * 100) }
    }).filter(Boolean)
  }, [taste, filmId])

  if (!rows.length) return null

  return (
    <div className="film-taste">
      <h4>And what kind of film it is</h4>
      <p className="atlas-note">
        Discovered from which films the same people enjoy, not from anything this film says.
        Nothing here is moral — that is the point of showing it separately.
      </p>
      <ul>
        {rows.map(({ dim, pct }) => (
          <li key={dim.dim_id}>
            <span className="film-taste-low">{dim.pole_low}</span>
            <span className="film-taste-track" aria-hidden="true">
              <i style={{ left: `${pct}%` }} />
            </span>
            <span className="film-taste-high">{dim.pole_high}</span>
            <b>{pct}<small>%</small></b>
          </li>
        ))}
      </ul>
      <p className="atlas-note">
        Read as a percentile: the share of films this one sits above on that dimension.
      </p>
    </div>
  )
}
