import React, { useEffect, useState } from 'react'
import FlowProgress from '../components/FlowProgress.jsx'
import useSwipeDecision from '../hooks/useSwipeDecision.js'
import { loadMoreOnboardingFilms, loadOnboardingFilms } from '../services/movieService.js'

const reactions = [
  { id: 'not_for_me', label: 'Not for me', icon: '×' },
  { id: 'loved_it', label: 'Loved it', icon: '♥' },
  { id: 'havent_seen', label: "Haven't seen it", icon: '−' },
]

function formatRuntime(minutes) {
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

// Enough films someone has actually seen for the instrument to say anything.
// Below this a compass is a shape drawn through almost no points.
const ENOUGH_TO_READ = 6
// And a limit on rescuing: two top-ups, then we stop asking. Somebody who has
// seen almost nothing on offer should be told so, not dealt cards forever.
const MAX_TOP_UPS = 2

function SeenItPage({ access, shareToken, onSubmit, onComplete }) {
  const [films, setFilms] = useState([])
  const [filmIndex, setFilmIndex] = useState(0)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [seen, setSeen] = useState(0)          // films they actually had a view on
  const [topUps, setTopUps] = useState(0)

  useEffect(() => {
    let active = true
    loadOnboardingFilms(access, shareToken).then((items) => active && setFilms(items)).catch(() => active && setError('Those films could not be loaded. Please try again.'))
    return () => { active = false }
  }, [access, shareToken])

  async function choose(reaction) {
    if (!film || selected) return
    const isLastFilm = filmIndex === films.length - 1
    const answered = seen + (reaction === 'havent_seen' ? 0 : 1)
    setSelected(reaction)
    setSeen(answered)
    if (!isLastFilm) {
      setFilmIndex((index) => index + 1)
      setSelected(null)
    }
    try {
      await onSubmit(film.id, reaction, shareToken)
      if (!isLastFilm) return

      // The end of the deck is not the end of the quiz if they have not said
      // enough to be read. "Haven't seen it" is honest and carries no moral
      // information, so somebody can answer every card and still be a blank.
      if (answered < ENOUGH_TO_READ && topUps < MAX_TOP_UPS) {
        try {
          const more = await loadMoreOnboardingFilms(access, shareToken)
          if (more?.length) {
            setFilms((current) => [...current, ...more])
            setFilmIndex((index) => index + 1)
            setSelected(null)
            setTopUps((n) => n + 1)
            return
          }
        } catch {
          // Nothing left to deal — finish on what we have rather than trap them.
        }
      }
      onComplete()
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
        <FlowProgress current={filmIndex + 1} total={films.length} />
        <div className="seen-it-heading"><p className="screen-label">Your half · {films.length} films</p><h1>Seen it? Did you like it?</h1></div>
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
        <aside className="seen-it-note"><span aria-hidden="true">ⓘ</span><p>{topUps > 0
          ? 'A few more — we need a handful you have actually seen before we can read you. Your date never sees these.'
          : 'Swipe right if you liked it · left if it wasn’t for you. Your date never sees these.'}</p></aside>
      </section>
    </main>
  )
}

export default SeenItPage
