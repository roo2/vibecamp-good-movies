import React from 'react'
import Factors from '../components/atlas/Factors.jsx'
import FilmExplorer from '../components/atlas/FilmExplorer.jsx'
import AxisAdjustment from '../components/atlas/AxisAdjustment.jsx'
import TasteDimensions from '../components/atlas/TasteDimensions.jsx'
import ModelPicker from '../components/atlas/ModelPicker.jsx'
import { filmPositions, loadAtlas, plotAxes, setCentroid } from '../services/atlasService.js'
import { loadMoralProfile } from '../services/profileService.js'
import { loadFactors, loadFilmSets, loadModels, loadTaste } from '../services/factorService.js'
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

function AtlasPage({ onBack, access }) {
  const [models, setModels] = React.useState(null)
  const [withdrawn, setWithdrawn] = React.useState([])
  const [selected, setSelected] = React.useState(null)
  const [factors, setFactors] = React.useState(null)
  const [filmSets, setFilmSets] = React.useState([])
  const [activeSets, setActiveSets] = React.useState(() => new Set())
  const [factorsError, setFactorsError] = React.useState(null)
  const [corpus, setCorpus] = React.useState(null)
  const [selectedId, setSelectedId] = React.useState(filmParam)
  const [taste, setTaste] = React.useState(null)
  // Which pair of axes the plane draws. Moral by default — this is an atlas of
  // what films argue, and taste is the comparison rather than the subject.
  const [space, setSpace] = React.useState('moral')

  React.useEffect(() => {
    let live = true
    loadFilmSets().then((p) => live && setFilmSets(p.sets || [])).catch(() => {})
    loadTaste().then((t) => live && setTaste(t)).catch(() => {})
    return () => { live = false }
  }, [])

  // Grouped rather than alphabetical or by size: the religious lists, then the
  // political ones, then the eras. Reading them in that order is reading the
  // question the project asks — do communities that state opposed commitments
  // sit apart — and the era sets are a control rather than a worldview, so they
  // come last. Anything unlisted keeps its server order behind these.
  const SET_ORDER = ['catholic', 'christian-edifying', 'conservative',
                     'socialist', 'feminist', 'red-pilled',
                     'old-hollywood', 'new-hollywood', 'blockbuster-hollywood',
                     'franchise-hollywood', 'mcu']
  const orderedSets = React.useMemo(() => {
    const rank = (s) => {
      const at = SET_ORDER.indexOf(s.set_id)
      return at === -1 ? SET_ORDER.length : at
    }
    return [...filmSets].sort((a, b) => rank(a) - rank(b))
  }, [filmSets])

  const chosen = React.useMemo(
    () => orderedSets.filter((s) => activeSets.has(s.set_id)), [orderedSets, activeSets])

  // The axes the plot draws, from the one selector the plane and the centroids
  // also use, so a label cannot name one pair while the plot draws another.
  const shownAxes = React.useMemo(() => plotAxes(factors), [factors])

  // Where each chosen set sits on average, in the axes' own units — computed
  // once here so the marker on the cloud and the numbers underneath it come
  // from the same arithmetic.
  const centres = React.useMemo(() => {
    const positions = filmPositions(factors, space)
    const out = {}
    for (const s of chosen) out[s.set_id] = setCentroid(positions, s.films)
    return out
  }, [factors, chosen, space])

  // The two axes the plane draws, in whichever space is selected. Built here so
  // the toggle changes one value and everything downstream follows.
  // The reader's own compass, if they followed the link from it. Read on
  // demand rather than always: the atlas is a public page and most of its
  // readers have not taken the survey.
  const [viewer, setViewer] = React.useState(null)
  // A compass is measured against ONE reading. The atlas can be switched to any
  // of them, and plotting a person derived from deepseek's axes onto dolphin's
  // would put them somewhere meaningless with no sign that anything was wrong.
  const viewerHere = React.useMemo(() => {
    if (!viewer || (viewer.scores?.length || 0) < 2) return null
    if (viewer.dim_version !== selected?.scorer) return null
    if (viewer.bank_version !== selected?.bank_version) return null
    return { scores: viewer.scores.map((s) => s.score), label: 'You' }
  }, [viewer, selected])
  const wantsMe = (window.location.hash.split('?')[1] || '').includes('me=1')
  React.useEffect(() => {
    if (!wantsMe || !access) return undefined
    let live = true
    loadMoralProfile(access)
      .then((p) => live && setViewer(p))
      .catch(() => {})
    return () => { live = false }
  }, [wantsMe, access])

  React.useEffect(() => {
    let live = true
    loadModels()
      .then(({ models: found, withdrawn: gone }) => {
        if (!live) return
        setModels(found)
        setWithdrawn(gone)
        // Open on the reading the PRODUCT reads, which the server marks. It
        // used to open on whichever reading had the most verdicts — a fact
        // about how much scoring has been done, not about which answer is in
        // use — so the atlas and the recommender disagreed by default.
        if (found.length) setSelected(found.find((m) => m.product) || found[0])
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
            Films answer moral propositions written from their own dialogue. An axis is a set of
            propositions that films answer together. Nobody chose them, or how many there are.
          </p>
          <p className="atlas-note">
            One model writes the questions, another answers them. They fail differently, so every
            pairing is here to compare.
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
          {/* Before the axes, not after. The moral axes are weak predictors of
              what anyone enjoys, and a reader who meets them first is being
              shown the answer without the thing it has to survive. */}
          <TasteDimensions taste={taste} />
          {factorsError && <p className="atlas-note">{factorsError}</p>}
          {!factors && !factorsError && <p className="message">Reading {selected?.scorer}…</p>}
          {/* Down here, next to the controls it belongs with rather than at the
              top of the page: which model produced a reading is a thing you
              change while looking at the plot, not a preamble to it.
              Deliberately OUTSIDE the `>= 2 factors` gate below — a reading
              with too few factors draws no plot, and a picker that disappeared
              with it would leave no way to switch off the broken one. */}
          <ModelPicker models={models} withdrawn={withdrawn}
                       selected={selected?.reading_id} onSelect={setSelected} />
          {/* Before the per-axis breakdown, because the shape of the whole
              corpus is the thing a reader most wants and cannot get from three
              separate distributions read one after another. */}
          {factors?.factors?.length >= 2 && (
            <>
              {filmSets.length > 0 && (
                <div className="set-picker">
                  <span className="set-picker-label">highlight a set</span>
                  {/* The provenance rides WITH the chip rather than as prose
                      under the plot. A set is somebody's claim and the claim
                      has to stay attached to it, but eleven paragraphs of
                      sources pushed the plot off the screen. Hover or focus
                      opens it; the chip still carries the source in `title` so
                      it survives with no pointer at all. */}
                  {orderedSets.map((s) => (
                    <span key={s.set_id} className="set-chip-wrap">
                      <button
                        type="button"
                        className={`set-chip${activeSets.has(s.set_id) ? ' on' : ''}`}
                        style={activeSets.has(s.set_id)
                          ? { borderColor: s.colour, color: s.colour }
                          : undefined}
                        aria-pressed={activeSets.has(s.set_id)}
                        aria-describedby={`set-tip-${s.set_id}`}
                        title={s.source || undefined}
                        onClick={() => setActiveSets((prev) => {
                          const next = new Set(prev)
                          next.has(s.set_id) ? next.delete(s.set_id) : next.add(s.set_id)
                          return next
                        })}>
                        <i style={{ background: s.colour }} />{s.name}
                        <small>{s.n}</small>
                      </button>
                      <span className="set-tip" id={`set-tip-${s.set_id}`} role="tooltip">
                        <b style={{ color: s.colour }}>{s.name}</b>
                        <span className="set-tip-desc">{s.description}</span>
                        <span className="set-tip-src">
                          {s.url
                            ? <a href={s.url} target="_blank" rel="noreferrer noopener">{s.source}</a>
                            : s.source}
                        </span>
                        <span className="set-tip-n">
                          {s.n} of its films are in the corpus.
                          {centres[s.set_id] && space !== 'taste' && (
                            <>{' '}Centre {centres[s.set_id].mean
                              .slice(0, shownAxes.length)
                              .map((m) => `${m >= 0 ? '+' : '−'}${Math.abs(m).toFixed(3)}`)
                              .join(' / ')} on {shownAxes.map((f) => f.name).join(', ')}.</>
                          )}
                        </span>
                      </span>
                    </span>
                  ))}
                </div>
              )}
              <FilmExplorer films={corpus?.films || []} factors={factors} taste={taste}
                            reading={selected} selectedId={selectedId}
                            onSelect={setSelectedId} sets={chosen} viewer={viewerHere}
                            space={space} onSpaceChange={setSpace} />
              {wantsMe && !viewerHere && (
                <p className="atlas-note">
                  {!access ? 'Take the survey first and this will show where you sit.'
                    : !viewer ? 'Reading your compass…'
                      : 'Your compass was measured against the '
                        + `${viewer.dim_version} reading, so it cannot be placed on this one. `
                        + 'Switch the reading above to see yourself.'}
                </p>
              )}
            </>
          )}
          <AxisAdjustment data={factors} taste={taste} />
          <Factors data={factors} />
        </>
      )}

      {/* Gated on the corpus, not on the RESULTS. Searching for a film that is
          not here used to unmount the whole section — including the search box —
          so the reader was left staring at a gap with no way to undo the typing
          that caused it. */}
    </main>
  )
}

export default AtlasPage
