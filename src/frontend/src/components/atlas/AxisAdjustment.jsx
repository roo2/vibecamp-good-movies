import React from 'react'

// What adjusting for taste did to each axis, and whether each one survives its
// own tests.
//
// This table used to carry hand-entered constants and a hardcoded verdict: the
// third axis was labelled "measured, not plotted" on a person-placement of 0.13
// against a floor of 0.27, under a heading explaining why the plot had two axes
// and not three. Both had stopped being true. The product plots three, and the
// placement test — which recomputes on every build and is what the product
// actually reads — puts that axis at 0.62, the HIGHEST of the three. The page
// whose job is to show the evidence was the last thing to hear it changed.
//
// So the verdict is no longer written here. `places_people` and its two numbers
// come from the reading being displayed, and this component reports them.
//
// `taste_explained` is live per axis too, from the same reading.

// Which reading the coherence and separation figures were measured on. Quoting
// them beside a different bank would attach evidence to axes it was never
// gathered from.
const MEASURED_ON = 'dolphin-subs'

function num(found, key) {
  const f = found?.[key]
  return f ? (f.display ?? f.value) : null
}

export default function AxisAdjustment({ data, taste }) {
  const axes = data?.factors || []
  const found = taste?.findings
  if (!axes.length) return null
  const measured = data?.bank_version === MEASURED_ON
  const anyAdjusted = axes.some((f) => typeof f.taste_explained === 'number')
  const anyPlaced = axes.some((f) => typeof f.places_people === 'boolean')
  if (!anyAdjusted && !anyPlaced) return null
  const dropped = axes.filter((f) => f.places_people === false)

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
            {measured && <th>Own propositions agree</th>}
            {measured && <th>Ideologies separate</th>}
            {anyPlaced && <th>A person can be placed</th>}
          </tr>
        </thead>
        <tbody>
          {axes.map((f, i) => {
            const fails = f.places_people === false
            return (
              <tr key={f.dim_id ?? f.factor_id ?? i} className={fails ? 'axis-dropped' : 'lead'}>
                <td>
                  {f.name}
                  {fails && <small> — measured, not plotted</small>}
                </td>
                <td className="n">
                  {typeof f.taste_explained === 'number'
                    ? `${(f.taste_explained * 100).toFixed(0)}%` : '—'}
                </td>
                {measured && <td className="n">{num(found, `axis${i + 1}_coherence`) ?? '—'}</td>}
                {measured && (
                  <td className="n">
                    {num(found, `axis${i + 1}_separation`)
                      ? `F = ${num(found, `axis${i + 1}_separation`)}` : '—'}
                  </td>
                )}
                {anyPlaced && (
                  <td className="n">
                    {typeof f.person_reliability === 'number'
                      ? `${f.person_reliability.toFixed(2)} / ${f.person_ceiling.toFixed(2)}`
                      : '—'}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>

      {anyPlaced && (
        <p className="atlas-note">
          Placement is read as the figure against its own noise ceiling — the second number, which
          differs by axis because it depends on how many people rated films that axis separates.
          An axis clears when the first exceeds the second.
          {measured && (
            <> Separation is compared against the F that shuffling the films produces,{' '}
              {num(found, 'separation_null') ?? '—'}.</>
          )}
        </p>
      )}

      {dropped.length > 0 && (
        <div className="note open">
          <h3>Why {dropped.length === 1 ? 'an axis is' : 'some axes are'} measured but not plotted</h3>
          <p>
            {dropped.map((f) => f.name).join(', ')} groups propositions that genuinely go together,
            but a person&apos;s position on it cannot be told from noise. A real grouping with no
            demonstrated validity is not a moral dimension. It stays visible here — this is an
            audit page — but nothing is plotted or recommended from it.
          </p>
        </div>
      )}

      {measured && dropped.length === 0 && (
        <div className="note open">
          <h3>All three are plotted, and one of them nearly was not</h3>
          <p>
            Autonomy vs Order was withdrawn once, on an earlier reading where no ideological list
            separated along it and a person could not be placed on it above noise. Under the
            common-factor extraction it passes both — it separates the lists at{' '}
            F = {num(found, 'axis3_separation') ?? '—'} against{' '}
            {num(found, 'separation_null') ?? '—'} from shuffled films, and places a person better
            than either of the other two.
          </p>
          <p className="atlas-note">
            The second axis stays the awkward one, and is published anyway: its propositions are
            the <em>least</em> coherent of the three, yet it separates ideological lists and a
            person can be placed on it. Most likely correctly identified and badly delimited.
          </p>
        </div>
      )}
    </section>
  )
}
