import React from 'react'
import { polePair } from './polePalette.js'

// One row: two pole labels, and a centred bar beneath them.
//
// Shared by the moral axes and the taste dimensions, because they are the same
// object — a position between two named ends — and were drawn by two different
// pieces of markup that had drifted apart in layout, in colour and in what the
// bar meant.
//
// LABELS ABOVE, TRACK BELOW, always. The earlier version put the labels either
// side of the bar in a three-column grid and switched to a stacked layout in
// narrow columns. Both existed, so both could be wrong, and in the film panel
// the long taste labels collided anyway: "Acclaimed craft" ran into "Slapdash
// spectacle". One layout that cannot collapse beats two that each work
// somewhere. The labels are a flex row that can only ever be two items pushed
// apart; the track is its own block at full width.
//
// COLOUR COMES FROM THE POLE, not from the axis and not from the side. See
// polePalette — the point is that Redemption is one colour everywhere it
// appears.

export default function AxisScale({ low, high, value, family = 'moral', index = 0 }) {
  // `value` is -1..1. Outside that is a caller bug rather than a film at an
  // extreme, so it is clamped instead of drawn past the end of its own track.
  const at = Math.max(-1, Math.min(1, value ?? 0))
  const side = at >= 0 ? 'high' : 'low'
  const pair = polePair(family, index)
  return (
    <span className={`axis-scale ${family} ${side}`}
          style={{ '--low': pair.low, '--high': pair.high }}>
      <span className="axis-scale-poles">
        <em className={side === 'low' ? 'lit' : ''}>{low}</em>
        <em className={side === 'high' ? 'lit' : ''}>{high}</em>
      </span>
      <span className="axis-scale-track">
        <u className="axis-scale-mid" />
        <i
          className={`axis-scale-bar ${side}`}
          style={at >= 0
            ? { insetInlineStart: '50%', inlineSize: `${Math.abs(at) * 50}%` }
            : { insetInlineEnd: '50%', inlineSize: `${Math.abs(at) * 50}%` }}
        />
      </span>
    </span>
  )
}
