import React from 'react'

export const FLOW_STEP_COUNT = 12

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
