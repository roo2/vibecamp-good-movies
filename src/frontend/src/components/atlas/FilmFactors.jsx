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

  return (
    <li className={scored ? 'film-factor' : 'film-factor absent'}>
      <button type="button" onClick={() => scored && setOpen(!open)} aria-expanded={open}
              disabled={!scored}>
        <span className="film-factor-name">{factor.name}</span>
        {scored ? (
          <>
            <Bar score={factor.score} />
            <span className="film-factor-score">
              {factor.score >= 0 ? '+' : ''}{factor.score.toFixed(2)}
              <em>{factor.items} items</em>
            </span>
          </>
        ) : (
          <span className="film-factor-absent">did not raise this</span>
        )}
      </button>

      {open && !!factor.verdicts?.length && (
        <div className="film-factor-why">
          <p className="film-factor-question">{factor.question}</p>
          <ul>
            {factor.verdicts.map((verdict) => (
              <li key={verdict.item_id} className={verdict.verdict}>
                <b>{verdict.verdict === 'affirms' ? 'affirms' : 'denies'}</b>
                <span>{verdict.text}</span>
                {verdict.evidence && <em>{verdict.evidence}</em>}
              </li>
            ))}
          </ul>
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
