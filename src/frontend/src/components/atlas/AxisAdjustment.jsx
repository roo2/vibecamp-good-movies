import React from 'react'

// What adjusting for taste did to each axis, and why only two are plotted.
//
// The plot draws two axes where it used to draw three, and that is a finding
// rather than a simplification — so the finding has to be on the page beside
// it. Without this block a reader sees a plane, assumes a design decision, and
// never learns that the third axis was tested and failed.
//
// `taste_explained` is live, per axis, from the reading currently selected.
// The three verdicts below are measured constants and are shown only for the
// reading they were measured on; quoting them against a different bank would
// attach evidence to axes it was never gathered from.

// Which reading these were measured on. Quoting them beside a different bank
// would attach evidence to axes it was never gathered from.
const MEASURED_ON = 'dolphin-subs'

function num(found, key) {
  const f = found?.[key]
  return f ? (f.display ?? f.value) : null
}

export default function AxisAdjustment({ data, taste }) {
  const axes = data?.factors || []
  const found = taste?.findings
  if (!axes.length) return null
  const verdicts = data?.bank_version === MEASURED_ON
    ? [1, 2, 3].map((i) => ({
      coherence: num(found, `axis${i}_coherence`),
      separation: num(found, `axis${i}_separation`),
      person: num(found, `axis${i}_person`),
      keep: i < 3,
    }))
    : null
  const anyAdjusted = axes.some((f) => typeof f.taste_explained === 'number')
  if (!anyAdjusted && !verdicts) return null

  return (
    <section className="axis-adjust" aria-labelledby="adjust">
      <h2 id="adjust">The axes, before and after taste is taken out</h2>
      <p>
        Every moral position on this page has had the part predictable from taste removed. How
        much that is differs enormously by axis.
      </p>

      <table className="figures">
        <thead>
          <tr>
            <th>Axis</th>
            <th>Taste explained</th>
            {verdicts && <th>Own propositions agree</th>}
            {verdicts && <th>Ideologies separate</th>}
            {verdicts && <th>A person can be placed</th>}
          </tr>
        </thead>
        <tbody>
          {axes.map((f, i) => {
            const v = verdicts?.[i]
            return (
              <tr key={f.dim_id ?? i} className={v && !v.keep ? 'axis-dropped' : 'lead'}>
                <td>
                  {f.name}
                  {v && !v.keep && <small> — measured, not plotted</small>}
                </td>
                <td className="n">
                  {typeof f.taste_explained === 'number'
                    ? `${(f.taste_explained * 100).toFixed(0)}%` : '—'}
                </td>
                {verdicts && <td className="n">{v?.coherence ?? '—'}</td>}
                {verdicts && <td className="n">{v ? `F = ${v.separation}` : '—'}</td>}
                {verdicts && <td className="n">{v?.person ?? '—'}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>

      {verdicts && (
        <div className="note open">
          <h3>Why the plot has two axes and not three</h3>
          <p>
            It fails three of the four. No ideological list separates along it —
            F = {num(found, 'axis3_separation') ?? '—'}, where shuffling the films produces{' '}
            {num(found, 'separation_null') ?? '—'}. And a person&apos;s position on it cannot be
            told from noise: {num(found, 'axis3_person') ?? '—'} against a floor of{' '}
            {num(found, 'person_floor') ?? '—'}.
          </p>
          <p>
            A real grouping of propositions with no demonstrated validity is not a moral
            dimension. It stays visible here — this is an audit page — but nothing is plotted or
            recommended from it.
          </p>
          <p className="atlas-note">
            The second is awkward and published anyway: its propositions are the <em>least</em>
            coherent of the three, yet it separates ideological lists strongly and a person can be
            placed on it. Most likely correctly identified and badly delimited.
          </p>
        </div>
      )}
    </section>
  )
}
