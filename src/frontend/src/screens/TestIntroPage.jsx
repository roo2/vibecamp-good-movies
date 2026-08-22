import React from 'react'
import { formatTime } from '../components/Countdown.jsx'

function TestIntroPage({ durationSeconds, onContinue }) {
  return (
    <main className="app-page">
      <section className="phone-screen welcome-screen">
        <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Moral Atlas</span></div>
        <div className="welcome-content">
          <h1>Every film is<br />arguing for<br /><em>something.</em></h1>
          <p className="screen-copy">Not genres. Not moods. We work out what you believe a good story should say — then find the film you’ll both agree with.</p>
          <div className="mini-map">
            <div className="mini-axis"><div><span>The old order was right</span><span>…was the problem</span></div><i><b className="you-dot" /><b className="them-dot" /></i></div>
            <div className="mini-axis"><div><span>They should pay</span><span>The harm should be repaired</span></div><i><u /><b className="you-dot wide" /><b className="them-dot wide" /></i></div>
            <p>Small gaps are shared ground. Wide ones are the story arguments worth having afterwards.</p>
          </div>
        </div>
        <button className="peach-button" type="button" onClick={onContinue}>Start — about {formatTime(durationSeconds)} <span aria-hidden="true">→</span></button>
      </section>
    </main>
  )
}

export default TestIntroPage
