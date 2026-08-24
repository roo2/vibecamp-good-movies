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

function Factor({ factor, scorer }) {
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

          <FactorDistribution films={factor.distribution} scorer={scorer}
                             factorId={factor.factor_id}
                             poleLow={factor.pole_low_label} poleHigh={factor.pole_high_label} />
          <FilmAnchors high={factor.high} low={factor.low} scorer={scorer}
                       factorId={factor.factor_id}
                       poleHigh={factor.pole_high} poleLow={factor.pole_low}
                       highLabel={factor.pole_high_label} lowLabel={factor.pole_low_label} />
          <p className="atlas-note">Tap any film to read the propositions it answered on this axis.</p>

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
  const shown = named.length
  const bar = Math.round((data.display_margin ?? CLEAR_MARGIN) * 100)
  const strict = data.estimator === 'strict'

  // Method first, then results. The derivation used to sit underneath the axes,
  // which asked a reader to judge eleven moral claims and only afterwards told
  // them where the eleven came from — and the heading counted the factors the
  // statistics found rather than the ones this page shows, so it announced a
  // number the list below did not contain.
  return (
    <>
      <section aria-labelledby="how-many">
        <h2 id="how-many">
          {shown === 1 ? 'One axis' : `${shown} axes`}, and where they came from
        </h2>
        <p className="atlas-note">
          Nobody chose these and nobody chose how many there are. {data.scorer} wrote its own
          bank of moral propositions from {data.films} films&apos; dialogue and scored those
          films against it. The groups are the propositions the same films answer the same
          way; the count is whatever survives the test below. Only then was the model asked
          what each group is about — so a name describes a finished result rather than a
          theory the propositions were sorted into.
        </p>

        <p className="factor-headline">
          <b>{data.n_factors}</b> beat chance · <b>{shown}</b> beat it by more than {bar}%,
          and those are the ones shown
          <span className="factor-headline-sub">
            {data.films} films × {data.items} propositions
            {data.dropped_items ? `, ${data.dropped_items} dropped as too rarely scored` : ''}
            {' '}· at most {data.max_recoverable} recoverable from this many films
          </span>
        </p>

        <p className="atlas-note">
          A factor is kept only if its eigenvalue beats the 95th percentile of a null built by
          permuting each proposition&apos;s own column — which destroys the relationships
          between propositions while leaving each one&apos;s engagement rate and affirm/deny
          balance untouched. So it has to explain more than the amount of structure those
          margins hand out for free. {bar}% is a second, editorial bar: a factor a few percent
          clear of chance is real and thin, and printed beside one that cleared by 500% a
          reader weighs them the same.
        </p>

        <Scree eigenvalues={data.eigenvalues} thresholds={data.null_threshold} />

        <p className="atlas-note">
          {strict ? (
            <>
              <b>How silence is handled.</b> A film&apos;s verdict is recorded only for the
              propositions it takes a position on, and these axes are built by correlating two
              propositions over the films that answered <em>both</em> — so agreement is what is
              measured, not which films happen to talk about the same things. Each film is also
              judged against its own rate of agreement, because the scorers say &ldquo;affirms&rdquo;
              far more often than &ldquo;denies&rdquo; and that habit would otherwise be the
              largest pattern in the data. Read the other way, silence counted as an answer and
              the biggest axis turned out to be how talkative a film is.
            </>
          ) : (
            <>
              <b>One limit, stated plainly.</b> Scoring is sparse and silence counts here as a
              third answer, so two propositions can group because the same films <em>engage</em>
              them rather than because those films <em>agree</em> about them. Some of what is
              measured this way is salience rather than stance.
            </>
          )}
        </p>
      </section>

      <section aria-labelledby="axes">
        <h2 id="axes">The axes {data.scorer} found</h2>
        {named.length ? (
          <ul className="factors">
            {named.map((factor) => (
              <Factor key={factor.factor_id} factor={factor} scorer={data.scorer} />
            ))}
          </ul>
        ) : (
          <p className="atlas-note">
            Scored, but the axes have not been named yet — run <code>atlas name-factors</code>.
          </p>
        )}
      </section>
    </>
  )
}

export default Factors
