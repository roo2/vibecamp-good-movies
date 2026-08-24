import React from 'react'

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
  return (
    <div className="film-factor-track">
      <u className="film-factor-mid" />
      <i
        className={score >= 0 ? 'film-factor-bar high' : 'film-factor-bar low'}
        style={score >= 0
          ? { insetInlineStart: '50%', inlineSize: `${magnitude}%` }
          : { insetInlineEnd: '50%', inlineSize: `${magnitude}%` }}
      />
    </div>
  )
}

function Row({ factor }) {
  const [open, setOpen] = React.useState(false)
  const scored = factor.score != null
  const side = factor.score >= 0 ? 'high' : 'low'
  // Which end of the axis the film actually landed on, said in the axis's own
  // words. A score of −1.00 under a name like "Moral relativism vs. absolute
  // values" tells the reader the film is at one extreme and nothing whatever
  // about which extreme: the sign only means something to someone who knows how
  // the propositions were worded. The pole sentence is that knowledge.
  const stance = factor.score >= 0 ? factor.pole_high : factor.pole_low

  return (
    <li className={scored ? `film-factor ${side}` : 'film-factor absent'}>
      <button type="button" onClick={() => scored && setOpen(!open)} aria-expanded={open}
              disabled={!scored}>
        <span className="film-factor-name">{factor.name}</span>
        {scored ? (
          <>
            <span className="film-factor-scale">
              <em className={side === 'low' ? 'lit' : ''}>{factor.pole_low_label}</em>
              <Bar score={factor.score} />
              <em className={side === 'high' ? 'lit' : ''}>{factor.pole_high_label}</em>
            </span>
            <span className="film-factor-score">
              {factor.score >= 0 ? '+' : ''}{factor.score.toFixed(2)}
              <em>{factor.items} item{factor.items === 1 ? '' : 's'}</em>
            </span>
            {stance && (
              <span className={`film-factor-lean ${side}`}>
                <b>reads as</b> {stance}
              </span>
            )}
          </>
        ) : (
          <span className="film-factor-absent">did not raise this</span>
        )}
      </button>

      {open && (
        <div className="film-factor-why">
          <p className="film-factor-question">{factor.question}</p>

          {/* Both ends, with the film's own marked. Showing only the side it
              landed on reads as a verdict; showing both makes it a position —
              the reader can see what the other answer would have been. */}
          <div className="film-factor-poles">
            <p className={side === 'low' ? 'pole low here' : 'pole low'}>
              <b>{factor.pole_low_label}</b> {factor.pole_low}
            </p>
            <p className={side === 'high' ? 'pole high here' : 'pole high'}>
              <b>{factor.pole_high_label}</b> {factor.pole_high}
            </p>
          </div>

          {factor.items === 1 && (
            <p className="film-factor-thin">
              One proposition put it here, so the position is as extreme as a
              single answer can make it rather than a settled reading.
            </p>
          )}

          {!!factor.verdicts?.length && (
            <ul>
              {factor.verdicts.map((verdict) => (
                <li key={verdict.item_id} className={verdict.verdict}>
                  <b>{verdict.verdict === 'affirms' ? 'affirms' : 'denies'}</b>
                  <span>{verdict.text}</span>
                  {verdict.evidence && <em>{verdict.evidence}</em>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  )
}

export function FilmFactors({ scorer, filmId }) {
  const [state, setState] = React.useState({ status: 'loading' })

  React.useEffect(() => {
    if (!scorer || !filmId) return undefined
    let live = true
    setState({ status: 'loading' })
    fetch(`/api/factors/${encodeURIComponent(scorer)}/films/${encodeURIComponent(filmId)}`)
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then((data) => live && setState({ status: 'ready', data }))
      .catch(() => live && setState({ status: 'failed' }))
    return () => { live = false }
  }, [scorer, filmId])

  if (state.status === 'loading') return <p className="detail-muted">Reading its positions…</p>
  if (state.status === 'failed') {
    return <p className="detail-muted">No axis positions for this film yet.</p>
  }

  const factors = state.data.factors || []
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
          <p className="atlas-note">
            Tap an axis to read the propositions behind the position. {engaged.length} of{' '}
            {factors.length} axes were engaged — the rest this film never raised.
          </p>
        </>
      )}
    </div>
  )
}

export default FilmFactors
