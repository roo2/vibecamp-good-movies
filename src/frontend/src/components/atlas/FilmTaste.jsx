import React from 'react'

// Where a film sits on the dimensions of TASTE, shown beside its moral position.
//
// Both belong on the same screen, because the interesting fact about a film is
// often the gap between them: a film can be unremarkable on every moral axis
// and highly distinctive in what kind of film it is, or the reverse. Showing
// only the moral position invites a reader to attribute to morality whatever
// they can see about the film.
//
// It borrows the COMPASS's markup — the same rows a person sees for their own
// taste in their profile — rather than the film panel's moral rows. Those put
// both pole labels and the track in one three-column grid, which works while
// the labels are short and collapses when they are not: "Enjoyable trash" and
// "Acclaimed craft" ran into each other and the track shrank to a stub. The
// compass row gives the labels a line of their own and the track the full
// width, and it is what a reader has already learnt on their own profile.
//
// What stays different is the colour. The moral axes carry the two colours the
// plot uses for them; taste is deliberately neutral, because it is not a moral
// claim and should not borrow the authority of looking like one.
//
// Positions are percentiles rather than raw scores. The underlying component
// scores differ by an order of magnitude between dimensions, so "55.7" and
// "-3.3" are not comparable and printing them side by side would mislead.

// Four, matching the profile, and picked the same way — by how reliably a
// dimension places somebody from about ten ratings rather than by how much
// of the corpus it covers. A reader who has seen their own four and then
// opens a film should be reading the same four back.
const SHOWN = 4

// 73th, 21th, 3th. The suffix depends on the last two digits, not the last one.
function ordinal(n) {
  const tens = n % 100
  if (tens >= 11 && tens <= 13) return `${n}th`
  return `${n}${{ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'}`
}

export default function FilmTaste({ taste, filmId }) {
  const rows = React.useMemo(() => {
    const dims = (taste?.dimensions || [])
      .filter((d) => d.status === 'named')
      .slice()
      .sort((a, b) => (b.profile_reliability ?? 0) - (a.profile_reliability ?? 0))
      .slice(0, SHOWN)
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
      <ul className="moral-axes taste-axes">
        {rows.map(({ dim, pct }) => (
          <li key={dim.dim_id} className="moral-axis taste">
            <span className="moral-axis-row">
              <span className="moral-axis-poles">
                <span className={pct < 50 ? 'lit' : ''}>{dim.pole_low}</span>
                <span className={pct >= 50 ? 'lit' : ''}>{dim.pole_high}</span>
              </span>
              <span className="moral-axis-track" aria-hidden="true">
                <i className="moral-axis-mid" />
                <b className="moral-axis-marker" style={{ left: `${pct}%` }} />
              </span>
              <span className="moral-axis-evidence">{ordinal(pct)} percentile</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="taste-axes-note">
        Read as a percentile: the share of films this one sits above. The middle of each
        track is the typical film.
      </p>
    </div>
  )
}
