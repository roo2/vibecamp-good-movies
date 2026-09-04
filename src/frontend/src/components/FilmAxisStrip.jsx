import React from 'react'
import { loadProductFilmAxes, loadTaste } from '../services/factorService.js'
import { polePair } from './atlas/polePalette.js'

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

// Server order, which is by how well supported the axis is — the same order the
// atlas lists them in and the same order a person's own compass uses. This used
// to sort by how hard THIS film leaned, which put a strong reading of a weak
// axis above a moderate reading of the corpus's clearest one, and meant the
// axes appeared in a different sequence on every screen that showed them.

// How far from the corpus centre a film has to sit before the card will name
// which end it is on, in standard deviations.
//
// Half rather than the three quarters this started at. The floor exists to stop
// the card asserting a pole on a rounding error — the 2019 Lion King at 0.31 —
// not to hold out for a dramatic reading, and three quarters was silencing
// films that had something to say. Half still excludes that film and everything
// like it while leaving one film in ten blank instead of one in four.
export const TASTE_FLOOR = 0.5

const shown = (factors, limit) => factors
  .filter((factor) => factor.score != null && factor.items > 0)
  .slice(0, limit)

// Which taste dimensions to name for one film, and where each sits.
//
// Standardised against the corpus rather than ranked — a percentile puts most
// films within a hair of the middle and draws a bar too small to read.
//
// The dimensions chosen are the ones this film is most DISTINCTIVE on, not the
// first in the list. Most films are unremarkable on most dimensions, so taking the top of
// a fixed order showed two flat bars for nearly every film and buried the one
// thing that made it unusual. Ranked by distance from the corpus centre.
//
// The palette index stays the one from the shared order, so a dimension keeps
// its colour wherever it appears — otherwise the same dimension would be
// amber on one film's card and green on the next, depending only on how
// strongly each film happened to sit on it.
//
// And a dimension has to CLEAR TASTE_FLOOR before it is named at all. Naming
// a pole is a claim, and ranking alone will always find a strongest one: the
// 2019 Lion King sits within a third of a standard deviation of the centre on
// every dimension, and the card still called it a slapdash spectacle because
// that was its largest rounding error. A film with nothing to say now says
// nothing.
export function tasteRowsFor(taste, filmId, tasteLimit) {
  const dims = (taste?.dimensions || [])
    .filter((d) => d.status === 'named')
    .slice()
    .sort((a, b) => (b.profile_reliability ?? 0) - (a.profile_reliability ?? 0))
  const films = taste?.films || []
  const mine = films.find((f) => f.film_id === filmId)
  if (!mine || !dims.length) return []
  return dims.map((d, index) => {
    const key = String(d.dim_id)
    const all = films.map((f) => f.position?.[key]).filter((v) => typeof v === 'number')
    const here = mine.position?.[key]
    if (typeof here !== 'number' || all.length < 20) return null
    const mean = all.reduce((t, v) => t + v, 0) / all.length
    const sd = Math.sqrt(all.reduce((t, v) => t + (v - mean) ** 2, 0) / all.length)
    const z = sd > 0 ? (here - mean) / sd : 0
    return { dim: d, at: Math.max(-1, Math.min(1, z / 3)), z, index }
  }).filter(Boolean)
    .filter((row) => Math.abs(row.z) >= TASTE_FLOOR)
    .sort((a, b) => Math.abs(b.at) - Math.abs(a.at))
    .slice(0, tasteLimit)
}

function Axis({ factor, open, onToggle, index, expandable = true }) {
  const side = factor.score >= 0 ? 'high' : 'low'
  // The axis's own two colours, the same pair the atlas and the film panel use,
  // so a colour means one thing across every screen that shows an axis.
  const pair = polePair('moral', index)
  const stance = factor.score >= 0 ? factor.pole_high : factor.pole_low
  const magnitude = Math.abs(factor.score) * 50
  const heaviest = Math.max(
    ...(factor.verdicts || []).map((v) => v.weight || 0), 0.0001)

  // The end it landed on, not the axis name: on a card this small the useful
  // three words are the ones describing where the film sits.
  const inner = (
    <>
      <span className="axis-strip-name">
        {factor.score >= 0 ? factor.pole_high_label : factor.pole_low_label}
        <em>over {factor.score >= 0 ? factor.pole_low_label : factor.pole_high_label}</em>
      </span>
      <span className="axis-strip-track">
        <i style={factor.score >= 0
          ? { insetInlineStart: '50%', inlineSize: `${magnitude}%` }
          : { insetInlineEnd: '50%', inlineSize: `${magnitude}%` }} />
      </span>
    </>
  )

  return (
    <li className={`axis-strip-row ${side} ${open ? 'open' : ''}`}
        style={{ '--low': pair.low, '--high': pair.high }}>
      {expandable
        ? <button type="button" onClick={onToggle} aria-expanded={open}>{inner}</button>
        : <span className="axis-strip-fixed">{inner}</span>}
      {expandable && open && (
        <div className="axis-strip-why">
          <p className="axis-strip-stance">{stance}</p>
          {/* Three verdicts, not all of them: this is a reason, not an audit.
              The bar under each is that proposition's loading on THIS axis, the
              same measure the film and atlas pages draw, so a reader meeting it
              in both places is reading one thing. It is scaled against the
              heaviest proposition on the whole axis rather than the heaviest of
              the three shown — within three the top bar would always be full
              and the shape would say nothing. */}
          <ul>
            {(factor.verdicts || []).slice(0, 3).map((verdict) => (
              <li key={verdict.item_id} className={verdict.verdict}>
                <b>{verdict.verdict}</b>
                <span>
                  {verdict.text}
                  {verdict.weight != null && (
                    <span className="axis-strip-weight"
                          title={`How much this proposition defines this axis (loading ${verdict.weight})`}>
                      <i style={{ inlineSize: `${Math.round((verdict.weight / heaviest) * 100)}%` }} />
                    </span>
                  )}
                </span>
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

// Three moral axes, because three is what the reading supports and showing two
// of them left a reader wondering which one was missing and why. Taste follows,
// because a card recommending a film should say what KIND of film it is — the
// half of the answer that actually predicts whether somebody enjoys it.
// `expandable` is off on the swipe card. A row that opens on tap changes the
// card's height, and a card that changes height either overflows the screen or
// needs a scroll container — and a scroll container inside a swipe target eats
// the swipe, which is what it did.
export default function FilmAxisStrip({
  filmId, limit = 3, tasteLimit = 3, expandable = true,
}) {
  const [factors, setFactors] = React.useState(null)
  const [taste, setTaste] = React.useState(null)
  const [openId, setOpenId] = React.useState(null)

  React.useEffect(() => {
    if (!filmId) return undefined
    let live = true
    setFactors(null)
    setOpenId(null)
    loadProductFilmAxes(filmId)
      .then((data) => live && setFactors(shown(data.factors || [], limit)))
      // A film nobody has scored yet is not an error worth a message on a card
      // whose job is to recommend it. The strip simply is not there.
      .catch(() => live && setFactors([]))
    return () => { live = false }
  }, [filmId, limit])

  React.useEffect(() => {
    let live = true
    loadTaste().then((t) => live && setTaste(t)).catch(() => live && setTaste(null))
    return () => { live = false }
  }, [])

  const tasteRows = React.useMemo(
    () => tasteRowsFor(taste, filmId, tasteLimit), [taste, filmId, tasteLimit])

  if (!factors?.length && !tasteRows.length) return null

  return (
    <div className="axis-strip">
      <span className="axis-strip-label">
        {expandable ? 'Where it stands · tap for why' : 'Where it stands'}
      </span>
      <ul>
        {factors.map((factor, index) => (
          <Axis
            key={factor.factor_id}
            factor={factor}
            index={index}
            expandable={expandable}
            open={openId === factor.factor_id}
            onToggle={() => setOpenId(openId === factor.factor_id ? null : factor.factor_id)}
          />
        ))}
      </ul>
      {tasteRows.length > 0 && (
        <div className="axis-strip-taste">
          <span className="axis-strip-label">And what kind of film</span>
          <ul>
            {tasteRows.map(({ dim, at, index }) => {
              const pair = polePair('taste', index)
              const high = at >= 0
              return (
                <li key={dim.dim_id} style={{ '--low': pair.low, '--high': pair.high }}>
                  <span className="axis-strip-name">
                    {high ? dim.pole_high : dim.pole_low}
                    <em>over {high ? dim.pole_low : dim.pole_high}</em>
                  </span>
                  <span className={`axis-strip-track ${high ? 'high' : 'low'}`}>
                    <i style={high
                      ? { insetInlineStart: '50%', inlineSize: `${Math.abs(at) * 50}%` }
                      : { insetInlineEnd: '50%', inlineSize: `${Math.abs(at) * 50}%` }} />
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
