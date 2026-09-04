import React from 'react'
import TasteDimensions from '../components/atlas/TasteDimensions.jsx'
import { loadTaste } from '../services/factorService.js'

// Taste, on its own page.
//
// It used to open the atlas, on the argument that a reader who meets the moral
// axes first is shown the answer without the thing it has to survive. That
// argument is still right and the placement was still wrong: the atlas is about
// what films ARGUE, and half a screen of preference data before the first axis
// made the page about two subjects and led with the weaker one. The comparison
// belongs somewhere a reader goes on purpose.
//
// What is added here beyond what the atlas carried: every dimension rather than
// the named ones, the figure that decides which get shown in a profile, and the
// films at each pole — which is the only part of this a reader can check against
// their own knowledge of the films.

const SHOWN_IN_PROFILE = 5

function pct(x) { return `${(x * 100).toFixed(1)}%` }

// The four films furthest along a dimension, each way. Positions come from the
// same payload the plot uses, so a film named here is a film the plot places.
function poles(films, dimId, take = 4) {
  const rows = films
    .map((f) => ({ title: f.title, at: f.position?.[String(dimId)] }))
    .filter((f) => typeof f.at === 'number')
    .sort((a, b) => b.at - a.at)
  return { high: rows.slice(0, take), low: rows.slice(-take).reverse() }
}

export default function TastePage({ onBack, onAtlas }) {
  const [taste, setTaste] = React.useState(null)
  const [error, setError] = React.useState(null)

  React.useEffect(() => {
    let live = true
    loadTaste()
      .then((t) => live && setTaste(t))
      .catch(() => live && setError('The taste dimensions could not be loaded.'))
    return () => { live = false }
  }, [])

  const dims = taste?.dimensions || []
  // Ordered as a profile orders them: by how reliably each places a PERSON from
  // the dozen or so films they rated, not by how much of the corpus it covers.
  // The two orderings disagree, and the disagreement is the point of the table.
  const byReadability = [...dims].sort(
    (a, b) => (b.profile_reliability ?? 0) - (a.profile_reliability ?? 0))
  const named = byReadability.filter((d) => d.status === 'named')

  return (
    <main className="atlas-page">
      <div className="atlas-wrap">
      <header className="atlas-header">
        {onBack && <button type="button" className="back-button" onClick={onBack}>←</button>}
        <div>
          <h1>What kind of film do people choose?</h1>
          <p className="atlas-note">
            A second set of dimensions, found the same way as the moral ones but from a different
            question: not what a film argues, but which films the same people enjoy. Derived from
            162,000 outside raters who never saw any of this.
          </p>
          <p className="atlas-note">
            It is here as the comparison the moral axes have to survive — and they do not survive
            it in the way you would expect.{' '}
            {onAtlas && (
              <button type="button" className="link-button" onClick={onAtlas}>
                The moral axes are on the atlas →
              </button>
            )}
          </p>
        </div>
      </header>

      {error && <section><p className="atlas-note">{error}</p></section>}
      {!taste && !error && <section><p className="message">Reading the dimensions…</p></section>}

      {taste && (
        <>
          <TasteDimensions taste={taste} />

          <section className="taste">
            <h2>Every dimension, and which of them a profile can use</h2>
            <p>
              Sixteen dimensions replicate across independent halves of the raters. Six can be
              named. That is not the same question as which are worth showing somebody about
              themselves — a dimension can be large in the corpus and still fail to place a person
              who has rated a dozen films, because people barely differ on it.
            </p>
            <p>
              <b>Places a person</b> is measured directly: split a rater&apos;s films in two, place
              them from each half, and correlate the two placements across raters. The top{' '}
              {SHOWN_IN_PROFILE} are what a profile shows, and they are not the largest{' '}
              {SHOWN_IN_PROFILE}.
            </p>

            <div className="scroll">
              <table className="figures taste-table">
                <thead>
                  <tr>
                    <th>Dimension</th><th>Places a person</th><th>Variation</th>
                    <th>Replicates</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {byReadability.map((d, i) => (
                    <tr key={d.dim_id} className={i < SHOWN_IN_PROFILE ? 'lead' : undefined}>
                      <td>
                        {d.status === 'unnamed'
                          ? <em>unnamed</em>
                          : <>{d.pole_low} <i aria-hidden="true">↔</i> {d.pole_high}</>}
                        {i < SHOWN_IN_PROFILE && <small className="taste-tags">shown in profiles</small>}
                      </td>
                      <td className="n">
                        {typeof d.profile_reliability === 'number'
                          ? d.profile_reliability.toFixed(2) : '—'}
                      </td>
                      <td className="n">{pct(d.variance)}</td>
                      <td className="n">{d.replication.toFixed(2)}</td>
                      <td className="n">{d.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="atlas-note">
              The break falls after the fifth: those place a person between 0.41 and 0.51, and the
              sixth drops to 0.25. A row for that one would be a confident reading of noise, which
              is the only kind of row worth cutting.
            </p>
          </section>

          <section className="taste">
            <h2>The films at each end</h2>
            <p>
              Nothing above can be checked by eye. This can: for each named dimension, the films
              the data puts furthest along it, in both directions. The names were written from
              1,128 human-assigned tags and never from titles — so if the titles look right, that
              is a check the naming could have failed.
            </p>
            {named.map((d) => {
              const { high, low } = poles(taste.films || [], d.dim_id)
              return (
                <div className="taste-poles" key={d.dim_id}>
                  <h3>{d.pole_low} <i aria-hidden="true">↔</i> {d.pole_high}</h3>
                  <div className="taste-poles-row">
                    <div>
                      <span className="taste-pole-label">{d.pole_low}</span>
                      <ul>{low.map((f) => <li key={f.title}>{f.title}</li>)}</ul>
                    </div>
                    <div>
                      <span className="taste-pole-label">{d.pole_high}</span>
                      <ul>{high.map((f) => <li key={f.title}>{f.title}</li>)}</ul>
                    </div>
                  </div>
                </div>
              )
            })}
          </section>
        </>
      )}
      </div>
    </main>
  )
}
