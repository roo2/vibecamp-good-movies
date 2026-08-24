import React from 'react'
import { loadProductFilmAxes } from '../services/factorService.js'

// Where a recommended film stands morally, on the card that recommends it.
//
// Unobtrusive by construction: closed it is one line of type and a few short
// bars, because the reason someone is on this screen is to pick a film, not to
// read an instrument. The justification is one tap away and never in the way —
// a person who wants to know WHY a film reads as it does can ask, and everyone
// else sees a shape and moves on.
//
// Only axes the film actually engaged appear. An axis it never raised would
// draw at the centre and read as "balanced", which is a claim the data does not
// make.

const strongest = (factors, limit) => factors
  .filter((factor) => factor.score != null && factor.items > 0)
  .sort((a, b) => Math.abs(b.score) - Math.abs(a.score))
  .slice(0, limit)

function Axis({ factor, open, onToggle }) {
  const side = factor.score >= 0 ? 'high' : 'low'
  const stance = factor.score >= 0 ? factor.pole_high : factor.pole_low
  const magnitude = Math.abs(factor.score) * 50

  return (
    <li className={`axis-strip-row ${side} ${open ? 'open' : ''}`}>
      <button type="button" onClick={onToggle} aria-expanded={open}>
        {/* The end it landed on, not the axis name: on a card this small the
            useful three words are the ones describing where the film sits. */}
        <span className="axis-strip-name">
          {factor.score >= 0 ? factor.pole_high_label : factor.pole_low_label}
          <em>over {factor.score >= 0 ? factor.pole_low_label : factor.pole_high_label}</em>
        </span>
        <span className="axis-strip-track">
          <i style={factor.score >= 0
            ? { insetInlineStart: '50%', inlineSize: `${magnitude}%` }
            : { insetInlineEnd: '50%', inlineSize: `${magnitude}%` }} />
        </span>
      </button>
      {open && (
        <div className="axis-strip-why">
          <p className="axis-strip-stance">{stance}</p>
          {/* Three verdicts, not all of them: this is a reason, not an audit. */}
          <ul>
            {(factor.verdicts || []).slice(0, 3).map((verdict) => (
              <li key={verdict.item_id} className={verdict.verdict}>
                <b>{verdict.verdict}</b>
                <span>{verdict.text}</span>
              </li>
            ))}
          </ul>
          <p className="axis-strip-count">
            read from {factor.items} proposition{factor.items === 1 ? '' : 's'}
          </p>
        </div>
      )}
    </li>
  )
}

export default function FilmAxisStrip({ filmId, limit = 4 }) {
  const [factors, setFactors] = React.useState(null)
  const [openId, setOpenId] = React.useState(null)

  React.useEffect(() => {
    if (!filmId) return undefined
    let live = true
    setFactors(null)
    setOpenId(null)
    loadProductFilmAxes(filmId)
      .then((data) => live && setFactors(strongest(data.factors || [], limit)))
      // A film nobody has scored yet is not an error worth a message on a card
      // whose job is to recommend it. The strip simply is not there.
      .catch(() => live && setFactors([]))
    return () => { live = false }
  }, [filmId, limit])

  if (!factors?.length) return null

  return (
    <div className="axis-strip">
      <span className="axis-strip-label">Where it stands · tap for why</span>
      <ul>
        {factors.map((factor) => (
          <Axis
            key={factor.factor_id}
            factor={factor}
            open={openId === factor.factor_id}
            onToggle={() => setOpenId(openId === factor.factor_id ? null : factor.factor_id)}
          />
        ))}
      </ul>
    </div>
  )
}
