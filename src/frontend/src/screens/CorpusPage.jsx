import React from 'react'
import FilmFactors from '../components/atlas/FilmFactors.jsx'
import { loadAtlas } from '../services/atlasService.js'
import { loadModels } from '../services/factorService.js'
import '../styles/atlas.css'

// Look up any film and read where it stands.
//
// The atlas answers "what are the axes, and which films anchor them". This
// answers the question people actually arrive with — "what does the machine
// make of THIS film" — and it is the same component doing the work, because a
// film's position should read identically wherever it is shown.
export default function CorpusPage({ onBack }) {
  const [corpus, setCorpus] = React.useState(null)
  const [scorer, setScorer] = React.useState(null)
  const [query, setQuery] = React.useState('')
  const [selected, setSelected] = React.useState(null)
  const [error, setError] = React.useState(null)

  React.useEffect(() => {
    let live = true
    loadAtlas().then((payload) => live && setCorpus(payload)).catch((e) => live && setError(e.message))
    loadModels().then(({ models }) => live && models.length && setScorer(models[0].scorer)).catch(() => {})
    return () => { live = false }
  }, [])

  const all = corpus?.films || []
  const matches = React.useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return []
    return all.filter((film) => `${film.title} ${film.year ?? ''}`.toLowerCase().includes(needle))
  }, [all, query])

  return (
    <main className="atlas-page">
      <header className="atlas-header">
        {onBack && <button type="button" className="back-button" onClick={onBack}>←</button>}
        <div>
          <h1>What does it make of your film?</h1>
        </div>
      </header>

      <div className="atlas-wrap">
        <p className="atlas-lede">
          Every film here was read for the moral positions it takes, from its own dialogue —
          no reviews, no synopsis. Search {all.length ? `${all.length} films` : 'the corpus'} and
          open one to see where it lands on each axis, and the propositions that put it there.
        </p>

        {error && <p className="atlas-note">{error}</p>}

        <input
          className="atlas-search"
          value={query}
          placeholder="Search for a film"
          aria-label="Search for a film"
          onChange={(event) => { setQuery(event.target.value); setSelected(null) }}
        />

        {/* Never gated on the results: a search that matches nothing must still
            leave the box on screen to undo it. */}
        {query.trim() && !matches.length && (
          <p className="atlas-note">
            Nothing matches &ldquo;{query.trim()}&rdquo;. The corpus is {all.length} films, so
            plenty of cinema is not in it yet.
          </p>
        )}

        {!!matches.length && !selected && (
          <ul className="film-list">
            {matches.slice(0, 40).map((film) => (
              <li key={film.id}>
                <button type="button" onClick={() => setSelected(film)}>
                  <b>{film.title}</b> <span>{film.year}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {selected && (
          <section className="corpus-film">
            <div className="corpus-film-head">
              <div>
                <h2>{selected.title}</h2>
                <p className="atlas-note">{selected.year}</p>
              </div>
              <button className="link-button" type="button" onClick={() => setSelected(null)}>
                Choose another
              </button>
            </div>
            {scorer
              ? <FilmFactors scorer={scorer} filmId={selected.id} />
              : <p className="atlas-note">No model has read the corpus yet.</p>}
          </section>
        )}

        {!query.trim() && !selected && (
          <p className="atlas-note">
            Start typing a title. If a film is not here it simply has not been read yet — the
            corpus grows by subtitle availability, not by taste.
          </p>
        )}

        {/* The axes are asserted on this page and explained on that one. */}
        <p className="corpus-footer">
          <a className="quiet-link" href="#/atlas">Where do these scales come from? →</a>
        </p>
      </div>
    </main>
  )
}
