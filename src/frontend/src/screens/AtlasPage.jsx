import React from 'react'
import { DivergingBars, MagnitudeBars, StatTiles } from '../components/atlas/Charts.jsx'
import FilmDetail from '../components/atlas/FilmDetail.jsx'
import { Dimensionality } from '../components/atlas/Dimensionality.jsx'
import { Reduction, Reliability } from '../components/atlas/Method.jsx'
import {
  FATE_LABELS, dimensionsByItems, fateDistribution, filmsOnAxis, filterFilms,
  ironyFilms, loadAtlas, originByFate,
} from '../services/atlasService.js'
import '../styles/atlas.css'

const FILTERS = [
  ['all', 'All'],
  ['destroyed', 'Destroyed'],
  ['reconciled', 'Reconciled'],
  ['escapes', 'Escapes'],
  ['irony', 'Depicts ≠ endorses'],
  ['origin', 'Evil explained'],
]

// An open film is in the URL, so a reading of one film is a link someone can
// send. `#/atlas?film=parasite-2019`.
function filmParam() {
  const [, search = ''] = window.location.hash.split('?')
  return new URLSearchParams(search).get('film')
}

function AtlasPage({ onBack }) {
  const [atlas, setAtlas] = React.useState(null)
  const [error, setError] = React.useState(null)
  const [axis, setAxis] = React.useState(null)
  const [query, setQuery] = React.useState('')
  const [filter, setFilter] = React.useState('all')
  const [selectedId, setSelectedId] = React.useState(filmParam)

  React.useEffect(() => {
    let live = true
    loadAtlas()
      .then((payload) => {
        if (!live) return
        setAtlas(payload)
        setAxis(payload.dimensions?.[0]?.dim_id ?? null)
      })
      .catch((loadError) => live && setError(loadError.message))
    return () => { live = false }
  }, [])

  React.useEffect(() => {
    const sync = () => setSelectedId(filmParam())
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])

  const openFilm = React.useCallback((film) => {
    window.location.hash = film ? `/atlas?film=${encodeURIComponent(film.id)}` : '/atlas'
  }, [])

  if (error) {
    return (
      <main className="atlas-page">
        <div className="atlas-wrap">
          <p className="atlas-error" role="alert">{error}</p>
        </div>
      </main>
    )
  }
  if (!atlas) {
    return (
      <main className="atlas-page">
        <div className="atlas-wrap"><p className="atlas-loading">Reading the store…</p></div>
      </main>
    )
  }

  const { totals } = atlas
  const dims = dimensionsByItems(atlas)
  const activeDim = atlas.dimensions.find((dim) => dim.dim_id === axis) || atlas.dimensions[0]
  const onAxis = activeDim ? filmsOnAxis(atlas, activeDim.dim_id) : []
  const fates = fateDistribution(atlas)
  const irony = ironyFilms(atlas)
  const matrix = originByFate(atlas)
  const visible = filterFilms(atlas, { query, filter })
  const scored = atlas.coverage.filter((row) => row.films_scored > 0)
  const selected = selectedId ? atlas.films.find((film) => film.id === selectedId) : null

  return (
    <main className="atlas-page">
      <div className="atlas-wrap">

        <header className="atlas-header">
          <div className="atlas-topbar">
            <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Moral Atlas</span></div>
            {onBack && <button type="button" className="link-button" onClick={onBack}>Back to the app</button>}
          </div>
          <p className="screen-label">
            The dataset · {totals.films} films · {totals.dimensions} derived axes
          </p>
          <h1>What a film <em>believes</em>, measured rather than argued about.</h1>
          <p className="atlas-lede">
            Every film is read for the moral positions it actually takes, scored against a
            fixed bank of {totals.bank_items} propositions, and placed on axes nobody chose in
            advance — they are whatever the bank turned out to be measuring.
          </p>
          <p className="atlas-caveat">
            Numbers below are derived from the films’ own text: plot summaries, critical
            reception, and dialogue. Nothing here is a rating, and none of it is a claim
            about whether a film is good.
          </p>
        </header>

        <section aria-labelledby="store-now">
          <h2 id="store-now">In the store right now</h2>
          <StatTiles tiles={[
            { label: 'Films', value: totals.films, hint: `${totals.films_with_skeleton} carry a skeleton` },
            { label: 'Read on full evidence', value: `${totals.films_with_full_skeleton}/${totals.films}`, hint: 'plot + reception + dialogue' },
            { label: 'Bank items', value: totals.bank_items, hint: `from ${totals.propositions} raw propositions` },
            { label: 'Scores', value: totals.scores.toLocaleString(), hint: 'film × item × condition' },
            { label: 'Derived axes', value: totals.dimensions, hint: `${totals.films_profiled} films placed` },
            { label: 'Spend so far', value: `$${atlas.spend_usd}`, hint: 'every stage, all conditions' },
          ]}
          />
        </section>

        {atlas.reduction && (
          <section aria-labelledby="reduction">
            <h2 id="reduction">
              From {atlas.reduction.stages[0].n.toLocaleString()} separate moral claims to
              {' '}{totals.dimensions}
            </h2>
            <p className="atlas-note">
              Films were treated as respondents and moral propositions as items, the way the
              Big Five personality factors were found: harvest a large pool of statements out
              of the corpus itself, cut it to a fixed bank, score every film against every
              item, then ask what the bank is really measuring. Nothing was chosen in advance
              — the axes are whatever survived.
            </p>
            <Reduction reduction={atlas.reduction} dimensions={atlas.dimensions} />
          </section>
        )}

        {atlas.reliability && (
          <section aria-labelledby="reliability">
            <h2 id="reliability">Does this hold up?</h2>
            <p className="atlas-note">
              Four attempts to knock the axes down, reported as numbers rather than as a
              verdict. They are here because “an LLM read 694 statements and found eight
              themes” is not evidence of anything on its own.
            </p>
            <Reliability
              reliability={atlas.reliability}
              dimensions={atlas.dimensions}
              splitHalf={atlas.split_half}
            />
          </section>
        )}

        {/* Placed straight after the reliability battery because it answers the
            objection that section raises and cannot itself settle: the axes are
            checked for coherence, but their COUNT was supplied. */}
        <Dimensionality dimensionality={atlas.dimensionality} />

        {dims.length > 0 && (
          <section aria-labelledby="axes">
            <h2 id="axes">The axes, and how much of the bank lands on each</h2>
            <p className="atlas-note">
              The axes were derived by reading the bank, not by imposing a theory on it. A
              large axis is one the corpus keeps returning to; a small one is a position
              these forty films rarely take.
            </p>
            <MagnitudeBars
              caption="Bank items assigned to each derived moral axis"
              rows={dims.map((dim) => ({
                key: dim.dim_id,
                label: dim.name,
                value: dim.n_items,
                title: `${dim.name}: ${dim.n_items} items${dim.mean_fit != null ? `, mean fit ${dim.mean_fit}` : ''}`,
              }))}
              note="One item sits on exactly one axis, so these sum to the active bank."
            />
          </section>
        )}

        {activeDim && onAxis.length > 0 && (
          <section aria-labelledby="where-films-sit">
            <h2 id="where-films-sit">Where each film sits</h2>
            <p className="atlas-note">{activeDim.question}</p>
            <div className="axis-picker" role="group" aria-label="Choose an axis">
              {atlas.dimensions.map((dim) => (
                <button
                  key={dim.dim_id}
                  type="button"
                  className={`chip ${dim.dim_id === activeDim.dim_id ? 'on' : ''}`}
                  aria-pressed={dim.dim_id === activeDim.dim_id}
                  onClick={() => setAxis(dim.dim_id)}
                >
                  {dim.name}
                </button>
              ))}
            </div>
            <DivergingBars
              caption={`Every scored film on the axis “${activeDim.name}”`}
              lowLabel={activeDim.pole_low}
              highLabel={activeDim.pole_high}
              selectedKey={selected?.id}
              onSelect={(row) => openFilm(row.film)}
              rows={onAxis.map((row) => ({
                key: row.film.id,
                label: `${row.film.title} (${row.film.year})`,
                value: row.net,
                n: row.n_items,
                film: row.film,
                title: `${row.film.title}: ${row.net > 0 ? '+' : ''}${row.net.toFixed(2)} over ${row.n_items} scored items, read from ${row.variant}`,
              }))}
            />
          </section>
        )}

        {fates.length > 0 && (
          <section aria-labelledby="fate">
            <h2 id="fate">What happens to the antagonist</h2>
            <p className="atlas-note">
              Ordered from most retributive to most reparative. A proxy for how a film
              settles accounts — not a score, and not one of the derived axes.
            </p>
            <MagnitudeBars
              caption="Films by what becomes of their antagonist"
              unit=" films"
              labelWidth="170px"
              rows={fates.map((row) => ({ key: row.fate, label: FATE_LABELS[row.fate] || row.fate, value: row.n }))}
            />
          </section>
        )}

        <section aria-labelledby="matrix">
          <h2 id="matrix">Is the antagonist explained?</h2>
          <p className="atlas-note">
            Whether the film supplies a backstory that mitigates — a proxy for whether it
            treats evil as chosen or as inflicted — against what it then does to them.
          </p>
          <div className="matrix" role="table" aria-label="Antagonist backstory against antagonist fate">
            <div role="row" className="matrix-head">
              <span role="columnheader" />
              {matrix.fates.map((fate) => (
                <span role="columnheader" key={fate}>{FATE_LABELS[fate]}</span>
              ))}
            </div>
            {matrix.rows.map((row) => (
              <div role="row" key={String(row.originGiven)}>
                <span role="rowheader">{row.originGiven ? 'Backstory given' : 'No backstory'}</span>
                {row.cells.map((cell) => (
                  <span role="cell" key={cell.fate} className={cell.films.length ? 'filled' : ''}>
                    <b>{cell.films.length || ''}</b>
                    {cell.films.length > 0 && (
                      <em>{cell.films.map((film) => film.title).join(', ')}</em>
                    )}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </section>

        {irony.length > 0 && (
          <section aria-labelledby="irony">
            <h2 id="irony">Depiction is not endorsement</h2>
            <p className="atlas-note">
              A plot summary of <em>Starship Troopers</em> reads as a sincere war picture; the
              film is a satire of one. {irony.length} films were flagged as presenting conduct
              they are actually critiquing — the check a naive reading fails.
            </p>
            <div className="film-grid">
              {irony.map((film) => (
                <button type="button" className="film-card flagged" key={film.id} onClick={() => openFilm(film)}>
                  <strong>{film.title} <span>{film.year}</span></strong>
                  <p>{film.skeleton.endorsement_evidence}</p>
                </button>
              ))}
            </div>
          </section>
        )}

        <section aria-labelledby="every-film">
          <h2 id="every-film">Every film</h2>
          <p className="atlas-note">
            Open any film for its full skeleton — including the fields the model refused to
            claim because it could not ground them in the evidence.
          </p>
          <div className="controls">
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search title or text…"
              aria-label="Search films"
            />
            {FILTERS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`chip ${filter === key ? 'on' : ''}`}
                aria-pressed={filter === key}
                onClick={() => setFilter(key)}
              >
                {label}
              </button>
            ))}
            <span className="count">{visible.length} of {atlas.films.length}</span>
          </div>
          <div className="film-grid">
            {visible.map((film) => (
              <button type="button" className="film-card" key={film.id} onClick={() => openFilm(film)}>
                <strong>{film.title} <span>{film.year}</span></strong>
                <p>{film.skeleton?.legitimacy_source || film.description || 'No skeleton yet.'}</p>
                <small>
                  {film.variant_label || 'not extracted'}
                  {film.skeleton?.antagonist_fate ? ` · ${FATE_LABELS[film.skeleton.antagonist_fate]}` : ''}
                </small>
              </button>
            ))}
          </div>
        </section>

        <section aria-labelledby="conditions">
          <h2 id="conditions">Coverage by evidence condition</h2>
          <p className="atlas-note">
            The same film read four ways. Which evidence a number came from changes what it
            means, so every figure on this page names its condition.
          </p>
          <MagnitudeBars
            caption="Films scored under each evidence condition"
            unit=" films"
            labelWidth="170px"
            rows={scored.map((row) => ({
              key: row.variant,
              label: row.label,
              value: row.films_scored,
              title: `${row.label}: ${row.films_scored} films scored, ${row.scores} scores`,
            }))}
          />
        </section>

        <footer className="atlas-footer">
          <p>
            Generated {new Date(atlas.generated_at).toLocaleString()} · prompt {atlas.prompt_version} ·
            bank {atlas.bank_version} · dimensions {atlas.dim_version}
            {/* Which of the two sources answered. "Live" is read from the store on
                request and is fresh by construction; "published" is a snapshot and
                is only as current as the last `atlas dataset`. Saying which is the
                difference between a stale page and a page that admits it. */}
            {atlas.source === 'published' ? (
              <> · <span className="atlas-source published" title="A snapshot built by `atlas dataset`, not read from the store">
                published snapshot
              </span></>
            ) : atlas.source === 'live' ? (
              <> · <span className="atlas-source live" title="Read from the store on this request">live</span></>
            ) : null}
          </p>
          <p>
            Skeletons are extracted from Wikipedia plot and reception sections and from
            subtitle tracks. The published dataset carries the short quotes each claim is
            grounded in, and no evidence text beyond them.
          </p>
        </footer>
      </div>

      {selected && (
        <div className="detail-scrim" role="presentation" onClick={() => openFilm(null)}>
          <div role="presentation" onClick={(event) => event.stopPropagation()}>
            <FilmDetail film={selected} dimensions={atlas.dimensions} onClose={() => openFilm(null)} />
          </div>
        </div>
      )}
    </main>
  )
}

export default AtlasPage
