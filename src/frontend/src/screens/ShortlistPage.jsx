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

// How long to wait before asking again when the server deals back only cards
// this person has already swiped. It backs off so a deck that is waiting on a
// slow connection is not hammering, and it never gives up: every reason for an
// empty hand here is temporary, and the alternative is the screen this fixed.
const RETRY_MS = [400, 900, 2000, 4000, 8000]

// Which of the dealt cards are actually new to this person.
//
// Exported and pure because the bug it exists to prevent is invisible in a
// render: the deck asks for more the moment two cards are left, the votes for
// the cards already gone are still in flight, and the server — which knows a
// film is spent only once its vote arrives — deals those same films straight
// back. Every one is dropped here, and a screen that treats an empty hand as an
// answer sits on "Finding films for you…" until the page is reloaded.
export function freshCards(dealt, queued, votedIds) {
  const have = new Set(queued.map((film) => film.id))
  return dealt.filter((film) => film && !have.has(film.id) && !votedIds.has(film.id))
}

// Whether a hand contains anything this person has not already judged. False is
// the state that used to end the deck: the server dealt, every card came back
// stale, and nothing asked again.
export function hasNewCards(dealt, votedIds) {
  return dealt.some((film) => film && !votedIds.has(film.id))
}

export default function ShortlistPage({ access, shareToken, matchesSeen = 0, solo = false, onDone, onSteer }) {
  const [queue, setQueue] = useState([])
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)
  const [matches, setMatches] = useState(matchesSeen)
  const voted = useRef(new Set())
  const fetching = useRef(false)
  // Votes the server has not acknowledged yet. A refill waits on these, because
  // asking for more cards while they are in the air is asking a question the
  // server cannot answer correctly.
  const pending = useRef(new Set())
  const retryAt = useRef(0)
  const retryTimer = useRef(null)

  useEffect(() => () => window.clearTimeout(retryTimer.current), [])

  const finish = useCallback((films) => {
    if (films.length > matchesSeen) onDone(films)
  }, [matchesSeen, onDone])

  const refill = useCallback(async () => {
    if (fetching.current) return
    fetching.current = true
    window.clearTimeout(retryTimer.current)
    try {
      // Let the votes land first. They were sent optimistically so the card
      // could leave in the same frame, which means the server can still be
      // holding films this person has already judged — and it would deal them
      // straight back, to be dropped below as stale.
      if (pending.current.size) await Promise.allSettled([...pending.current])

      const result = await loadNextShortlistFilm(access, shareToken, matchesSeen)
      if (result.state === 'shortlist') { finish(result.films); return }
      if (result.state === 'exhausted') { setState('exhausted'); return }

      const dealt = result.queue || [result.film]
      // Decided out here rather than inside the updater: React runs an updater
      // during the render it schedules, so anything the updater assigns is
      // still unset on the next line, and the retry below would fire every
      // time. `voted` is a ref, so this reads the same set the merge will.
      const anythingNew = hasNewCards(dealt, voted.current)
      setQueue((current) => [...current, ...freshCards(dealt, current, voted.current)])
      setState('ready')

      // An empty hand is not an answer. The server has cards — it just dealt
      // some — so this is a race with our own votes, and asking again is what
      // resolves it. Nothing else would: the refill effect watches the queue
      // length and the state, and neither of them changed.
      if (!anythingNew) {
        const wait = RETRY_MS[Math.min(retryAt.current, RETRY_MS.length - 1)]
        retryAt.current += 1
        retryTimer.current = window.setTimeout(() => { refill() }, wait)
      } else {
        retryAt.current = 0
      }
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

    const sent = saveShortlistReaction(access, shareToken, decided.id, reaction)
      .then((result) => {
        if (result?.state === 'shortlist') finish(result.films)
        else if (typeof result?.matches === 'number') setMatches(result.matches)
      })
      .catch((voteError) => setError(voteError.message))
      .finally(() => pending.current.delete(sent))
    pending.current.add(sent)
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
      <span>{progress}</span>
      {/* Back to the step, not a sheet over the deck. The position is asked
          for once at the start of the flow, and this is how somebody returns
          to change it — the same screen, reached the same way. */}
      {onSteer && (
        <button type="button" className="deck-steer" onClick={onSteer}>Steer</button>
      )}
    </header>
    <article className="deck-card swipe-card" key={film.id} {...swipe.handlers} style={swipe.style}>
      <span className="swipe-cue swipe-cue-left" aria-hidden="true" style={{ opacity: swipe.direction === 'left' ? swipe.strength : 0 }}>× No</span>
      <span className="swipe-cue swipe-cue-right" aria-hidden="true" style={{ opacity: swipe.direction === 'right' ? swipe.strength : 0 }}>♥ Yes</span>
      <div className="deck-art" style={film.artwork_url ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.86), transparent 62%), url(${film.artwork_url})` } : {}}>
        <h2>{film.title}<span className="deck-year">{film.year}</span></h2>
      </div>
      <div className="deck-copy">
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
        {/* Only a real note. The fallback repeated the header verbatim — the
            same three words twice on one screen, taking the space the art
            wanted. */}
        {film.note && <small>{film.note}</small>}
      </div>
    </article>
    <div className="deck-actions"><button type="button" disabled={swipe.committed} onClick={() => vote('no')}>×<span>No</span></button><button className="deck-heart" type="button" disabled={swipe.committed} onClick={() => vote('yes')}>♥<span>Yes</span></button></div>
    <p className="deck-note">Swipe right to say yes, left to pass.</p>
  </section></main>
}
