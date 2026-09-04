import React, { useCallback, useEffect, useRef, useState } from 'react'
import useSwipeDecision from '../hooks/useSwipeDecision.js'
import FilmAxisStrip from '../components/FilmAxisStrip.jsx'
import { loadNextShortlistFilm, loadShortlistSelection, saveShortlistReaction } from '../services/shortlistService.js'

// Swiping must never wait on the network.
//
// It used to: a swipe posted the vote, waited for it, asked for the next film,
// waited for that too, and only then drew a card — so the exit animation ended
// in a frozen screen and the whole thing felt slow to use even though nothing
// was wrong. The server now hands over a queue, so a card can leave and the next
// one arrive in the same frame, with the vote sent behind it.
//
// The cost of being optimistic is that a failed vote is discovered after the
// card is gone. That is the right trade here — the vote is one row, retried on
// the next fetch because an unvoted film simply comes back round — and a
// dropped one is worth less than making every swipe feel like a form submission.

const REFILL_AT = 2

export default function ShortlistPage({ access, shareToken, matchesSeen = 0, solo = false, onDone }) {
  const [queue, setQueue] = useState([])
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)
  const [matches, setMatches] = useState(matchesSeen)
  const voted = useRef(new Set())
  const fetching = useRef(false)

  const finish = useCallback((films) => {
    if (films.length > matchesSeen) onDone(films)
  }, [matchesSeen, onDone])

  const refill = useCallback(async () => {
    if (fetching.current) return
    fetching.current = true
    try {
      const result = await loadNextShortlistFilm(access, shareToken, matchesSeen)
      if (result.state === 'shortlist') { finish(result.films); return }
      if (result.state === 'exhausted') { setState('exhausted'); return }
      // Anything already swiped locally is dropped: the server has not heard
      // about those votes yet and would otherwise deal the same card twice.
      setQueue((current) => {
        const have = new Set(current.map((film) => film.id))
        const fresh = (result.queue || [result.film])
          .filter((film) => !have.has(film.id) && !voted.current.has(film.id))
        return [...current, ...fresh]
      })
      setState('ready')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      fetching.current = false
    }
  }, [access, shareToken, finish, matchesSeen])

  useEffect(() => { refill() }, [refill])

  // The other person is swiping too, so the shortlist can fill without you.
  useEffect(() => {
    const poll = window.setInterval(() => {
      loadShortlistSelection(access, shareToken)
        .then((selection) => {
          if (selection.state === 'shortlist') {
            setMatches(selection.films.length)
            finish(selection.films)
          } else if (typeof selection.matches === 'number') setMatches(selection.matches)
        })
        .catch(() => {})
    }, 3000)
    return () => window.clearInterval(poll)
  }, [access, shareToken, finish])

  const film = queue[0]

  function vote(reaction) {
    if (!film) return
    const decided = film
    voted.current.add(decided.id)
    setQueue((current) => current.slice(1))     // the card is gone this frame

    saveShortlistReaction(access, shareToken, decided.id, reaction)
      .then((result) => {
        if (result?.state === 'shortlist') finish(result.films)
        else if (typeof result?.matches === 'number') setMatches(result.matches)
      })
      .catch((voteError) => setError(voteError.message))
  }

  const swipe = useSwipeDecision({ disabled: !film, onLeft: () => vote('no'), onRight: () => vote('yes') })

  useEffect(() => {
    if (state === 'ready' && queue.length <= REFILL_AT) refill()
  }, [state, queue.length, refill])

  if (error && !film) return <main className="app-page"><p className="message">{error}</p></main>
  if (state === 'exhausted' && !film) {
    return <main className="app-page"><p className="message">{solo ? 'You have been through every film we can offer you.' : 'You have been through every film we can offer you both.'}</p></main>
  }
  if (!film) return <main className="app-page"><p className="message">{solo ? 'Finding films for you…' : 'Finding films for the two of you…'}</p></main>

  // Past the target the count is no longer a countdown: they came back through
  // "keep looking", and "0 to go" would read as a finished job they are somehow
  // still doing.
  const WANTED = 3
  const progress = matches === 0
    ? (solo ? 'Say yes to shortlist it' : 'Both say yes to shortlist it')
    : matches < WANTED
      ? `${matches} shortlisted · ${WANTED - matches} to go`
      : `${matches} shortlisted · looking for more`
  return <main className="app-page"><section className="phone-screen deck-screen">
    <header className="deck-header">
      <span>{solo ? 'Picked for you' : 'Films for the two of you'}</span>
      <span>{progress}</span>
    </header>
    <article className="deck-card swipe-card" key={film.id} {...swipe.handlers} style={swipe.style}>
      <span className="swipe-cue swipe-cue-left" aria-hidden="true" style={{ opacity: swipe.direction === 'left' ? swipe.strength : 0 }}>× No</span>
      <span className="swipe-cue swipe-cue-right" aria-hidden="true" style={{ opacity: swipe.direction === 'right' ? swipe.strength : 0 }}>♥ Yes</span>
      <div className="deck-art" style={film.artwork_url ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.8), transparent), url(${film.artwork_url})` } : {}}><h2>{film.title}</h2></div>
      <div className="deck-copy">
        <span>{film.year}</span>
        {film.description && <p>{film.description}</p>}
        {/* Inside the card, not under it. The card stretches to fill the screen
            and only fifty of six hundred and seventy-six films have a written
            description, so for almost every film this was blank space above a
            strip that had nowhere to go. */}
        {/* Fixed height on this card: no expansion, and two taste rows rather
            than three. Everything has to fit above the buttons without the
            card scrolling, because a scroll container here competes with the
            swipe. The full, expandable reading is on the film page. */}
        <FilmAxisStrip filmId={film.id} expandable={false} tasteLimit={2} />
        <small>{film.note || (solo ? 'Picked for you' : 'Picked for both of you')}</small>
      </div>
    </article>
    <div className="deck-actions"><button type="button" disabled={swipe.committed} onClick={() => vote('no')}>×<span>No</span></button><button className="deck-heart" type="button" disabled={swipe.committed} onClick={() => vote('yes')}>♥<span>Yes</span></button></div>
    <p className="deck-note">Swipe right for yes · left for no. {solo ? 'Three yeses and you have your shortlist.' : 'When you both say yes, it joins your shortlist.'}</p>
  </section></main>
}
