import React, { useEffect, useState } from 'react'
import FilmAxisStrip from '../components/FilmAxisStrip.jsx'
import { loadShortlistSelection } from '../services/shortlistService.js'

// The three films you both said yes to.
//
// It used to be one, announced the moment it appeared, which decided the evening
// for a couple who were enjoying deciding it. Three is enough to choose between
// and few enough that choosing is not a second argument — and the choosing is
// deliberately left to them: nothing here picks a winner.
export default function MatchPage({ access, shareToken, films: initial, solo = false, onKeepLooking, onStartOver }) {
  const [films, setFilms] = useState(initial || [])
  const [openId, setOpenId] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!access || !shareToken) return undefined
    let active = true
    loadShortlistSelection(access, shareToken)
      .then((result) => {
        if (!active) return
        if (result.state === 'shortlist') setFilms(result.films)
      })
      .catch((requestError) => active && setError(requestError.message))
    return () => { active = false }
  }, [access, shareToken])

  if (!films.length) return <main className="app-page"><p className="message">Gathering your shortlist…</p></main>

  return <main className="app-page match-page"><section className="match-sheet">
    <div className="sheet-handle" />
    <p className="screen-label"><i /> <i /> {solo ? 'Your yeses' : 'You both said yes'}</p>
    <h1>Your <em>shortlist.</em></h1>
    <p className="match-lede">
      {solo
        ? `${films.length} ${films.length === 1 ? 'film' : 'films'} that argue for what your taste says you believe. Pick whichever you fancy tonight.`
        : `${films.length} ${films.length === 1 ? 'film' : 'films'} you each said yes to, without seeing what the other one picked. Pick whichever you fancy tonight.`}
    </p>
    {error && <p className="message" role="alert">{error}</p>}

    <ul className="match-list">
      {films.map((film) => (
        <li key={film.id} className={openId === film.id ? 'match-item open' : 'match-item'}>
          <button type="button" onClick={() => setOpenId(openId === film.id ? null : film.id)}
                  aria-expanded={openId === film.id}>
            <span className="match-art" style={film.artwork_url
              ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.55), transparent), url(${film.artwork_url})` }
              : {}} aria-hidden="true" />
            <span className="match-title">
              <b>{film.title}</b>
              <em>{film.year}</em>
              {film.note && <small>{film.note}</small>}
            </span>
          </button>
          {openId === film.id && (
            <div className="match-detail">
              {film.description && <p>{film.description}</p>}
              <FilmAxisStrip filmId={film.id} />
              <a className="peach-button" href={`https://www.justwatch.com/au/search?q=${encodeURIComponent(film.title)}`}
                 target="_blank" rel="noreferrer">See where to watch <span aria-hidden="true">↗</span></a>
            </div>
          )}
        </li>
      ))}
    </ul>

    <div className="match-actions">
      <button className="match-secondary-button" type="button" onClick={onKeepLooking}>Keep looking</button>
      <button className="match-text-button" type="button" onClick={onStartOver}>Start over</button>
    </div>
  </section></main>
}
