import React from 'react'
import FilmFactors from '../components/atlas/FilmFactors.jsx'
import FilmPlane from '../components/atlas/FilmPlane.jsx'
import FilmTaste from '../components/atlas/FilmTaste.jsx'
import { loadAtlas, planePoints } from '../services/atlasService.js'
import { loadFactors, loadModels, loadTaste } from '../services/factorService.js'
import '../styles/atlas.css'

// Look up any film and read where it stands.
//
// The atlas answers "what are the axes, and which films anchor them". This
// answers the question people actually arrive with — "what does the machine
// make of THIS film" — and it is the same component doing the work, because a
// film's position should read identically wherever it is shown.
export default function CorpusPage({ onBack }) {
  const [corpus, setCorpus] = React.useState(null)
  // The whole reading, not just the scorer: which propositions a film was judged
  // against is half of what its position means.
  const [reading, setReading] = React.useState(null)
  const [query, setQuery] = React.useState('')
  const [selected, setSelected] = React.useState(null)
  const [error, setError] = React.useState(null)
  const [factors, setFactors] = React.useState(null)
  const [taste, setTaste] = React.useState(null)

  React.useEffect(() => {
    let live = true
    loadAtlas().then((payload) => live && setCorpus(payload)).catch((e) => live && setError(e.message))
    // The reading the PRODUCT reads, which the server marks — not whichever
    // has the most verdicts. Picking models[0] here while the atlas picked the
    // product's reading meant the two pages quietly showed different data.
    loadModels()
      .then(({ models }) => {
        if (live && models.length) setReading(models.find((m) => m.product) || models[0])
      })
      .catch(() => {})
    loadTaste().then((t) => live && setTaste(t)).catch(() => {})
    return () => { live = false }
  }, [])

  // The same axes the atlas draws, from the same reading, through the same
  // helper — so a film cannot sit in one place here and another there.
  React.useEffect(() => {
    if (!reading) return undefined
    let live = true
    loadFactors(reading).then((f) => live && setFactors(f)).catch(() => {})
    return () => { live = false }
  }, [reading])

  const plane = React.useMemo(() => planePoints(factors, taste, 'moral'), [factors, taste])

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
            {reading
              ? <FilmFactors scorer={reading.scorer} filmId={selected.id}
                             variant={reading.variant} bank={reading.bank_version} />
              : <p className="atlas-note">No model has read the corpus yet.</p>}
            <FilmTaste taste={taste} filmId={selected.id} />
          </section>
        )}

        {/* Where it sits among everything else. A film's axis scores mean
            little as bare numbers — "0.47 on redemptive" is only legible next
            to where every other film landed. */}
        {plane && (
          <section className="corpus-plane">
            <h2>{selected ? `Where ${selected.title} sits` : 'The corpus, on two axes'}</h2>
            <p className="atlas-note">
              {selected
                ? 'Highlighted among every film that has been read. Click any other to open it.'
                : 'Every film that has been read, positioned with taste held constant. '
                  + 'Click one to open it.'}
            </p>
            <FilmPlane points={plane.points} xAxis={plane.xAxis} yAxis={plane.yAxis}
                       selectedId={selected?.id}
                       onSelect={(id) => {
                         const film = all.find((f) => f.id === id)
                         if (film) { setSelected(film); setQuery('') }
                       }} />
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
