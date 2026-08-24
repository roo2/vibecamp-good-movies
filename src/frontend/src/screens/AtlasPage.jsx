import React from 'react'
import Factors from '../components/atlas/Factors.jsx'
import FilmDetail from '../components/atlas/FilmDetail.jsx'
import ModelPicker from '../components/atlas/ModelPicker.jsx'
import { loadAtlas } from '../services/atlasService.js'
import { loadFactors, loadModels } from '../services/factorService.js'
import '../styles/atlas.css'

// This page used to be built around one dimension set: eight axes a model was
// asked to produce, a funnel showing the reduction down to them, a reliability
// battery attacking them, and every film ranked along each. All of it rested on
// a count nobody had checked, and none of it survives axes that are discovered
// per model — because there is no longer one answer to display.
//
// What replaced it is narrower on purpose: pick a model, see the axes ITS
// verdicts produced, and see the evidence for why there are that many. The film
// list stays because the source text is what every claim was read from, and
// being able to check a claim against the dialogue is the point.

// An open film is in the URL, so a reading of one film is a link someone can
// send. `#/atlas?film=parasite-2019`.
function filmParam() {
  const [, search = ''] = window.location.hash.split('?')
  return new URLSearchParams(search).get('film')
}

function AtlasPage({ onBack }) {
  const [models, setModels] = React.useState(null)
  const [withdrawn, setWithdrawn] = React.useState([])
  const [selected, setSelected] = React.useState(null)
  const [factors, setFactors] = React.useState(null)
  const [factorsError, setFactorsError] = React.useState(null)
  const [corpus, setCorpus] = React.useState(null)
  const [query, setQuery] = React.useState('')
  const [selectedId, setSelectedId] = React.useState(filmParam)

  React.useEffect(() => {
    let live = true
    loadModels()
      .then(({ models: found, withdrawn: gone }) => {
        if (!live) return
        setModels(found)
        setWithdrawn(gone)
        // Most verdicts first, so the page opens on the model with the most to
        // say rather than on whichever sorts first alphabetically.
        if (found.length) setSelected(found[0])
      })
      .catch(() => live && setModels([]))
    // The corpus index is a separate, cheaper read: it carries the films and
    // their source text, which do not depend on which model you are reading.
    loadAtlas().then((payload) => live && setCorpus(payload)).catch(() => {})
    return () => { live = false }
  }, [])

  React.useEffect(() => {
    if (!selected) return undefined
    let live = true
    setFactors(null)
    setFactorsError(null)
    loadFactors(selected.scorer, selected.variant, selected.bank_version)
      .then((payload) => live && setFactors(payload))
      .catch((error) => live && setFactorsError(error.message))
    return () => { live = false }
  }, [selected])

  React.useEffect(() => {
    const onHash = () => setSelectedId(filmParam())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const films = React.useMemo(() => {
    const all = corpus?.films || []
    const needle = query.trim().toLowerCase()
    if (!needle) return all
    return all.filter((film) => `${film.title} ${film.year ?? ''}`.toLowerCase().includes(needle))
  }, [corpus, query])

  if (models === null) {
    return <main className="app-page"><p className="message">Reading the atlas…</p></main>
  }

  return (
    <main className="atlas-page">
      <header className="atlas-header">
        {onBack && <button type="button" className="back-button" onClick={onBack}>←</button>}
        <div>
          <h1>What do these films argue?</h1>
          <p className="atlas-note">
            Films are treated as respondents and moral propositions as items. Each model writes
            its own propositions from the films&apos; dialogue, scores every film against them,
            and the axes are whatever groups of propositions the films answer together. Nothing
            is imposed — including how many axes there are.
          </p>
        </div>
      </header>

      {!models.length ? (
        <section>
          <p className="atlas-note">
            No model has scored the corpus yet. Run <code>atlas model-propose</code>,{' '}
            <code>atlas model-bank</code>, <code>atlas model-scan</code> and{' '}
            <code>atlas name-factors</code>.
          </p>
        </section>
      ) : (
        <>
          <ModelPicker models={models} withdrawn={withdrawn} selected={selected?.scorer} onSelect={setSelected} />
          {factorsError && <p className="atlas-note">{factorsError}</p>}
          {!factors && !factorsError && <p className="message">Reading {selected?.scorer}…</p>}
          <Factors data={factors} />
        </>
      )}

      {!!films.length && (
        <section aria-labelledby="films">
          <h2 id="films">The corpus</h2>
          <p className="atlas-note">
            {films.length} films. Open one to read the dialogue every claim about it was scored
            from — the point of showing it is that a reader can disagree with the verdict.
          </p>
          <input
            className="atlas-search"
            value={query}
            placeholder="Find a film"
            onChange={(event) => setQuery(event.target.value)}
          />
          <ul className="film-list">
            {films.slice(0, 60).map((film) => (
              <li key={film.id}>
                <button type="button" onClick={() => setSelectedId(film.id)}>
                  <b>{film.title}</b> <span>{film.year}</span>
                </button>
              </li>
            ))}
          </ul>
          {films.length > 60 && (
            <p className="atlas-note">Showing 60 of {films.length} — search to narrow.</p>
          )}
        </section>
      )}

      {selectedId && (
        <FilmDetail
          film={(corpus?.films || []).find((f) => f.id === selectedId)}
          scorer={selected?.scorer}
          onClose={() => setSelectedId(null)}
        />
      )}

      <footer className="atlas-footer">
        <p>
          Read live from the store — there is no published snapshot to go stale.
          {corpus?.generated_at && ` Corpus read ${new Date(corpus.generated_at).toLocaleString()}.`}
        </p>
      </footer>
    </main>
  )
}

export default AtlasPage
