import React from 'react'
import { polePair } from './polePalette.js'

// The films furthest along each taste dimension, in both directions.
//
// The one part of the taste half a reader can check by eye. Everything else on
// that side is a number about 162,000 strangers; this is a list of films they
// may have seen, and the names of the dimensions were written from 1,128
// human-assigned tags and never from titles — so if the titles look right, that
// is a check the naming could have failed and did not.
//
// Drawn with the values side's own markup, because it is the same object: an
// axis, its two ends, and the films at each. It used to be two bare lists of
// titles with no positions, which read as a different kind of claim from the
// anchors under a values axis when it is exactly the same kind. The pole
// colours come from the taste palette by the same rule, so a dimension keeps
// its colour here, on the plot and on a film's card.
const TAKE = 5

function poles(films, dimId, take = TAKE) {
  const rows = films
    .map((f) => ({ id: f.film_id || f.title, title: f.title, at: f.position?.[String(dimId)] }))
    .filter((f) => typeof f.at === 'number')
    .sort((a, b) => b.at - a.at)
  return { high: rows.slice(0, take), low: rows.slice(-take).reverse() }
}

const signed = (n) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(2)}`

function Side({ side, label, films }) {
  return (
    <div className={`anchors-side ${side}`}>
      <span className="anchors-label">Most {label}</span>
      <ul>
        {films.map((film) => (
          <li key={film.id}>
            {/* Static rather than a button: a values anchor opens into the
                propositions that put the film there, and a taste position has
                no such reading behind it — it is co-preference, which is one
                number all the way down. A control that opened nothing would
                promise otherwise. */}
            <span className="anchor-static">
              <b>{film.title}</b>
              <em>{signed(film.at)}</em>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function TastePoles({ taste, heading = 'The films at each end' }) {
  const dims = (taste?.dimensions || [])
    .filter((d) => d.status === 'named')
    .slice()
    .sort((a, b) => (b.profile_reliability ?? 0) - (a.profile_reliability ?? 0))
  if (!dims.length) return null

  return (
    <section className="taste">
      <h2>{heading}</h2>
      <p className="atlas-note">
        Nothing else on this side can be checked by eye. This can: for each named dimension, the
        films the data puts furthest along it, in both directions. The names were written from
        1,128 human-assigned tags and never from titles.
      </p>
      {dims.map((d, index) => {
        const pair = polePair('taste', index)
        const { high, low } = poles(taste.films || [], d.dim_id)
        if (!high.length && !low.length) return null
        return (
          <div className="taste-poles" key={d.dim_id}
               style={{ '--low': pair.low, '--high': pair.high }}>
            <h3>{d.pole_low} <i aria-hidden="true">↔</i> {d.pole_high}</h3>
            <div className="anchors">
              <Side side="high" label={d.pole_high} films={high} />
              <Side side="low" label={d.pole_low} films={low} />
            </div>
          </div>
        )
      })}
    </section>
  )
}
