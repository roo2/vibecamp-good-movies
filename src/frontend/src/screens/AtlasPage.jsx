import React from 'react'
import Factors from '../components/atlas/Factors.jsx'
import FilmPlane from '../components/atlas/FilmPlane.jsx'
import TasteDimensions from '../components/atlas/TasteDimensions.jsx'
import FilmDetail from '../components/atlas/FilmDetail.jsx'
import ModelPicker from '../components/atlas/ModelPicker.jsx'
import { filmPositions, loadAtlas, setCentroid } from '../services/atlasService.js'
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
  const [query, setQuery] = React.useState('')
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

  const chosen = React.useMemo(
    () => filmSets.filter((s) => activeSets.has(s.set_id)), [filmSets, activeSets])

  // Where each chosen set sits on average, in the axes' own units — computed
  // once here so the marker on the cloud and the numbers underneath it come
  // from the same arithmetic.
  const centres = React.useMemo(() => {
    const positions = filmPositions(factors?.factors)
    const out = {}
    for (const s of chosen) out[s.set_id] = setCentroid(positions, s.films)
    return out
  }, [factors, chosen])

  // The two axes the plane draws, in whichever space is selected. Built here so
  // the toggle changes one value and everything downstream follows.
  const plane = React.useMemo(() => {
    if (space === 'taste') {
      const dims = (taste?.dimensions || []).filter((d) => d.status === 'named').slice(0, 2)
      if (dims.length < 2) return null
      const [dx, dy] = dims
      const points = (taste.films || []).flatMap((f) => {
        const x = f.position?.[String(dx.dim_id)]
        const y = f.position?.[String(dy.dim_id)]
        return typeof x === 'number' && typeof y === 'number'
          ? [{ id: f.film_id, title: f.title, x, y }] : []
      })
      return {
        points,
        xAxis: { high: dx.pole_high, low: dx.pole_low },
        yAxis: { high: dy.pole_high, low: dy.pole_low },
      }
    }
    const list = (factors?.factors || []).slice(0, 2)
    if (list.length < 2) return null
    const byFilm = new Map()
    list.forEach((factor, k) => {
      for (const row of factor.distribution || []) {
        const seen = byFilm.get(row.film_id) || { title: row.title, v: [] }
        seen.v[k] = row.score
        byFilm.set(row.film_id, seen)
      }
    })
    const points = [...byFilm.entries()]
      .filter(([, f]) => f.v.length === 2 && f.v.every((n) => typeof n === 'number'))
      .map(([id, f]) => ({ id, title: f.title, x: f.v[0], y: f.v[1] }))
    const label = (f, end) => f?.[`pole_${end}_label`] || f?.name || ''
    return {
      points,
      xAxis: { high: label(list[0], 'high'), low: label(list[0], 'low') },
      yAxis: { high: label(list[1], 'high'), low: label(list[1], 'low') },
    }
  }, [space, taste, factors])

  // The reader's own compass, if they followed the link from it. Read on
  // demand rather than always: the atlas is a public page and most of its
  // readers have not taken the survey.
  const [viewer, setViewer] = React.useState(null)
  // A compass is measured against ONE reading. The atlas can be switched to any
  // of them, and plotting a person derived from deepseek's axes onto dolphin's
  // would put them somewhere meaningless with no sign that anything was wrong.
  const viewerHere = React.useMemo(() => {
    if (!viewer || viewer.scores?.length !== 3) return null
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
            Films are treated as respondents and moral propositions as items. A model writes
            propositions from the films&apos; dialogue, every film is scored against them, and the
            axes are whatever groups of propositions the films answer together. Nothing is
            imposed — including how many axes there are.
          </p>
          <p className="atlas-note">
            The model that writes the questions need not be the one that answers them, and the
            two roles fail differently — so the toggle offers each pairing rather than one button
            per model. Dolphin writes the sharper questions: 98 of its 218 propositions divide
            films, against 72 of deepseek&apos;s 297. Deepseek gives the steadier answers,
            recovering the same six axes from either bank, where dolphin finds one axis in its own
            questions and fourteen in deepseek&apos;s — most of those resting on a handful of
            propositions each.
          </p>
          <p className="atlas-note">
            Propositions every film agrees with are set aside before any of this. Most of a bank
            turns out to be consensus rather than measurement, and a claim nobody argues with
            cannot tell two films apart.
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
          <ModelPicker models={models} withdrawn={withdrawn}
                       selected={selected?.reading_id} onSelect={setSelected} />
          {factorsError && <p className="atlas-note">{factorsError}</p>}
          {!factors && !factorsError && <p className="message">Reading {selected?.scorer}…</p>}
          {/* Before the per-axis breakdown, because the shape of the whole
              corpus is the thing a reader most wants and cannot get from three
              separate distributions read one after another. */}
          {factors?.factors?.length >= 3 && (
            <>
              {filmSets.length > 0 && (
                <div className="set-picker">
                  <span className="set-picker-label">highlight a set</span>
                  {filmSets.map((s) => (
                    <button
                      key={s.set_id} type="button"
                      className={`set-chip${activeSets.has(s.set_id) ? ' on' : ''}`}
                      style={activeSets.has(s.set_id)
                        ? { borderColor: s.colour, color: s.colour }
                        : undefined}
                      aria-pressed={activeSets.has(s.set_id)}
                      title={s.source || undefined}
                      onClick={() => setActiveSets((prev) => {
                        const next = new Set(prev)
                        next.has(s.set_id) ? next.delete(s.set_id) : next.add(s.set_id)
                        return next
                      })}>
                      <i style={{ background: s.colour }} />{s.name}
                      <small>{s.n}</small>
                    </button>
                  ))}
                </div>
              )}
              {(taste?.dimensions || []).length > 0 && (
                <div className="plane-axis-pick" role="tablist"
                     aria-label="Which axes to plot">
                  <button type="button" role="tab" aria-selected={space === 'moral'}
                          className={space === 'moral' ? 'on' : undefined}
                          onClick={() => setSpace('moral')}>
                    What films argue
                  </button>
                  <button type="button" role="tab" aria-selected={space === 'taste'}
                          className={space === 'taste' ? 'on' : undefined}
                          onClick={() => setSpace('taste')}>
                    What people choose by
                  </button>
                </div>
              )}
              {plane && (
                <FilmPlane points={plane.points} xAxis={plane.xAxis} yAxis={plane.yAxis}
                           sets={space === 'moral' ? chosen : []}
                           viewer={space === 'moral' ? viewerHere : null}
                           selectedId={selectedId} onSelect={setSelectedId} />
              )}
              {wantsMe && !viewerHere && (
                <p className="atlas-note">
                  {!access ? 'Take the survey first and this will show where you sit.'
                    : !viewer ? 'Reading your compass…'
                      : 'Your compass was measured against the '
                        + `${viewer.dim_version} reading, so it cannot be placed on this one. `
                        + 'Switch the reading above to see yourself.'}
                </p>
              )}
              {[...activeSets].map((id) => {
                const s = filmSets.find((x) => x.set_id === id)
                const c = centres[id]
                return s ? (
                  <p key={id} className="set-source">
                    <b style={{ color: s.colour }}>{s.name}</b> — {s.description}{' '}
                    <em>
                      Source: {s.url
                        ? <a href={s.url} target="_blank" rel="noreferrer noopener">{s.source}</a>
                        : s.source}.
                    </em>{' '}
                    {s.n} of its films are in the corpus.
                    {c && (
                      <span className="set-centre">
                        Centre:{' '}
                        {c.mean.map((m, k) => (
                          <b key={k}>{m >= 0 ? '+' : '−'}{Math.abs(m).toFixed(3)}</b>
                        )).reduce((a, b) => [a, ' / ', b])}
                        {' '}on {factors.factors.slice(0, 3).map((f) => f.name).join(', ')}.
                      </span>
                    )}
                  </p>
                ) : null
              })}
            </>
          )}
          <Factors data={factors} />
        </>
      )}

      {/* Gated on the corpus, not on the RESULTS. Searching for a film that is
          not here used to unmount the whole section — including the search box —
          so the reader was left staring at a gap with no way to undo the typing
          that caused it. */}
      {/* After the axes, not before: the moral axes only survive being shown
          next to taste, and a reader has to see taste at full strength for that
          to mean anything. Outside the corpus gate, because it does not depend
          on the film list having loaded. */}
      <TasteDimensions taste={taste} />

      {!!(corpus?.films || []).length && (
        <section aria-labelledby="films">
          <h2 id="films">The corpus</h2>
          <p className="atlas-note">
            {(corpus?.films || []).length} films. Open one to read the dialogue every claim about
            it was scored from — the point of showing it is that a reader can disagree with the
            verdict.
          </p>
          <input
            className="atlas-search"
            value={query}
            placeholder="Find a film"
            onChange={(event) => setQuery(event.target.value)}
          />
          {!films.length && (
            <p className="atlas-note">
              Nothing here matches &ldquo;{query.trim()}&rdquo;. The corpus is
              {' '}{(corpus?.films || []).length} films, so a lot of cinema is missing from it.
            </p>
          )}
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
          variant={selected?.variant}
          bank={selected?.bank_version}
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
