import React from 'react'

// Where a film sits on the dimensions of TASTE, shown beside its moral position.
//
// Both belong on the same screen, because the interesting fact about a film is
// often the gap between them: a film can be unremarkable on every moral axis
// and highly distinctive in what kind of film it is, or the reverse. Showing
// only the moral position invites a reader to attribute to morality whatever
// they can see about the film.
//
// It borrows the moral scale's markup deliberately — same grid, same track,
// same bar growing from the centre — because these two things were built a week
// apart and looked it: different row heights, different markers, different type.
// A reader should not have to learn two instruments to read one film.
//
// What stays different is the colour. The moral axes carry the two colours the
// plot uses for them; taste is deliberately neutral, because it is not a moral
// claim and should not borrow the authority of looking like one.
//
// Positions are percentiles rather than raw scores. The underlying component
// scores differ by an order of magnitude between dimensions, so "55.7" and
// "-3.3" are not comparable and printing them side by side would mislead.

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
    <div className="detail-field film-taste">
      <span>And what kind of film it is</span>
      <p className="atlas-note">
        Discovered from which films the same people enjoy, not from anything this film says.
        Nothing here is moral — which is the point of showing it apart.
      </p>
      <ul className="film-factors">
        {rows.map(({ dim, pct }) => {
          // Drawn from the middle, like the moral bars, so the two scales read
          // as one instrument. The middle is the median film, and the bar is
          // how far from typical this one is.
          const magnitude = Math.abs(pct - 50)
          const high = pct >= 50
          return (
            <li key={dim.dim_id} className="film-factor taste">
              <span className="film-factor-scale">
                <em className={!high ? 'lit' : ''}>{dim.pole_low}</em>
                <span className="film-factor-track">
                  <u className="film-factor-mid" />
                  <i className="film-factor-bar taste"
                     style={high
                       ? { insetInlineStart: '50%', inlineSize: `${magnitude}%` }
                       : { insetInlineEnd: '50%', inlineSize: `${magnitude}%` }} />
                </span>
                <em className={high ? 'lit' : ''}>{dim.pole_high}</em>
              </span>
              <span className="film-factor-score">
                {pct}<em>percentile</em>
              </span>
            </li>
          )
        })}
      </ul>
      <p className="atlas-note">
        Read as a percentile: the share of films this one sits above. The middle of each bar is
        the typical film.
      </p>
    </div>
  )
}
