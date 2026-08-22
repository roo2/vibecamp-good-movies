import React, { useState } from 'react'

// The API scores each axis from -1 (pole_low) to +1 (pole_high); the track runs
// left to right over that range, so the centre of the track is "uncommitted".
const trackPosition = (score) => ((score + 1) / 2) * 100

// `confidence` is the share of full weight the shrinkage prior has let go of, so
// what is left of it is honest uncertainty — drawn as a band around the marker
// rather than hidden behind a point that looks more exact than it is.
const spreadFor = (confidence) => (1 - confidence) * 50

function strengthOf(axis) {
  if (!axis.evidence_items) return 'not read yet'
  if (axis.leaning === 'balanced') return 'balanced'
  return Math.abs(axis.score) >= 0.35 ? 'committed' : 'leaning'
}

function MoralAxis({ axis, expanded, onToggle }) {
  const centre = trackPosition(axis.score)
  const spread = spreadFor(axis.confidence)
  const bandLeft = Math.max(0, centre - spread)
  const bandRight = Math.min(100, centre + spread)
  const unread = !axis.evidence_items

  return (
    <li className={`moral-axis ${unread ? 'unread' : axis.leaning}`}>
      <button type="button" className="moral-axis-head" onClick={onToggle} aria-expanded={expanded}>
        <span className="moral-axis-name">{axis.name}</span>
        <span className="moral-axis-strength">{strengthOf(axis)}</span>
      </button>

      <div className="moral-axis-track" role="img"
           aria-label={`${axis.name}: ${axis.score >= 0 ? axis.pole_high : axis.pole_low}`}>
        <i className="moral-axis-mid" />
        <u className="moral-axis-band" style={{ left: `${bandLeft}%`, width: `${bandRight - bandLeft}%` }} />
        {!unread && <b className="moral-axis-marker" style={{ left: `${centre}%` }} />}
      </div>

      {expanded && (
        <div className="moral-axis-detail">
          <p className="moral-axis-question">{axis.question}</p>
          {unread ? (
            <p className="moral-axis-empty">
              None of the films you reacted to argue about this one, so we have not read you on it.
            </p>
          ) : (
            <>
              <p className={axis.leaning === 'low' ? 'moral-axis-pole lit' : 'moral-axis-pole'}>
                {axis.pole_low}
              </p>
              <p className={axis.leaning === 'high' ? 'moral-axis-pole lit' : 'moral-axis-pole'}>
                {axis.pole_high}
              </p>
              <p className="moral-axis-evidence">
                {axis.score >= 0 ? '+' : ''}{axis.score.toFixed(2)} · read from {Math.round(axis.evidence_items)} propositions
                across {axis.films} {axis.films === 1 ? 'film' : 'films'}
              </p>
            </>
          )}
        </div>
      )}
    </li>
  )
}

function MoralAxes({ scores }) {
  // The axis they committed to hardest opens first, so the screen says something
  // before anyone taps anything.
  const strongest = scores.reduce(
    (best, axis) => (Math.abs(axis.score) > Math.abs(best.score) ? axis : best), scores[0])
  const [openId, setOpenId] = useState(strongest ? strongest.dim_id : null)

  return (
    <ul className="moral-axes">
      {scores.map((axis) => (
        <MoralAxis
          key={axis.dim_id}
          axis={axis}
          expanded={openId === axis.dim_id}
          onToggle={() => setOpenId(openId === axis.dim_id ? null : axis.dim_id)}
        />
      ))}
    </ul>
  )
}

export default MoralAxes
