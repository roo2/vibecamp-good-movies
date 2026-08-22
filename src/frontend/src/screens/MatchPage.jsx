import React from 'react'

export default function MatchPage({ onContinue }) {
  return <main className="app-page match-page"><section className="match-sheet">
    <div className="sheet-handle" />
    <p className="screen-label"><i /> <i /> You both said yes</p>
    <h1>Tonight’s<br /><em>shared pick.</em></h1>
    <div className="match-film"><div className="match-poster">Shared<br />match</div><div><h2>Arrival</h2><p>Says what you both lean toward: understanding another perspective can change what a life is worth.</p><p>It will still push on whether knowing the future makes a choice less free.</p></div></div>
    <div className="match-where"><span>Where to watch</span><p>Availability comes with the live shortlist service.</p></div>
    <button className="peach-button" type="button" onClick={onContinue}>Compare the other matches <span>→</span></button>
  </section></main>
}
