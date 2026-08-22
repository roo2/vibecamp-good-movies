import React, { useState } from 'react'

export default function TiebreakPage({ onDone }) {
  const [picked, setPicked] = useState(null)
  function pick(title) { setPicked(title); window.setTimeout(onDone, 260) }
  return <main className="app-page"><section className="phone-screen tiebreak-screen">
    <header className="deck-header"><span>Round 1 of 2</span><span>━ ─</span></header>
    <h1>Three you both want.<br />One evening.</h1><p className="screen-copy">Straight knockout. No discussion, no negotiating.</p>
    <div className="tiebreak-cards"><button className={picked === 'Arrival' ? 'picked' : ''} onClick={() => pick('Arrival')}><strong>Arrival</strong><span>A visitor learns that understanding another perspective can change what a life is worth.</span></button><button className={picked === 'Spirited Away' ? 'picked' : ''} onClick={() => pick('Spirited Away')}><strong>Spirited Away</strong><span>A child holds onto compassion and identity inside rules she does not understand.</span></button></div>
    <div className="or-divider"><i />or<i /></div><button className="coin-button" onClick={onDone}>Neither of us decides — flip for it</button>
  </section></main>
}
