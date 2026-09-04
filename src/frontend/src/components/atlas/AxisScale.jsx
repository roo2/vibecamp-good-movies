import React from 'react'

// One row: two pole labels either side of a centred bar.
//
// Shared, because the moral axes and the taste dimensions are the same object —
// a position between two named ends — and were being drawn by two different
// pieces of markup. The moral rows put the labels beside a centred bar; the
// taste rows had drifted into a three-column grid with a marker, a percentile
// and a trailing sentence, which read as a different instrument measuring a
// different kind of thing. It is not.
//
// COLOUR MEANS DIRECTION, in both. Not which axis — which END the film sits at.
// That was the other half of the divergence: the moral rows coloured by
// direction and the taste rows by dimension, so the same hue meant "redemption"
// in one place and "the third taste dimension" in another. Each family supplies
// its own pair through --high and --low, and no hue is shared between them.
//
// The bar is centred because the axis has two directions; a left-anchored bar
// would read as "how much of this quality the film has", which is not what a
// score of -0.6 means. It means the film denied most of what this axis asks.

export default function AxisScale({ low, high, value, family = 'moral', compact = false }) {
  // `value` is -1..1. Anything outside is a caller bug rather than a film at an
  // extreme, so it is clamped instead of drawn past the end of its own track.
  const at = Math.max(-1, Math.min(1, value ?? 0))
  const side = at >= 0 ? 'high' : 'low'
  const magnitude = Math.abs(at) * 50
  return (
    <span className={`axis-scale ${family} ${side}${compact ? ' compact' : ''}`}>
      <em className={side === 'low' ? 'lit' : ''}>{low}</em>
      <span className="axis-scale-track">
        <u className="axis-scale-mid" />
        <i
          className={`axis-scale-bar ${side}`}
          style={at >= 0
            ? { insetInlineStart: '50%', inlineSize: `${magnitude}%` }
            : { insetInlineEnd: '50%', inlineSize: `${magnitude}%` }}
        />
      </span>
      <em className={side === 'high' ? 'lit' : ''}>{high}</em>
    </span>
  )
}
