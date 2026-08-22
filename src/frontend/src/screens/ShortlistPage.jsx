import React, { useEffect, useState } from 'react'
import { loadShortlist, saveShortlistReaction } from '../services/shortlistService.js'

export default function ShortlistPage({ access, onDone }) {
  const [films, setFilms] = useState([])
  const [index, setIndex] = useState(0)
  useEffect(() => { loadShortlist(access).then(setFilms) }, [access])
  const film = films[index]
  if (!film) return <main className="app-page"><p className="message">{films.length ? 'Your votes are in.' : 'Finding your shortlist…'}</p></main>
  async function vote(reaction) {
    await saveShortlistReaction(access, film.id, reaction)
    if (index === films.length - 1) onDone()
    else setIndex(index + 1)
  }
  return <main className="app-page"><section className="phone-screen deck-screen">
    <header className="deck-header"><span>Tonight’s list</span><span>{films.length - index} left</span></header>
    <article className="deck-card"><div className="deck-art" style={film.artwork_url ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.8), transparent), url(${film.artwork_url})` } : {}}><h2>{film.title}</h2></div><div className="deck-copy"><span>{film.year}</span><p>{film.description}</p><small>Matched for both of you</small></div></article>
    <div className="deck-actions"><button onClick={() => vote('no')}>×<span>Pass</span></button><button className="deck-heart" onClick={() => vote('yes')}>♥<span>Want</span></button></div>
    <p className="deck-note">Votes stay private until everyone has chosen.</p>
  </section></main>
}
