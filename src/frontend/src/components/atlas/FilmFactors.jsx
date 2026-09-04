import React from 'react'
import Verdicts from './Verdicts.jsx'
import { loadFilmAxes } from '../../services/factorService.js'

// One film against every axis, and the verdicts that put it there.
//
// The bar is centred, because the axis has two directions and a left-anchored
// bar would read as "how much of this quality the film has" — which is not what
// a score of -0.6 means. It means the film denied most of what this axis asks.
//
// An axis the film never engaged shows as absent rather than as zero. Silence
// and even-handedness look identical in a number and are opposites in a film:
// one never raised the question, the other weighed it and split.

function Bar({ score }) {
  const magnitude = Math.abs(score) * 50
  // A span rather than a div: this sits inside a <button>, which may only
  // contain phrasing content. The stylesheet gives it `display: block`, without
  // which an inline box would ignore its height and collapse to zero width —
  // pinning every bar to the left.
  return (
    <span className="film-factor-track">
      <u className="film-factor-mid" />
      <i
        className={score >= 0 ? 'film-factor-bar high' : 'film-factor-bar low'}
        style={score >= 0
          ? { insetInlineStart: '50%', inlineSize: `${magnitude}%` }
          : { insetInlineEnd: '50%', inlineSize: `${magnitude}%` }}
      />
    </span>
  )
}

function Row({ factor }) {
  const [open, setOpen] = React.useState(false)
  const scored = factor.score != null
  const side = factor.score >= 0 ? 'high' : 'low'

  // The row is two labels and a bar, and nothing else.
  //
  // It used to carry the axis name, the score, the item count and a "reads as"
  // line quoting the pole sentence — four ways of saying what the bar and the
  // two labels already say, stacked above an expansion that then said them
  // again. The name repeats the poles; the "reads as" sentence is the pole
  // sentence verbatim; the question is a third phrasing of the same contrast.
  // What is left is the position, and what put it there.
  return (
    <li className={scored ? `film-factor ${side}` : 'film-factor absent'}>
      <button type="button" onClick={() => scored && setOpen(!open)} aria-expanded={open}
              disabled={!scored}
              aria-label={scored
                ? `${factor.name}. Reads as ${side === 'high' ? factor.pole_high_label : factor.pole_low_label}`
                : `${factor.name}. This film did not raise it`}>
        {scored ? (
          <span className="film-factor-scale">
            <em className={side === 'low' ? 'lit' : ''}>{factor.pole_low_label}</em>
            <Bar score={factor.score} />
            <em className={side === 'high' ? 'lit' : ''}>{factor.pole_high_label}</em>
          </span>
        ) : (
          <span className="film-factor-scale">
            <em>{factor.pole_low_label}</em>
            <span className="film-factor-absent">did not raise this</span>
            <em>{factor.pole_high_label}</em>
          </span>
        )}
      </button>

      {open && (
        <div className="film-factor-why">
          {/* Both ends, with the film's own lit. Showing only the side it landed
              on reads as a verdict; showing both makes it a position — the
              reader can see what the other answer would have been. */}
          <div className="film-factor-poles">
            <p className={side === 'low' ? 'pole low here' : 'pole low'}>
              <b>{factor.pole_low_label}</b> {factor.pole_low}
            </p>
            <p className={side === 'high' ? 'pole high here' : 'pole high'}>
              <b>{factor.pole_high_label}</b> {factor.pole_high}
            </p>
          </div>

          <Verdicts verdicts={factor.verdicts}
                    poleHigh={factor.pole_high_label}
                    poleLow={factor.pole_low_label} />

          {/* The count still has to be said. One proposition at -1.00 looks
              exactly as certain as forty, and is not. */}
          <p className="film-factor-thin">
            {factor.score >= 0 ? '+' : ''}{factor.score.toFixed(2)} from {factor.items}{' '}
            proposition{factor.items === 1 ? '' : 's'}
            {factor.items === 1 && ' — as extreme as a single answer can make it, rather than a settled reading'}
          </p>
        </div>
      )}
    </li>
  )
}

// `bank` matters as much as `scorer` and was not being sent. The endpoint falls
// back to the bank a scorer wrote for ITSELF, so picking "dolphin → deepseek"
// changed the axes listed at the top of the atlas and left every individual
// film still reported on deepseek's own six — two different readings on one
// screen, with nothing to say they were different.
export function FilmFactors({ scorer, filmId, variant = 'subs', bank = '' }) {
  const [state, setState] = React.useState({ status: 'loading' })

  React.useEffect(() => {
    if (!scorer || !filmId) return undefined
    let live = true
    setState({ status: 'loading' })
    loadFilmAxes({ scorer, variant, bank_version: bank }, filmId)
      .then((data) => live && setState({ status: 'ready', data }))
      .catch(() => live && setState({ status: 'failed' }))
    return () => { live = false }
  }, [scorer, filmId, variant, bank])

  if (state.status === 'loading') return <p className="detail-muted">Reading its positions…</p>
  if (state.status === 'failed') {
    return <p className="detail-muted">No axis positions for this film yet.</p>
  }

  // The axes the app reads a person on, which the server names rather than
  // leaving to position. Taking the first two meant taking the MARGIN order,
  // and that stopped being the product's pair once axis selection also asked
  // whether an axis can place a person — so this panel described a film on one
  // axis while the plot beside it used another. Readings the product does not
  // use carry no flag and still fall back to the first two.
  // EVERY axis the product reads, not the first two. The plane draws two
  // because a plane has two dimensions; a film's reading has no such limit, and
  // slicing it here would describe a film on fewer axes than the compass reads
  // the person sitting next to it.
  const all = state.data.factors || []
  const flagged = all.filter((factor) => factor.product)
  const factors = flagged.length ? flagged : all.slice(0, 2)
  const engaged = factors.filter((factor) => factor.score != null)

  return (
    <div className="detail-field">
      <span>Where {state.data.scorer} places it</span>
      {engaged.length === 0 ? (
        <p className="detail-muted">
          Scored, but it engaged too few propositions to place on any axis.
        </p>
      ) : (
        <>
          <ul className="film-factors">
            {factors.map((factor) => <Row key={factor.factor_id} factor={factor} />)}
          </ul>
          {/* The count only earns its place when it is not the full set: "3 of 3
              engaged" tells a reader nothing they cannot see. */}
          <p className="atlas-note">
            Tap an axis for the propositions behind it.
            {engaged.length < factors.length
              && ` This film raised ${engaged.length} of ${factors.length}.`}
          </p>
        </>
      )}
    </div>
  )
}

export default FilmFactors
