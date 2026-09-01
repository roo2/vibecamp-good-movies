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

const MEASURED = {
  'dolphin-subs': [
    { coherence: 0.89, separation: 15.9, person: 0.37, keep: true },
    { coherence: 0.29, separation: 5.9, person: 0.31, keep: true },
    { coherence: 0.51, separation: 1.8, person: 0.13, keep: false },
  ],
}

export default function AxisAdjustment({ data }) {
  const axes = data?.factors || []
  if (!axes.length) return null
  const verdicts = MEASURED[data?.bank_version]
  const anyAdjusted = axes.some((f) => typeof f.taste_explained === 'number')
  if (!anyAdjusted && !verdicts) return null

  return (
    <section className="axis-adjust" aria-labelledby="adjust">
      <h2 id="adjust">The axes, before and after taste is taken out</h2>
      <p>
        Every moral position shown on this page has had the part predictable from a
        film&apos;s taste position removed. The raw number confounds two things a reader cannot
        separate by eye — what a film argues, and what kind of film it is — and how much is
        removed differs enormously from one axis to the next.
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
                {verdicts && <td className="n">{v ? v.coherence.toFixed(2) : '—'}</td>}
                {verdicts && <td className="n">{v ? `F = ${v.separation.toFixed(1)}` : '—'}</td>}
                {verdicts && <td className="n">{v ? v.person.toFixed(2) : '—'}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>

      {verdicts && (
        <div className="note open">
          <h3>Why the plot has two axes and not three</h3>
          <p>
            The third fails three of these four tests. Its own propositions agree only weakly.
            No ideological list separates along it — F = 1.8, where shuffling the films produces
            2.0, so it does not clear what chance produces. And a person&apos;s position on it
            cannot be told from noise: 0.13 against a floor of 0.27.
          </p>
          <p>
            It is a real grouping of propositions with no demonstrated validity, which is a
            different thing from a moral dimension. It stays measured and visible here — this is
            an audit page, and an axis that failed is a result — but it is not plotted and
            nothing is recommended from it.
          </p>
          <p className="atlas-note">
            The second is the awkward one and is published anyway: its propositions are the
            <em> least</em> coherent of the three at 0.29, yet it separates ideological lists
            strongly and a person can be placed on it. Most likely it is correctly identified and
            badly delimited.
          </p>
        </div>
      )}
    </section>
  )
}
