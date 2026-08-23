import React, { useEffect, useState } from 'react'
import useSwipeDecision from '../hooks/useSwipeDecision.js'
import { loadNextShortlistFilm, loadShortlistSelection, saveShortlistReaction } from '../services/shortlistService.js'

export default function ShortlistPage({ access, shareToken, onDone }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [voting, setVoting] = useState(false)
  const loadNext = () => loadNextShortlistFilm(access, shareToken)
    .then((nextResult) => { setResult(nextResult); setError(null) })
    .catch((nextError) => setError(nextError.message))
  useEffect(() => {
    loadNext()
    const poll = window.setInterval(() => {
      loadShortlistSelection(access, shareToken)
        .then((selection) => {
          if (selection.state === 'selected') setResult(selection)
        })
        .catch((pollError) => setError(pollError.message))
    }, 4000)
    return () => window.clearInterval(poll)
  }, [access, shareToken])
  useEffect(() => {
    if (result?.state === 'selected') onDone(result.film)
  }, [result, onDone])
  const film = result?.film
  async function vote(reaction) {
    if (!film || voting) return
    setVoting(true)
    try {
      const vote = await saveShortlistReaction(access, shareToken, film.id, reaction)
      if (vote.state === 'selected') onDone(vote.film)
      else await loadNext()
    } catch (voteError) {
      setError(voteError.message)
    } finally {
      setVoting(false)
    }
  }
  const swipe = useSwipeDecision({ disabled: !film || voting, onLeft: () => vote('no'), onRight: () => vote('yes') })

  if (error) return <main className="app-page"><p className="message">{error}</p></main>
  if (!result) return <main className="app-page"><p className="message">Finding your shortlist…</p></main>
  if (result.state === 'selected') return <main className="app-page"><p className="message">You found tonight’s film.</p></main>
  if (result.state === 'exhausted') return <main className="app-page"><p className="message">No more films are available right now.</p></main>

  return <main className="app-page"><section className="phone-screen deck-screen">
    <header className="deck-header"><span>Tonight’s list</span><span>Keep looking</span></header>
    <article className="deck-card swipe-card" {...swipe.handlers} style={swipe.style}>
      <span className="swipe-cue swipe-cue-left" aria-hidden="true" style={{ opacity: swipe.direction === 'left' ? swipe.strength : 0 }}>× No</span>
      <span className="swipe-cue swipe-cue-right" aria-hidden="true" style={{ opacity: swipe.direction === 'right' ? swipe.strength : 0 }}>♥ Yes</span>
      <div className="deck-art" style={film.artwork_url ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.8), transparent), url(${film.artwork_url})` } : {}}><h2>{film.title}</h2></div><div className="deck-copy"><span>{film.year}</span><p>{film.description}</p><small>{film.note || 'Matched for both of you'}</small></div>
    </article>
    <div className="deck-actions"><button type="button" disabled={voting || swipe.committed} onClick={() => vote('no')}>×<span>No</span></button><button className="deck-heart" type="button" disabled={voting || swipe.committed} onClick={() => vote('yes')}>♥<span>Yes</span></button></div>
    <p className="deck-note">Swipe right for yes · left for no. You can always use the buttons.</p>
  </section></main>
}
