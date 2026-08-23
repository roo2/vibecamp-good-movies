import React from 'react'

// One step per named film, plus the wait and the compass at the end. The server
// decides how many films a deck holds — DIRECT_CARDS in film_service.py, and
// fewer on a small corpus — so the film screen passes its own total and this is
// only the fallback for the two screens that cannot know it.
export const SEEN_IT_CARDS = 20
export const FLOW_STEP_COUNT = SEEN_IT_CARDS + 2
export const WAITING_STEP = SEEN_IT_CARDS + 1
export const COMPASS_STEP = FLOW_STEP_COUNT

export default function FlowProgress({ current, total = FLOW_STEP_COUNT, onBack, backLabel = 'Previous step' }) {
  return (
    <header className="flow-progress">
      <button className="back-button" type="button" aria-label={backLabel} disabled={!onBack} onClick={onBack}>←</button>
      <div className="segment-progress" aria-label={`Step ${current} of ${total}`}>
        {Array.from({ length: total }, (_, index) => <i className={index < current ? 'active' : ''} key={index} />)}
      </div>
      <span>{current} / {total}</span>
    </header>
  )
}
