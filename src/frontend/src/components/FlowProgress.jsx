import React from 'react'

// One step per named film, plus the wait and the compass at the end. Must match
// DIRECT_CARDS in film_service.py — the server decides how many films a deck
// holds, and a progress bar that disagrees with it counts to the wrong number.
export const SEEN_IT_CARDS = 12
export const FLOW_STEP_COUNT = SEEN_IT_CARDS + 2
export const WAITING_STEP = SEEN_IT_CARDS + 1
export const COMPASS_STEP = FLOW_STEP_COUNT

export default function FlowProgress({ current, onBack, backLabel = 'Previous step' }) {
  return (
    <header className="flow-progress">
      <button className="back-button" type="button" aria-label={backLabel} disabled={!onBack} onClick={onBack}>←</button>
      <div className="segment-progress" aria-label={`Step ${current} of ${FLOW_STEP_COUNT}`}>
        {Array.from({ length: FLOW_STEP_COUNT }, (_, index) => <i className={index < current ? 'active' : ''} key={index} />)}
      </div>
      <span>{current} / {FLOW_STEP_COUNT}</span>
    </header>
  )
}
