import React, { useEffect, useState } from 'react'
import { loadShortlistSelection } from '../services/shortlistService.js'

export default function MatchPage({ access, shareToken, film, onContinue }) {
  const [selectedFilm, setSelectedFilm] = useState(film)

  useEffect(() => {
    if (selectedFilm || !access || !shareToken) return
    loadShortlistSelection(access, shareToken)
      .then((result) => {
        if (result.state === 'selected') setSelectedFilm(result.film)
      })
      .catch(console.error)
  }, [access, selectedFilm, shareToken])

  if (!selectedFilm) return <main className="app-page"><p className="message">Loading tonight’s film…</p></main>
  return <main className="app-page match-page"><section className="match-sheet">
    <div className="sheet-handle" />
    <p className="screen-label"><i /> <i /> You both said yes</p>
    <h1>Tonight’s<br /><em>shared pick.</em></h1>
    <div className="match-film"><div className="match-poster">Shared<br />match</div><div><h2>{selectedFilm.title}</h2><p>{selectedFilm.description}</p><p>You all chose it independently.</p></div></div>
    <div className="match-where"><span>Where to watch</span><p>Availability comes with the live shortlist service.</p></div>
    <button className="peach-button" type="button" onClick={onContinue}>Start it <span>→</span></button>
  </section></main>
}
