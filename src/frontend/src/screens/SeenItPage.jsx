import React, { useEffect, useState } from 'react'
import FlowProgress from '../components/FlowProgress.jsx'
import useSwipeDecision from '../hooks/useSwipeDecision.js'
import { loadOnboardingFilms } from '../services/movieService.js'
import { preloadTestQuestions } from '../services/testService.js'

const reactions = [
  { id: 'not_for_me', label: 'Not for me', icon: '×' },
  { id: 'loved_it', label: 'Loved it', icon: '♥' },
  { id: 'havent_seen', label: "Haven't seen it", icon: '−' },
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
    preloadTestQuestions(access, shareToken)
    return () => { active = false }
  }, [access, shareToken])

  async function choose(reaction) {
    if (!film || selected) return
    const isLastFilm = filmIndex === films.length - 1
    setSelected(reaction)
    if (!isLastFilm) {
      setFilmIndex((index) => index + 1)
      setSelected(null)
    }
    try {
      await onSubmit(film.id, reaction, shareToken)
      if (isLastFilm) onComplete()
    } catch (submissionError) {
      setSelected(null)
      setError(submissionError.message)
    }
  }

  const film = films[filmIndex]
  const swipe = useSwipeDecision({
    disabled: Boolean(selected),
    onLeft: () => choose('not_for_me'),
    onRight: () => choose('loved_it'),
  })

  if (error) return <main className="app-page"><p className="message">{error}</p></main>
  if (!film) return <main className="app-page"><p className="message">Finding films you might know…</p></main>

  return (
    <main className="app-page seen-it-page">
      <section className="phone-screen seen-it-screen">
        <FlowProgress current={filmIndex + 1} />
        <div className="seen-it-heading"><p className="screen-label">Step one · Gut reaction</p><h1>Seen it? Did you like it?</h1></div>
        <div className="seen-it-content">
          <article className="movie-card swipe-card" {...swipe.handlers} style={{ ...(film.artwork_url ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.82), rgba(23,19,16,.08)), url(${film.artwork_url})` } : {}), ...swipe.style }}>
            <span className="swipe-cue swipe-cue-left" aria-hidden="true" style={{ opacity: swipe.direction === 'left' ? swipe.strength : 0 }}>× Not for me</span>
            <span className="swipe-cue swipe-cue-right" aria-hidden="true" style={{ opacity: swipe.direction === 'right' ? swipe.strength : 0 }}>♥ Loved it</span>
            <div><h2>{film.title}</h2><p>{film.year || '—'} · {film.genre} · {film.runtime_min ? formatRuntime(film.runtime_min) : 'Runtime unavailable'}</p></div>
          </article>
          <div className="movie-reactions" aria-label={`Your reaction to ${film.title}`}>
            {reactions.map((reaction) => (
              <button className={`movie-reaction ${reaction.id === 'loved_it' ? 'loved' : ''} ${reaction.id === 'havent_seen' ? 'unseen' : ''} ${selected === reaction.id ? 'selected' : ''}`} key={reaction.id} type="button" onClick={() => choose(reaction.id)} disabled={Boolean(selected) || swipe.committed}>
                <strong aria-hidden="true">{reaction.icon}</strong><span>{selected === reaction.id ? 'Saving…' : reaction.label}</span>
              </button>
            ))}
          </div>
        </div>
        <aside className="seen-it-note"><span aria-hidden="true">ⓘ</span><p>Swipe right to like · left to pass. You can always use the buttons.</p></aside>
      </section>
    </main>
  )
}

export default SeenItPage
