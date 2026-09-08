import React from 'react'
import Fig from './Fig.jsx'

// The dimensions of taste: what they are, how they were found, and which of
// them can be named.
//
// Taste ALONE. Everything holding it against the values axes — what predicts a
// person's preference, how much of an axis taste explains, what survives having
// it subtracted — moved to `TasteVersusValues`, behind the view that exists for
// that question. This section had been about two subjects, and the second one
// arrived halfway down under a heading that did not mention it.

function pct(x) { return `${(x * 100).toFixed(1)}%` }

export default function TasteDimensions({ taste }) {
  const dims = taste?.dimensions || []
  const found = taste?.findings
  if (!dims.length) return null
  const named = dims.filter((d) => d.status === 'named')
  const unnamed = dims.filter((d) => d.status === 'unnamed')
  const franchise = dims.filter((d) => d.status === 'franchise')

  return (
    <section className="taste" aria-labelledby="taste">
      <h2 id="taste">What people actually choose by</h2>

      <p>
        The dimensions of taste were found the same way the values axes were — nobody chose
        them, only what came back from independent halves of the raters was kept (
        <Fig from={found} name="replication_floor" /> and above), and names came last, from{' '}
        <Fig from={found} name="tag_vocab" /> human-assigned tags rather than from film titles.
        A model shown titles alone produced fourteen confident genre labels; thirteen survived no
        external check.
      </p>

      <table className="figures taste-table">
        <thead>
          <tr>
            <th>Dimension of taste</th><th>Variation</th><th>Replicates</th><th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {named.map((d, i) => (
            <tr key={d.dim_id} className={i === 0 ? 'lead' : undefined}>
              <td>
                {d.pole_high} <i aria-hidden="true">↔</i> {d.pole_low}
                <small className="taste-tags">{d.tags_high.slice(0, 3).join(', ')}</small>
              </td>
              <td className="n">{pct(d.variance)}</td>
              <td className="n">{d.replication.toFixed(2)}</td>
              <td className="n">{d.evidence.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="taste-lead-note">
        The largest fact about film taste is how good the film is held to be —{' '}
        <Fig from={found} name="quality_vs_imdb" /> against IMDb rating and{' '}
        <Fig from={found} name="quality_vs_tag" /> against the tag <em>surprisingly clever</em>,
        from data the namer never saw. None of the fourteen is about values.
      </p>

      {(unnamed.length > 0 || franchise.length > 0) && (
        <p className="atlas-note">
          {unnamed.length > 0 && <>
            <b>{unnamed.length} replicate and cannot be named.</b> No instrument tried — genre,
            ratings, era, {' '}<Fig from={found} name="tag_vocab" /> tags — characterises them.
            Published unnamed rather than labelled.{' '}
          </>}
          {franchise.length > 0 && <>
            <b>{franchise.length} are franchise artefacts.</b> A dimension whose defining tags are{' '}
            <em>new zealand</em> and <em>tolkien</em> is one film series, not a dimension of taste.
          </>}
        </p>
      )}

    </section>
  )
}
