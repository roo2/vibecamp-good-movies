import React, { useEffect, useState } from 'react'
import { loadOnboardingFilms } from '../services/movieService.js'

const reactions = [
  { id: 'not_for_me', label: 'Not for me', icon: '×' },
  { id: 'havent_seen', label: "Haven't seen it", icon: '−' },
  { id: 'loved_it', label: 'Loved it', icon: '♥' },
]

function formatRuntime(minutes) {
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

function SeenItPage({ access, shareToken, onSubmit, onComplete }) {
  const [films, setFilms] = useState([])
  const [filmIndex, setFilmIndex] = useState(0)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    let active = true
    loadOnboardingFilms(access, shareToken).then((items) => active && setFilms(items)).catch(() => active && setError('Those films could not be loaded. Please try again.'))
    return () => { active = false }
  }, [access, shareToken])

  async function choose(reaction) {
    if (!film || selected) return
    setSelected(reaction)
    try {
      await onSubmit(film.id, reaction, shareToken)
      if (filmIndex === films.length - 1) onComplete()
      else {
        setFilmIndex((index) => index + 1)
        setSelected(null)
      }
    } catch (submissionError) {
      setSelected(null)
      setError(submissionError.message)
    }
  }

  if (error) return <main className="app-page"><p className="message">{error}</p></main>
  if (films.length === 0) return <main className="app-page"><p className="message">Finding films you might know…</p></main>

  const film = films[filmIndex]

  return (
    <main className="app-page">
      <section className="phone-screen seen-it-screen">
        <header className="seen-it-header">
          <button className="back-button" type="button" aria-label="Back" disabled>←</button>
          <div className="segment-progress" aria-label={`Film ${filmIndex + 1} of ${films.length}`}>{films.map((item, index) => <i className={index <= filmIndex ? 'active' : ''} key={item.id} />)}</div>
          <span>{filmIndex + 1} / {films.length}</span>
        </header>
        <div className="seen-it-heading"><p className="screen-label">Step one · Gut reaction</p><h1>Seen it? Did you like it?</h1></div>
        <div className="seen-it-content">
          <article className="movie-card">
            <span>Poster placeholder</span>
            <div><h2>{film.title}</h2><p>{film.year || '—'} · {film.genre} · {film.runtime_min ? formatRuntime(film.runtime_min) : 'Runtime unavailable'}</p></div>
          </article>
          <div className="movie-reactions" aria-label={`Your reaction to ${film.title}`}>
            {reactions.map((reaction) => (
              <button className={`movie-reaction ${reaction.id === 'loved_it' ? 'loved' : ''} ${selected === reaction.id ? 'selected' : ''}`} key={reaction.id} type="button" onClick={() => choose(reaction.id)} disabled={Boolean(selected)}>
                <strong aria-hidden="true">{reaction.icon}</strong><span>{selected === reaction.id ? 'Saving…' : reaction.label}</span>
              </button>
            ))}
          </div>
        </div>
        <aside className="seen-it-note"><span aria-hidden="true">ⓘ</span><p>We’re not learning your genres. We’re reading what these stories <em>believe</em> — and what you believed along with them.</p></aside>
      </section>
    </main>
  )
}

export default SeenItPage
