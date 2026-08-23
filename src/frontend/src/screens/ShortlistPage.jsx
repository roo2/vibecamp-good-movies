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

export default function ShortlistPage({ access, shareToken, matchesSeen = 0, onDone }) {
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
      const result = await loadNextShortlistFilm(access, shareToken)
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
  }, [access, shareToken, finish])

  useEffect(() => { refill() }, [refill])

  // The other person is swiping too, so the shortlist can fill without you.
  useEffect(() => {
    const poll = window.setInterval(() => {
      loadShortlistSelection(access, shareToken)
        .then((selection) => {
          if (selection.state === 'shortlist') finish(selection.films)
          else if (typeof selection.matches === 'number') setMatches(selection.matches)
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
    return <main className="app-page"><p className="message">You have been through every film we can offer you both.</p></main>
  }
  if (!film) return <main className="app-page"><p className="message">Finding films for the two of you…</p></main>

  const remaining = Math.max(0, 3 - matches)
  return <main className="app-page"><section className="phone-screen deck-screen">
    <header className="deck-header">
      <span>Films for the two of you</span>
      <span>{matches ? `${matches} agreed · ${remaining} to go` : 'Both say yes to shortlist it'}</span>
    </header>
    <article className="deck-card swipe-card" key={film.id} {...swipe.handlers} style={swipe.style}>
      <span className="swipe-cue swipe-cue-left" aria-hidden="true" style={{ opacity: swipe.direction === 'left' ? swipe.strength : 0 }}>× No</span>
      <span className="swipe-cue swipe-cue-right" aria-hidden="true" style={{ opacity: swipe.direction === 'right' ? swipe.strength : 0 }}>♥ Yes</span>
      <div className="deck-art" style={film.artwork_url ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.8), transparent), url(${film.artwork_url})` } : {}}><h2>{film.title}</h2></div>
      <div className="deck-copy"><span>{film.year}</span>{film.description && <p>{film.description}</p>}<small>{film.note || 'Picked for both of you'}</small></div>
    </article>
    <FilmAxisStrip filmId={film.id} />
    <div className="deck-actions"><button type="button" disabled={swipe.committed} onClick={() => vote('no')}>×<span>No</span></button><button className="deck-heart" type="button" disabled={swipe.committed} onClick={() => vote('yes')}>♥<span>Yes</span></button></div>
    <p className="deck-note">Swipe right for yes · left for no. When you both say yes, it joins your shortlist.</p>
  </section></main>
}
