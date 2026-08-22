import React, { useEffect, useState } from 'react'
import { loadNextShortlistFilm, loadShortlistSelection, saveShortlistReaction } from '../services/shortlistService.js'

export default function ShortlistPage({ access, shareToken, onDone }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
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
  if (error) return <main className="app-page"><p className="message">{error}</p></main>
  if (!result) return <main className="app-page"><p className="message">Finding your shortlist…</p></main>
  if (result.state === 'selected') return <main className="app-page"><p className="message">You found tonight’s film.</p></main>
  if (result.state === 'exhausted') return <main className="app-page"><p className="message">No more films are available right now.</p></main>
  const film = result.film
  async function vote(reaction) {
    try {
      const vote = await saveShortlistReaction(access, shareToken, film.id, reaction)
      if (vote.state === 'selected') onDone(vote.film)
      else loadNext()
    } catch (voteError) {
      setError(voteError.message)
    }
  }
  return <main className="app-page"><section className="phone-screen deck-screen">
    <header className="deck-header"><span>Tonight’s list</span><span>Keep looking</span></header>
    <article className="deck-card"><div className="deck-art" style={film.artwork_url ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.8), transparent), url(${film.artwork_url})` } : {}}><h2>{film.title}</h2></div><div className="deck-copy"><span>{film.year}</span><p>{film.description}</p><small>{film.note || 'Matched for both of you'}</small></div></article>
    <div className="deck-actions"><button onClick={() => vote('no')}>×<span>Pass</span></button><button className="deck-heart" onClick={() => vote('yes')}>♥<span>Want</span></button></div>
    <p className="deck-note">Votes stay private until everyone has chosen.</p>
  </section></main>
}
