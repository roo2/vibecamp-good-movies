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

// How far apart two readings on the same axis can be before the gap is worth
// naming. The axis runs -1..+1, so a full point is a quarter of its width and
// comfortably more than the noise in a dozen films.
const APART = 0.5

function MoralAxis({ axis, others, expanded, onToggle }) {
  const centre = trackPosition(axis.score)
  const spread = spreadFor(axis.confidence)
  const bandLeft = Math.max(0, centre - spread)
  const bandRight = Math.min(100, centre + spread)
  const unread = !axis.evidence_items
  // Only companions who were read on THIS axis. Someone can be read on the
  // corpus and still have engaged nothing that loads on one particular factor.
  const read = others.filter((other) => other.axis && other.axis.evidence_items)
  const split = read.filter((other) => Math.abs(other.axis.score - axis.score) >= APART)

  return (
    <li className={`moral-axis ${unread ? 'unread' : axis.leaning}`}>
      <button type="button" className="moral-axis-head" onClick={onToggle} aria-expanded={expanded}>
        <span className="moral-axis-name">{axis.name}</span>
        <span className="moral-axis-strength">
          {read.length && !unread
            ? (split.length ? 'you differ' : 'you agree')
            : strengthOf(axis)}
        </span>
      </button>

      {/* Both ends named, always, and named the same way whether or not this
          axis was read. A number on an unlabelled line is not a position — it
          is a number, and the reader has to guess which way is which. */}
      <div className="moral-axis-poles">
        <span className={axis.leaning === 'low' && !unread ? 'lit' : ''}>{axis.pole_low_label}</span>
        <span className={axis.leaning === 'high' && !unread ? 'lit' : ''}>{axis.pole_high_label}</span>
      </div>

      <div className="moral-axis-track" role="img"
           aria-label={[`${axis.name}: you, ${axis.score >= 0 ? axis.pole_high : axis.pole_low}`,
                        ...read.map((other) => `${other.name}, ${other.axis.score >= 0 ? axis.pole_high : axis.pole_low}`)].join('; ')}>
        <i className="moral-axis-mid" />
        <u className="moral-axis-band" style={{ left: `${bandLeft}%`, width: `${bandRight - bandLeft}%` }} />
        {/* Their marker sits under yours, hollow and dimmer, so the two never
            read as one person's uncertainty — and so yours stays the one the
            eye finds first on your own compass. */}
        {read.map((other) => (
          <b className="moral-axis-marker companion" key={other.user_id}
             style={{ left: `${trackPosition(other.axis.score)}%` }}
             title={`${other.name}: ${other.axis.score >= 0 ? '+' : ''}${other.axis.score.toFixed(2)}`} />
        ))}
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
                <b>{axis.pole_low_label}</b>
                {axis.pole_low}
              </p>
              <p className={axis.leaning === 'high' ? 'moral-axis-pole lit' : 'moral-axis-pole'}>
                <b>{axis.pole_high_label}</b>
                {axis.pole_high}
              </p>
              <p className="moral-axis-evidence">
                {axis.score >= 0 ? '+' : ''}{axis.score.toFixed(2)} · read from {Math.round(axis.evidence_items)} propositions
                across {axis.films} {axis.films === 1 ? 'film' : 'films'}
              </p>
              {read.map((other) => (
                <p className="moral-axis-evidence companion" key={other.user_id}>
                  <b>{other.name}</b> {other.axis.score >= 0 ? '+' : ''}{other.axis.score.toFixed(2)}
                  {' · '}
                  {Math.abs(other.axis.score - axis.score) >= APART
                    ? 'the other side of this one from you'
                    : 'close to where you landed'}
                </p>
              ))}
            </>
          )}
        </div>
      )}
    </li>
  )
}

function MoralAxes({ scores, companions = [] }) {
  const byId = companions.map((companion) => ({
    user_id: companion.user_id,
    // Nobody is asked for a name any more, so there is usually nothing to show
    // but the role — which is all the reader needed anyway.
    name: (companion.name || '').trim() || 'your partner',
    scores: new Map((companion.profile?.scores || []).map((axis) => [axis.dim_id, axis])),
  }))

  // Everything starts closed. Opening one axis for the reader made the list
  // arrive already half-unpacked, and an expanded panel reads as something the
  // reader did rather than something the screen chose — the first impression
  // should be the whole shape of the compass, not one axis of it.
  const [openId, setOpenId] = useState(null)

  return (
    <>
      {byId.length > 0 && (
        <p className="moral-axes-key">
          <b className="key-you" /> you
          {byId.map((companion) => (
            <React.Fragment key={companion.user_id}>
              <b className="key-companion" /> {companion.name}
            </React.Fragment>
          ))}
        </p>
      )}
      <ul className="moral-axes">
        {scores.map((axis) => (
          <MoralAxis
            key={axis.dim_id}
            axis={axis}
            others={byId.map((companion) => ({
              user_id: companion.user_id, name: companion.name,
              axis: companion.scores.get(axis.dim_id),
            }))}
            expanded={openId === axis.dim_id}
            onToggle={() => setOpenId(openId === axis.dim_id ? null : axis.dim_id)}
          />
        ))}
      </ul>
    </>
  )
}

export default MoralAxes
