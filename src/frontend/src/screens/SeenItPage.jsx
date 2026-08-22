import React, { useEffect, useState } from 'react'
import { loadOnboardingFilm } from '../services/movieService.js'

const reactions = [
  { id: 'not_for_me', label: 'Not for me', icon: '×' },
  { id: 'havent_seen', label: "Haven't seen it", icon: '−' },
  { id: 'loved_it', label: 'Loved it', icon: '♥' },
]

function formatRuntime(minutes) {
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

function SeenItPage({ onSubmit }) {
  const [film, setFilm] = useState(null)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    let active = true
    loadOnboardingFilm().then((item) => active && setFilm(item)).catch(() => active && setError('That film could not be loaded. Please try again.'))
    return () => { active = false }
  }, [])

  async function choose(reaction) {
    if (!film || selected) return
    setSelected(reaction)
    try {
      await onSubmit(film.id, reaction)
    } catch (submissionError) {
      setSelected(null)
      setError(submissionError.message)
    }
  }

  if (error) return <main className="app-page"><p className="message">{error}</p></main>
  if (!film) return <main className="app-page"><p className="message">Finding a film you might know…</p></main>

  return (
    <main className="app-page">
      <section className="phone-screen seen-it-screen">
        <header className="seen-it-header">
          <button className="back-button" type="button" aria-label="Back" disabled>←</button>
          <div className="segment-progress" aria-label="Step 4 of 12"><i className="active" /><i /><i /></div>
          <span>4 / 12</span>
        </header>
        <div className="seen-it-heading"><p className="screen-label">Step one · Gut reaction</p><h1>Seen it? Did you like it?</h1></div>
        <div className="seen-it-content">
          <article className={`movie-card ${film.poster_tone}`}>
            <span>Poster placeholder</span>
            <div><h2>{film.title}</h2><p>{film.year} · {film.genre} · {formatRuntime(film.runtime_min)}</p></div>
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
