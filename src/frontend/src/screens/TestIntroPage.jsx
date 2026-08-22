import React from 'react'
import { formatTime } from '../components/Countdown.jsx'

function TestIntroPage({ durationSeconds, onContinue }) {
  return (
    <main className="flow-shell">
      <section className="flow-card intro-card">
        <p className="eyebrow">Moral Atlas</p>
        <p className="step-label">Before we begin</p>
        <h1>A quick read on what matters to you.</h1>
        <p className="flow-copy">You’ll see a handful of instinctive choices. There are no right answers — pick the response that feels closest to yours.</p>
        <div className="time-callout">
          <span>Time limit</span>
          <strong>{formatTime(durationSeconds)}</strong>
          <p>Answer quickly. Your first instinct is useful here.</p>
        </div>
        <button className="primary-button" type="button" onClick={onContinue}>Start the test <span aria-hidden="true">→</span></button>
      </section>
    </main>
  )
}

export default TestIntroPage
