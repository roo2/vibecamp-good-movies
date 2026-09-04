import React from 'react'
import FilmExplorer from '../components/atlas/FilmExplorer.jsx'
import { loadAtlas, plotAxes } from '../services/atlasService.js'
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
  const [selected, setSelected] = React.useState(null)
  const [error, setError] = React.useState(null)
  const [space, setSpace] = React.useState('moral')
  const [pair, setPair] = React.useState(null)
  const [factors, setFactors] = React.useState(null)
  const [taste, setTaste] = React.useState(null)
  // Every axis the product reads, which is what the picker offers — the same
  // selector the atlas uses, so a label here cannot name one pair while the
  // plot draws another.
  //
  // Below the state it reads, not above it. `const` is not hoisted, so a
  // useMemo over `factors` declared before `factors` exists throws on the first
  // render and the page goes black — no message, nothing in the network tab.
  const productAxes = React.useMemo(() => plotAxes(factors), [factors])

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
    // Three positional arguments, not the reading object. Passing the object
    // asked for /api/factors/[object Object], which 404s — and the silent catch
    // below turned that into a blank page rather than a message.
    loadFactors(reading.scorer, reading.variant, reading.bank_version)
      .then((f) => live && setFactors(f))
      .catch((e) => live && setError(e.message))
    return () => { live = false }
  }, [reading])


  const all = corpus?.films || []

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
          Every film here was read from its own dialogue — no reviews, no synopsis.
          Search {all.length ? `${all.length} films` : 'the corpus'}, or pick a point.
        </p>

        {error && <p className="atlas-note">{error}</p>}

        {/* The same three spaces and the same axis picker the atlas has. This
            page drew one fixed view of one pair, so a reader who found their
            film here could not ask what it looks like on any other axis, or in
            taste at all — the controls existed one page away and nothing said
            so. */}
        <FilmExplorer films={all} factors={factors} taste={taste} reading={reading}
                      selectedId={selected?.id || null}
                      onSelect={(id) => setSelected(all.find((f) => f.id === id) || null)}
                      space={space} onSpaceChange={setSpace}
                      pair={pair} onPairChange={setPair}
                      axes={productAxes} />

        {!selected && (
          <p className="atlas-note">
            If a film is not here it simply has not been read yet — the corpus grows by subtitle
            availability, not by taste.
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
