import FilmAxisStrip from '../components/FilmAxisStrip.jsx'
import React, { useEffect, useState } from 'react'
import { loadShortlistSelection, reopenShortlist } from '../services/shortlistService.js'

export default function MatchPage({ access, shareToken, film, onKeepLooking, onStartOver }) {
  const [selectedFilm, setSelectedFilm] = useState(film)
  const [error, setError] = useState(null)
  const [reopening, setReopening] = useState(false)

  useEffect(() => {
    if (!access || !shareToken) return undefined
    let active = true
    function refreshSelection() {
      loadShortlistSelection(access, shareToken).then((result) => {
        if (!active) return
        setError(null)
        if (result.state === 'selected') setSelectedFilm((current) => current?.id === result.film.id ? current : result.film)
        else if (selectedFilm) onKeepLooking()
      }).catch((requestError) => active && setError(requestError.message))
    }
    refreshSelection()
    const poll = window.setInterval(refreshSelection, 1500)
    return () => {
      active = false
      window.clearInterval(poll)
    }
  }, [access, onKeepLooking, selectedFilm, shareToken])

  async function handleSomethingElse() {
    if (reopening) return
    setReopening(true)
    setError(null)
    try {
      await reopenShortlist(access, shareToken)
      onKeepLooking()
    } catch (requestError) {
      setError(requestError.message)
      setReopening(false)
    }
  }

  if (!selectedFilm) return <main className="app-page"><p className="message">Loading tonight’s film…</p></main>
  const watchUrl = `https://www.justwatch.com/au/search?q=${encodeURIComponent(selectedFilm.title)}`
  return <main className="app-page match-page"><section className="match-sheet">
    <div className="sheet-handle" />
    <p className="screen-label"><i /> <i /> You both said yes</p>
    <h1>Tonight’s<br /><em>shared pick.</em></h1>
    <div className="match-film"><div className="match-poster">Shared<br />match</div><div><h2>{selectedFilm.title}</h2>{selectedFilm.description && <p>{selectedFilm.description}</p>}<p>You all chose it independently.</p></div></div>
    <FilmAxisStrip filmId={selectedFilm.id} />
    {error && <p className="message" role="alert">{error}</p>}
    <div className="match-actions">
      <a className="peach-button" href={watchUrl} target="_blank" rel="noreferrer">See where to watch <span aria-hidden="true">↗</span></a>
      <button className="match-secondary-button" type="button" disabled={reopening} onClick={handleSomethingElse}>Something else</button>
      <button className="match-text-button" type="button" onClick={onStartOver}>Start over</button>
    </div>
  </section></main>
}
