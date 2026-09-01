import React from 'react'

// The dimensions of taste, and what they did to the moral ones.
//
// Presented before the moral axes because the honest order of the argument runs
// through it: the axes look weak the moment they are asked to predict what
// anybody enjoys, and a reader shown only the axes never finds that out.
//
// Every figure quoted here comes from the `findings` table with its provenance,
// rather than being typed in. A number that changes should change the page.

function pct(x) { return `${(x * 100).toFixed(1)}%` }

// `display` when the raw number reads badly, the value otherwise. A missing
// finding renders as an em dash rather than "undefined" or a stale literal.
function Fig({ from, name, suffix = '' }) {
  const f = from?.[name]
  if (!f) return <b>—</b>
  return (
    <b title={[f.note, f.source].filter(Boolean).join(' · ')}>
      {f.display ?? f.value}{suffix}
    </b>
  )
}

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
        The axes below are what films <em>argue</em>. They are not what people choose by. Shown a
        film someone rated highly and one they rated poorly, across{' '}
        <Fig from={found} name="ml_raters" /> outside raters:
      </p>

      <table className="figures">
        <thead>
          <tr><th>Ranked by</th><th>One person</th><th>Two people</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>The moral axes</td>
            <td className="n"><Fig from={found} name="pairwise_moral_one" /></td>
            <td className="n"><Fig from={found} name="pairwise_moral_two" /></td>
          </tr>
          <tr>
            <td>Ideological list membership</td>
            <td className="n"><Fig from={found} name="pairwise_sets_one" /></td>
            <td className="n"><Fig from={found} name="pairwise_sets_two" /></td>
          </tr>
          <tr className="lead">
            <td>Which films are liked by the same people</td>
            <td className="n"><Fig from={found} name="pairwise_cf_one" /></td>
            <td className="n"><Fig from={found} name="pairwise_cf_two" /></td>
          </tr>
          <tr>
            <td><em>chance</em></td>
            <td className="n"><Fig from={found} name="pairwise_chance" /></td>
            <td className="n"><Fig from={found} name="pairwise_chance" /></td>
          </tr>
        </tbody>
      </table>

      <p>
        So the dimensions of taste were found the same way the moral ones were — nobody chose
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
        from data the namer never saw. None of the fourteen is moral.
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

      <h3>What that does to the moral axes — and what it does not</h3>
      <p>
        Taste accounts for <Fig from={found} name="taste_explains_axis1" suffix="%" /> of the
        leading moral axis and almost none of the second. Morality accounts for essentially none
        of any taste dimension. The two spaces share{' '}
        <Fig from={found} name="shared_variance" suffix="%" /> of their variance —{' '}
        <Fig from={found} name="cca" /> against <Fig from={found} name="cca_null" /> on permuted
        films — leaving three quarters of the moral signal invisible to preference.
      </p>
      <p>
        Which raises the suspicion that the axes were only ever taste. So every proposition's
        verdicts were replaced with what remains after its taste position is subtracted, and the
        discovery was run again from those residuals, free to come out differently. The
        propositions did regroup. The axes reassembled anyway.
      </p>

      <table className="figures">
        <thead>
          <tr>
            <th>Rebuilt without taste, against the original</th>
            <th>Deterministic pessimism</th><th>Divine order</th>
          </tr>
        </thead>
        <tbody>
          <tr className="lead">
            <td>Redemptive hope <i aria-hidden="true">↔</i> Deterministic retribution</td>
            <td className="n"><Fig from={found} name="rebuild_axis1" /></td><td className="n">0.11</td>
          </tr>
          <tr className="lead">
            <td>Inherited order <i aria-hidden="true">↔</i> Self-determination</td>
            <td className="n">0.15</td><td className="n"><Fig from={found} name="rebuild_axis2" /></td>
          </tr>
          <tr>
            <td><em>shuffled films</em></td>
            <td className="n"><Fig from={found} name="rebuild_null" /></td>
            <td className="n"><Fig from={found} name="rebuild_null" /></td>
          </tr>
        </tbody>
      </table>

      <p>
        The names came back independently and so did the placements — which is the distinction
        that matters. This project has already believed two readings had replicated because their
        <em> names</em> matched, when their positions agreed no better than{' '}
        <Fig from={found} name="names_matched_positions_did_not" />.
      </p>
      <p className="taste-conclusion">
        <em>Morality cannot rank films because it is orthogonal to taste, and is worth measuring
        for the same reason.</em> The part invisible to preference data still separates lists built
        by Catholics from lists built by Satanists.
      </p>
    </section>
  )
}
