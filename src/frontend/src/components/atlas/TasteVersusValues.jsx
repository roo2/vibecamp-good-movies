import React from 'react'
import Fig from './Fig.jsx'

// Where taste and values are held against each other.
//
// This used to sit inside the taste section, which made that section about two
// subjects: what people choose by, and what that does to the values axes. A
// reader who came to read about taste got an argument about values halfway
// down, and a reader who wanted the argument had to find it under a heading
// that did not mention it.
//
// It belongs here instead — behind "Values, taste removed" — because that view
// exists for exactly this question. Everything plotted there is a values
// position with the part taste predicts subtracted out, and this is the
// evidence for why that subtraction is worth doing and what survives it.
export default function TasteVersusValues({ taste }) {
  const found = taste?.findings
  if (!found) return null

  return (
    <section className="taste" aria-labelledby="taste-vs-values">
      <h2 id="taste-vs-values">What taste explains, and what it does not</h2>

      <p>
        The axes on this page are what films <em>argue</em>. They are not what people choose by.
        Shown a film someone rated highly and one they rated poorly, across{' '}
        <Fig from={found} name="ml_raters" /> outside raters:
      </p>

      <table className="figures">
        <thead>
          <tr><th>Ranked by</th><th>One person</th><th>Two people</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>The values axes</td>
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
        Taste accounts for <Fig from={found} name="taste_explains_axis1" suffix="%" /> of the
        leading values axis and almost none of the second. Values account for essentially none
        of any taste dimension. The two spaces share{' '}
        <Fig from={found} name="shared_variance" suffix="%" /> of their variance —{' '}
        <Fig from={found} name="cca" /> against <Fig from={found} name="cca_null" /> on permuted
        films — leaving three quarters of the values signal invisible to preference.
      </p>
      <p>
        Which raises the suspicion that the axes were only ever taste. So every proposition&apos;s
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
        <em>Values cannot rank films because they are orthogonal to taste, and are worth measuring
        for the same reason.</em> The part invisible to preference data still separates lists built
        by Catholics from lists built by Satanists.
      </p>
    </section>
  )
}
