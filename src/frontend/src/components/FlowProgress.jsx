import React from 'react'

// The bar counts films and only films. It used to add the wait and the compass,
// so it read "1 / 22" while promising twenty — and those two screens are not
// more of the same task, they are what happens afterwards. The film screen
// passes the size of the deck it was actually dealt.
export const SEEN_IT_CARDS = 20
export const FLOW_STEP_COUNT = SEEN_IT_CARDS

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
