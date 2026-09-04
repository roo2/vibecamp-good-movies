import React from 'react'

// Where a film sits on the dimensions of TASTE, shown beside its moral position.
//
// Both belong on the same screen, because the interesting fact about a film is
// often the gap between them: a film can be unremarkable on every moral axis and
// highly distinctive in what kind of film it is, or the reverse.
//
// It uses the COMPASS's rows — the same ones a person sees for their own taste —
// so a reader who has learnt to read their own profile can read a film without
// learning anything new. That includes the colour: these rows were deliberately
// grey while the moral axes sat above them wearing the plot's two colours, and
// stopped needing to be once the profile dropped the moral axes and gave each
// taste dimension a hue of its own. A dimension keeps its colour between the two
// screens, which is the whole point of sharing the markup.
//
// Positions are percentiles rather than raw scores. The underlying component
// scores differ by an order of magnitude between dimensions, so "55.7" and
// "-3.3" are not comparable and printing them side by side would mislead.

// Five, matching the profile, and picked the same way — by how reliably a
// dimension places somebody from about ten ratings rather than by how much of
// the corpus it covers. The sixth measures at 0.25 where these five sit between
// 0.41 and 0.51.
const SHOWN = 5

// The same five hues the profile uses, in the same order, so a dimension is the
// same colour wherever a reader meets it.
const HUES = ['#eda36b', '#5cc3c0', '#b58ce0', '#e0899a', '#93c56b']

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
      </p>
      <ul className="taste-axes">
        {rows.map(({ dim, pct }, index) => {
          const high = pct >= 50
          const far = Math.abs(pct - 50) >= 20
          return (
            <li key={dim.dim_id} className="taste-axis"
                style={{ '--hue': HUES[index % HUES.length] }}>
              <span className="taste-axis-poles">
                <span className={high ? '' : 'lit'}>{dim.pole_low}</span>
                <span className={high ? 'lit' : ''}>{dim.pole_high}</span>
              </span>
              <span className="taste-axis-track">
                <i className="taste-axis-mid" />
                <i className="taste-axis-band"
                   style={high
                     ? { left: '50%', width: `${pct - 50}%` }
                     : { left: `${pct}%`, width: `${50 - pct}%` }} />
                <b className="taste-axis-marker" style={{ left: `${pct}%` }} />
              </span>
              <span className="taste-axis-read">
                {ordinal(pct)} percentile
                {far && <> — sits toward <b>{(high ? dim.pole_high : dim.pole_low).toLowerCase()}</b></>}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
