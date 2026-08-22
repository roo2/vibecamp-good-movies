import React from 'react'

const pct = (value) => (value == null ? '—' : `${(value * 100).toFixed(0)}%`)
const num = (value, dp = 3) => (value == null ? '—' : value.toFixed(dp))

// The reduction is the claim: several hundred separate moral statements turn out
// to be a handful of questions asked repeatedly. Showing it as a funnel means
// showing what was dropped at each step, which is the part a reader should be
// suspicious about.
export function Reduction({ reduction, dimensions }) {
  if (!reduction?.stages?.length) return null
  const stages = reduction.stages
  const widest = Math.max(...stages.map((stage) => stage.n))
  const smallest = Math.min(...dimensions.map((d) => d.n_items))
  const largest = Math.max(...dimensions.map((d) => d.n_items))

  return (
    <>
      <ol className="funnel">
        {stages.map((stage, index) => (
          <li key={stage.key}>
            <span className="funnel-rank">{index + 1}</span>
            <div className="funnel-body">
              <strong>{stage.n.toLocaleString()}</strong>
              <b>{stage.label}</b>
              <span>{stage.detail}</span>
            </div>
            {/* Width is share of the largest stage — a rough sense of scale, and
                deliberately not a log axis, which would flatter the collapse. */}
            <div className="funnel-bar" aria-hidden="true">
              <i style={{ inlineSize: `${Math.max(2, (stage.n / widest) * 100)}%` }} />
            </div>
          </li>
        ))}
      </ol>
      <p className="atlas-note funnel-note">
        Between the second step and the third sit {reduction.scored?.toLocaleString()} scored
        verdicts — every film against every item it engages — which are not a step in the
        reduction but are what makes it checkable, because they were recorded before the axes
        existed. The last step is the one worth being suspicious of: an LLM asked for eight
        moral dimensions will always return eight moral dimensions. That is why the axes are
        not presented as a finding on their own, and why everything under “Does this hold up?”
        exists to attack them. The axes come out uneven — {largest} items on the largest
        against {smallest} on the smallest — which is what it looks like when the shape is
        read off the corpus rather than imposed evenly.
      </p>
    </>
  )
}

// Three independent attempts to knock the axes down. A reader should be able to
// see the weakest number as easily as the strongest, so nothing here is
// summarised into a verdict.
export function Reliability({ reliability, dimensions, splitHalf }) {
  if (!reliability) {
    return (
      <p className="atlas-note">
        The axes have not been validated in this store yet — run
        {' '}<code>atlas dimensions-validate</code>.
      </p>
    )
  }

  return (
    <>
      <h3 className="sub-head">1 · The same items, assigned again, blind</h3>
      <p className="atlas-note">
        A sample of the bank was put back through assignment as if it had never been seen.
        Cohen’s κ prices in agreement that would happen by chance anyway — raw agreement
        flatters any labelling with one dominant category, which is the failure mode here.
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Run</th><th scope="col">Model</th>
              <th scope="col">Items</th><th scope="col">Same axis</th>
              <th scope="col">By chance</th><th scope="col">Cohen’s κ</th>
              <th scope="col">Same polarity</th>
            </tr>
          </thead>
          <tbody>
            {reliability.passes.map((pass) => (
              <tr key={pass.pass}>
                <th scope="row">{pass.pass}</th>
                <td>{pass.model || '—'}</td>
                <td className="n">{pass.n}</td>
                <td className="n">{pct(pass.raw)}</td>
                <td className="n muted">{pct(pass.chance)}</td>
                <td className="n"><b>{num(pass.kappa, 2)}</b></td>
                <td className="n">{pct(pass.polarity_agreement)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="table-note">
        κ above 0.8 is conventionally read as strong agreement. Polarity is the harder
        test: it asks not just which axis a statement belongs to but which way it points.
      </p>

      <h3 className="sub-head">2 · Against verdicts that predate the axes</h3>
      <p className="atlas-note">
        Every film was scored against the bank <em>before</em> the axes existed, so those
        verdicts cannot have been shaped to fit them. Both tests compare the real grouping
        against {reliability.tests[0]?.permutations.toLocaleString() ?? '1,000'} random
        regroupings that keep the axis sizes identical — the null is “these items were
        sorted arbitrarily”. Own-film verdicts are excluded, so no film votes on a
        statement harvested from itself.
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Test</th><th scope="col">What a high value means</th>
              <th scope="col">Observed</th><th scope="col">Random regroupings</th>
              <th scope="col">z</th><th scope="col">Beat it</th>
            </tr>
          </thead>
          <tbody>
            {reliability.tests.map((test) => (
              <tr key={test.key}>
                <th scope="row">{test.label}</th>
                <td className="reads">{test.reads}</td>
                <td className="n"><b>{num(test.observed)}</b></td>
                <td className="n muted">{num(test.null_mean)} ± {num(test.null_sd)}</td>
                <td className="n"><b>{test.z == null ? '—' : `${test.z > 0 ? '+' : ''}${test.z.toFixed(1)}`}</b></td>
                <td className="n">{test.n_at_least_observed}/{test.permutations.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="table-note">
        Read over {reliability.n_engagements?.toLocaleString()} engagements across
        {' '}{reliability.n_packets} film–condition packets. “Beat it” counts how many random
        regroupings scored at least as well as the real one; zero of a thousand is the
        strongest statement this test can make, and it is not the same as a probability of
        zero. Seed {reliability.seed}, so these numbers reproduce exactly.
      </p>

      <h3 className="sub-head">3 · Axis by axis</h3>
      <p className="atlas-note">
        An aggregate can look healthy while one axis quietly does all the work, so each is
        reported on its own. Fit is the assigner’s own confidence that an item belongs
        where it put it.
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Axis</th><th scope="col">Items</th>
              <th scope="col">Median fit</th><th scope="col">Re-checked</th>
              <th scope="col">Same axis</th><th scope="col">Same polarity</th>
            </tr>
          </thead>
          <tbody>
            {dimensions.map((dim) => {
              const a = dim.agreement || {}
              const weak = a.same_axis != null && a.same_axis < 0.75
              return (
                <tr key={dim.dim_id}>
                  <th scope="row">{dim.name}</th>
                  <td className="n">{a.n_items ?? dim.n_items}</td>
                  <td className="n">{a.median_fit ?? '—'}</td>
                  <td className="n muted">{a.rechecked ?? 0}</td>
                  <td className={`n${weak ? ' weak' : ''}`}>{pct(a.same_axis)}</td>
                  <td className="n">{pct(a.same_polarity)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="table-note">
        The weakest row is the honest one to look at first: axes re-checked on only a
        handful of items carry the least evidence, and a low “same axis” there means the
        boundary with a neighbouring axis is genuinely blurred rather than that the axis
        is wrong.
      </p>

      {splitHalf && (
        <>
          <h3 className="sub-head">4 · Derived twice, from halves that share nothing</h3>
          <p className="atlas-note">
            The corpus was split into two film sets with no propositions in common
            ({splitHalf.half_a_films} films and {splitHalf.half_b_films}), and eight axes
            were derived from each independently. If the axes came from the prompt rather
            than the corpus, the two lists would still both have eight entries — but they
            would not keep landing on the same questions.
          </p>
          <div className="halves">
            <div>
              <span className="eyebrow">Half A · {splitHalf.half_a_films} films</span>
              <ol>{splitHalf.half_a.map((axis) => <li key={axis.dim_id}>{axis.name}</li>)}</ol>
            </div>
            <div>
              <span className="eyebrow">Half B · {splitHalf.half_b_films} films</span>
              <ol>{splitHalf.half_b.map((axis) => <li key={axis.dim_id}>{axis.name}</li>)}</ol>
            </div>
          </div>
          <p className="table-note">
            No correlation is quoted here on purpose. Whether “Punishment versus mercy” and
            “Payback Versus Mercy” are the same axis is a judgement about meaning, and a
            number put on that judgement would look like evidence without being any. The
            two lists are side by side so the reader makes that call themselves.
          </p>
        </>
      )}
    </>
  )
}
