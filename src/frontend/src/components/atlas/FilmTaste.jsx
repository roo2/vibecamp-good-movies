import React from 'react'
import AxisScale from './AxisScale.jsx'

// Where a film sits on the dimensions of TASTE, beside its moral position.
//
// Both belong on the same screen because the interesting fact about a film is
// often the gap between them: a film can be unremarkable on every moral axis
// and highly distinctive in what kind of film it is, or the reverse.
//
// It draws the same row the moral axes draw, through the same component. It
// used to draw its own — a marker on a track, a percentile, and a sentence
// naming the end it leaned to — which made a taste dimension look like a
// different kind of measurement from a moral one, and squeezed the pole labels
// into two narrow wrapping columns to make room for prose nobody needed. The
// bar says which end and how far. The percentile said it again in numbers.
//
// What differs is colour, and it differs by family rather than by dimension:
// violet and rose here, amber and teal for the moral axes, so a hue never means
// two things.

// Five, matching the profile, and picked the same way — by how reliably a
// dimension places somebody from about ten ratings rather than by how much of
// the corpus it covers. The sixth measures at 0.25 where these five sit between
// 0.41 and 0.51.
const SHOWN = 5

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
      // Standardised against the corpus, not ranked against it. A percentile
      // maps most films to near zero — Master and Commander sits at the 56th on
      // one dimension, which drew a bar 6% of the track wide and read as a
      // rendering fault rather than as "this film is typical". A z-score keeps
      // the middle crowded where it belongs while giving a distinctive film a
      // bar you can see. Divided by three because that is where the corpus
      // runs out; beyond it the scale clamps.
      const mean = all.reduce((t, v) => t + v, 0) / all.length
      const sd = Math.sqrt(all.reduce((t, v) => t + (v - mean) ** 2, 0) / all.length)
      return { dim: d, value: sd > 0 ? (here - mean) / (sd * 3) : 0 }
    }).filter(Boolean)
  }, [taste, filmId])

  if (!rows.length) return null

  return (
    <div className="detail-field film-taste">
      <span>And what kind of film it is</span>
      <p className="atlas-note">
        Discovered from which films the same people enjoy, not from anything this film says.
      </p>
      <ul className="film-factors">
        {rows.map(({ dim, value }, index) => (
          <li key={dim.dim_id} className="film-factor">
            <AxisScale low={dim.pole_low} high={dim.pole_high} value={value}
                       family="taste" index={index} />
          </li>
        ))}
      </ul>
    </div>
  )
}
