import React from 'react'

// The dimensions of taste, and what they did to the moral ones.
//
// This section exists because the honest order of the argument runs through it.
// The moral axes look weak the moment they are asked to predict what anybody
// will enjoy, and a reader who is shown only the axes never finds that out. So
// taste is presented first, at its full strength, and the moral axes are shown
// afterwards surviving having it removed — which is a stronger claim than the
// one this page used to make, and it can only be made in that order.

function pct(x) { return `${(x * 100).toFixed(1)}%` }

export default function TasteDimensions({ taste }) {
  const dims = taste?.dimensions || []
  if (!dims.length) return null
  const named = dims.filter((d) => d.status === 'named')
  const unnamed = dims.filter((d) => d.status === 'unnamed')
  const franchise = dims.filter((d) => d.status === 'franchise')

  return (
    <section className="taste" aria-labelledby="taste">
      <h2 id="taste">What people actually choose by</h2>

      <p>
        The axes above are what films <em>argue</em>. They are not what people choose by, and
        the difference is measurable. Put the same films in front of{' '}
        <b>162,265</b> outside raters and ask a simple question — shown a film someone rated
        highly and one they rated poorly, which is which — and the moral axes answer correctly{' '}
        <b>57%</b> of the time, where 50% is chance. Ranking by which films are liked by the same
        people answers <b>83%</b>.
      </p>

      <div className="taste-how">
        <h3>The dimensions below were found the same way the moral ones were</h3>
        <ol>
          <li>
            <b>Nobody chose them.</b> The same factor analysis is run, but over co-preference
            instead of proposition verdicts — who enjoys what together, rather than what a film
            claims.
          </li>
          <li>
            <b>Only what replicates is kept.</b> The raters are split in half at random and the
            analysis run separately on each. Fourteen dimensions come back the same from both,
            at 0.85 to 1.00. The rest are discarded.
          </li>
          <li>
            <b>Names come last, from evidence.</b> A model shown only film titles produced
            fourteen confident genre labels, and thirteen of them survived no external check.
            So the names below are read off 1,128 human-assigned tags the namer never saw, and
            each is published with the strength of the tag that earned it.
          </li>
        </ol>
      </div>

      <table className="figures taste-table">
        <thead>
          <tr>
            <th>Dimension of taste</th>
            <th>Share of variation</th>
            <th>Replicates</th>
            <th>Evidence</th>
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
        The largest single fact about film taste is <em>how good the film is held to be</em> —
        confirmed twice from data the namer never saw, at −0.67 against IMDb rating and 0.73
        against the tag <em>surprisingly clever</em>. Not one of the fourteen is moral.
      </p>

      {(unnamed.length > 0 || franchise.length > 0) && (
        <div className="note open">
          <h3>Four of these are published without a name, and three are not really dimensions</h3>
          {unnamed.length > 0 && (
            <p>
              <b>{unnamed.length} replicate and cannot be characterised.</b> They come back
              identically from independent halves of 81,000 raters, so they are unambiguously
              something — and neither genre, ratings, era, nor 1,128 human tags can say what,
              topping out at 0.21 to 0.26. They are shown as unnamed rather than given a label
              that would read as knowledge.
            </p>
          )}
          {franchise.length > 0 && (
            <p>
              <b>{franchise.length} are artefacts of a small corpus.</b> A dimension whose
              defining tags are <em>new zealand</em> and <em>tolkien</em> is not a dimension of
              taste, it is one film series. With 546 films and a few large franchises, the
              factorisation finds franchise-shaped structure. These would likely dissolve on a
              larger corpus and nothing should be built on them.
            </p>
          )}
        </div>
      )}

      <h3>What that does to the moral axes — and what it does not</h3>
      <p>
        Taste accounts for <b>21%</b> of the leading moral axis and about 3% of the second.
        Morality accounts for essentially none of any taste dimension. Allowing combinations
        rather than single pairs, the two spaces share <b>26%</b> of their variance — real, well
        clear of the 20% that permuted films produce, and still leaving three quarters of the
        moral signal invisible to preference.
      </p>
      <p>
        Which raises the obvious suspicion: were the moral axes ever anything but taste, reached
        by a longer route? That is testable. Every proposition's verdicts were replaced with what
        remains after its taste position is subtracted, and the whole discovery procedure was run
        again from those residuals, free to produce a different answer. The propositions did
        regroup substantially. The axes reassembled anyway.
      </p>

      <table className="figures">
        <thead>
          <tr>
            <th>Rebuilt with taste removed, it lands where the original landed</th>
            <th>Deterministic pessimism</th>
            <th>Divine order</th>
          </tr>
        </thead>
        <tbody>
          <tr className="lead">
            <td>Redemptive hope <i aria-hidden="true">↔</i> Deterministic retribution</td>
            <td className="n">0.81</td><td className="n">0.11</td>
          </tr>
          <tr className="lead">
            <td>Inherited order <i aria-hidden="true">↔</i> Self-determination</td>
            <td className="n">0.15</td><td className="n">0.58</td>
          </tr>
          <tr>
            <td><em>shuffled films, for comparison</em></td>
            <td className="n">0.03</td><td className="n">0.03</td>
          </tr>
        </tbody>
      </table>

      <p>
        The names came back independently and so did the film placements. That distinction is the
        whole thing: this project has already been caught once believing two readings had
        replicated because their <em>names</em> matched, when their film positions correlated 0.11
        to 0.22 against a floor of 0.07. Here both agree, against a shuffled floor of 0.08.
      </p>
      <p className="taste-conclusion">
        So the two results are one result. <em>Morality cannot rank films because it is orthogonal
        to taste, and morality is worth measuring because it is orthogonal to taste.</em> Four
        fifths of the leading axis is invisible to preference data — and that invisible part still
        separates lists built by Catholics from lists built by Satanists.
      </p>
    </section>
  )
}
