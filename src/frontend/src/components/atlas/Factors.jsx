import React from 'react'
import { FactorDistribution, FactorPropositions, FilmAnchors } from './FactorDistribution.jsx'
import { CLEAR_MARGIN, isClear } from '../../services/factorService.js'

const pct = (value) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`

// The scree is the evidence for how MANY axes there are, which is the number
// this whole page used to take on faith. Bars are observed eigenvalues; the
// tick is the 95th percentile of a null built by permuting each item's own
// column, so a factor has to beat the structure the margins give away free.
function Scree({ eigenvalues, thresholds }) {
  const rows = eigenvalues.map((observed, index) => ({
    index: index + 1, observed, threshold: thresholds[index] ?? 0,
  }))
  const ceiling = Math.max(...rows.map((row) => Math.max(row.observed, row.threshold)))

  return (
    <div className="scree">
      {rows.map((row) => {
        const margin = row.threshold ? (row.observed - row.threshold) / row.threshold : 0
        const state = margin <= 0 ? 'below' : margin >= CLEAR_MARGIN ? 'clear' : 'marginal'
        return (
          <div className={`scree-row ${state}`} key={row.index}>
            <span className="scree-index">{row.index}</span>
            <div className="scree-track">
              <i className="scree-bar" style={{ inlineSize: `${(row.observed / ceiling) * 100}%` }} />
              <u className="scree-null" style={{ insetInlineStart: `${(row.threshold / ceiling) * 100}%` }} />
            </div>
            <span className="scree-margin">{pct(margin)}</span>
          </div>
        )
      })}
    </div>
  )
}

function Factor({ factor }) {
  const [open, setOpen] = React.useState(false)
  const clear = isClear(factor)

  return (
    <li className={`factor ${clear ? 'clear' : 'marginal'} ${factor.coherent === false ? 'incoherent' : ''}`}>
      <button type="button" className="factor-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="factor-name">{factor.name}</span>
        <span className="factor-meta">
          {factor.n_items} propositions
          {factor.margin != null && <> · <b>{pct(factor.margin)}</b> over chance</>}
        </span>
      </button>
      <p className="factor-question">{factor.question}</p>

      {factor.coherent === false && (
        <p className="factor-warning">
          The model that named this would not call it coherent: these propositions are
          answered together by the same films without obviously sharing a moral question.
          Kept rather than hidden — a statistical factor that resists naming is a result.
        </p>
      )}

      {open && (
        <div className="factor-detail">
          {/* Denying first, then affirming: the histogram below runs −1 on the
              left to +1 on the right, and a legend in the opposite order to the
              thing it labels makes the reader do the flip themselves. */}
          <p className="factor-pole low">
            <b>−&nbsp;{factor.pole_low_label}</b> {factor.pole_low}
          </p>
          <p className="factor-pole high">
            <b>+&nbsp;{factor.pole_high_label}</b> {factor.pole_high}
          </p>

          <FactorDistribution films={factor.distribution}
                             poleLow={factor.pole_low_label} poleHigh={factor.pole_high_label} />
          <FilmAnchors high={factor.high} low={factor.low}
                       poleHigh={factor.pole_high} poleLow={factor.pole_low}
                       highLabel={factor.pole_high_label} lowLabel={factor.pole_low_label} />

          <p className="factor-examples-label">
            The propositions this factor is made of. Films answered these together —
            that co-movement is the axis; the name above is only a description of it.
          </p>
          <FactorPropositions propositions={factor.propositions} />
        </div>
      )}
    </li>
  )
}

export function Factors({ data }) {
  if (!data) return null
  const named = data.factors || []
  const clear = named.filter(isClear).length

  return (
    <>
      <section aria-labelledby="axes">
        <h2 id="axes">The axes {data.scorer} found</h2>
        <p className="atlas-note">
          Nobody chose these, and nobody chose how many there are. {data.scorer} wrote its own
          bank of moral propositions from {data.films} films&apos; dialogue, scored those films
          against it, and the groupings below are the propositions that the same films answer
          the same way. Only then was the model asked what each group is about — so the names
          are a description of a finished result, not a theory the items were sorted into.
        </p>
        {named.length ? (
          <ul className="factors">
            {named.map((factor) => <Factor key={factor.factor_id} factor={factor} />)}
          </ul>
        ) : (
          <p className="atlas-note">
            Scored, but the axes have not been named yet — run <code>atlas name-factors</code>.
          </p>
        )}
      </section>

      <section aria-labelledby="how-many">
        <h2 id="how-many">Why {data.n_clear_factors}, and not eight?</h2>
        <p className="atlas-note">
          This page used to assert eight axes because a model had been asked for eight, and a
          model asked for eight will always return eight. The count below is the one number
          here that nobody supplied: each factor is kept only if its eigenvalue beats the 95th
          percentile of a null built by permuting each proposition&apos;s own column, which
          destroys the relationships between propositions while leaving each one&apos;s
          engagement rate and affirm/deny balance untouched.
        </p>
        <p className="factor-headline">
          <b>{data.n_factors}</b> clear the null · <b>{clear}</b> clear it by more than {Math.round(CLEAR_MARGIN * 100)}%, which is the bar for appearing here
          <span className="factor-headline-sub">
            {data.films} films × {data.items} propositions
            {data.dropped_items ? `, ${data.dropped_items} dropped as too rarely scored` : ''}
            {' '}· at most {data.max_recoverable} recoverable from this many films
          </span>
        </p>
        <Scree eigenvalues={data.eigenvalues} thresholds={data.null_threshold} />
        <p className="atlas-note">
          Factors within a few percent of the line move between runs as the null is resampled,
          so they are drawn differently and should be read as candidates rather than results.
          One limit this cannot design away: scoring is sparse, so silence counts as a third
          answer — which means two propositions can group because the same films <em>engage</em>
          them, not because those films <em>agree</em> about them. Some of what is measured
          here is salience.
        </p>
      </section>
    </>
  )
}

export default Factors
