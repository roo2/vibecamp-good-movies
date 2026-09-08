import React, { useEffect, useState } from 'react'
import FlowProgress from '../components/FlowProgress.jsx'
import useSwipeDecision from '../hooks/useSwipeDecision.js'
import { loadMoreOnboardingFilms, loadOnboardingFilms } from '../services/movieService.js'

// Two degrees each way, and no middle.
//
// The deck used to offer disliked / shrugged / loved, which made one button do
// two jobs — "I liked this" and "this is one of my favourites" are not the same
// answer — and put a shrug where the scale's midpoint should be. A shrug is a
// weak answer dressed as a neutral one, and it was the button people reached
// for when they meant "it was fine, I suppose", which is a mild yes as often as
// a mild no.
//
// So: hate, dislike, like, love. The two ends are bigger, because they are the
// answers that carry the most about somebody and should be the easiest to hit;
// the middle two are the same shape, smaller. Not having seen a film is not a
// point on this scale at all, so it stays underneath with room of its own.
//
// The emoji IS the label. A face is read faster than a word at arm's length,
// and these four faces are unambiguous in a way "It was fine" never was — but
// every button still carries its words for a screen reader, and the word
// appears under the emoji while an answer is saving.
const reactions = [
  { id: 'hated_it', label: 'Hated it', emoji: '😡', size: 'strong' },
  { id: 'not_for_me', label: 'Not for me', emoji: '🙁', size: 'mild' },
  { id: 'liked_it', label: 'Liked it', emoji: '🙂', size: 'mild' },
  { id: 'loved_it', label: 'Loved it', emoji: '😍', size: 'strong' },
]
const SKIP = { id: 'havent_seen', label: "Haven't seen it", icon: '−' }

function formatRuntime(minutes) {
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

// Enough films someone has actually seen for the instrument to say anything.
// Below this a compass is a shape drawn through almost no points.
const ENOUGH_TO_READ = 6
// And a limit on rescuing: two top-ups, then we stop asking. Somebody who has
// seen almost nothing on offer should be told so, not dealt cards forever.
const MAX_TOP_UPS = 2

function SeenItPage({ access, shareToken, onSubmit, onComplete, onAbandon }) {
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
  // A swipe records the MILD negative and the emphatic positive, which is
  // deliberate rather than an oversight: the gesture is the fast path, and the
  // cost of a mis-swipe should be small on the side that pushes a profile away
  // from a film. Saying you hated something is a claim worth a deliberate tap.
  const swipeLeft = reactions[1]
  const swipeRight = reactions[3]
  const swipe = useSwipeDecision({
    disabled: Boolean(selected),
    onLeft: () => choose(swipeLeft.id),
    onRight: () => choose(swipeRight.id),
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
            {/* The cue shows the face the swipe will actually press, so the
                gesture and the buttons under it cannot say different things. */}
            <span className="swipe-cue swipe-cue-left" aria-hidden="true" style={{ opacity: swipe.direction === 'left' ? swipe.strength : 0 }}>{swipeLeft.emoji} {swipeLeft.label}</span>
            <span className="swipe-cue swipe-cue-right" aria-hidden="true" style={{ opacity: swipe.direction === 'right' ? swipe.strength : 0 }}>{swipeRight.emoji} {swipeRight.label}</span>
            <div><h2>{film.title}</h2><p>{film.year || '—'} · {film.genre} · {film.runtime_min ? formatRuntime(film.runtime_min) : 'Runtime unavailable'}</p></div>
          </article>
          <div className="movie-reactions" aria-label={`Your reaction to ${film.title}`}>
            {reactions.map((reaction) => (
              <button
                className={`movie-reaction ${reaction.size} ${selected === reaction.id ? 'selected' : ''}`}
                key={reaction.id}
                type="button"
                aria-label={reaction.label}
                title={reaction.label}
                onClick={() => choose(reaction.id)}
                disabled={Boolean(selected) || swipe.committed}>
                <strong aria-hidden="true">{reaction.emoji}</strong>
                {selected === reaction.id && <span>Saving…</span>}
              </button>
            ))}
            <button className={`movie-reaction unseen ${selected === SKIP.id ? 'selected' : ''}`} type="button" onClick={() => choose(SKIP.id)} disabled={Boolean(selected) || swipe.committed}>
              <strong aria-hidden="true">{SKIP.icon}</strong><span>{selected === SKIP.id ? 'Saving…' : SKIP.label}</span>
            </button>
          </div>
        </div>
        {/* Deliberately the quietest thing on the screen. It is an escape
            hatch, not a step: twenty films is a long way in to find out you
            wanted the other mode or a different position, but nobody should be
            invited to abandon a quiz they are halfway through. */}
        {onAbandon && (
          <button type="button" className="quiet-exit" onClick={onAbandon}>Start over</button>
        )}
        <aside className="seen-it-note"><span aria-hidden="true">ⓘ</span><p>{topUps > 0
          ? 'A few more — we need a handful you have actually seen before we can read you. Your friend never sees these.'
          : 'Swipe right if you liked it · left if it wasn’t for you. Your friend never sees these.'}</p></aside>
      </section>
    </main>
  )
}

export default SeenItPage
