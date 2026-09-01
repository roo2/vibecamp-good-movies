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

function Factor({ factor, reading }) {
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
          The namer would not call this coherent: the same films answer these together with no obvious shared question. Kept, not hidden — that is a result.
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

          <FactorDistribution films={factor.distribution} reading={reading}
                             factorId={factor.factor_id}
                             poleLow={factor.pole_low_label} poleHigh={factor.pole_high_label} />
          <FilmAnchors high={factor.high} low={factor.low} reading={reading}
                       factorId={factor.factor_id}
                       poleHigh={factor.pole_high} poleLow={factor.pole_low}
                       highLabel={factor.pole_high_label} lowLabel={factor.pole_low_label} />
          <p className="atlas-note">Tap any film to read the propositions it answered on this axis.</p>

          <p className="factor-examples-label">
            The propositions this axis is made of. Films answered them together — that is the axis. The name is only a description.
          </p>
          <FactorPropositions propositions={factor.propositions}
                              poleHigh={factor.pole_high_label}
                              poleLow={factor.pole_low_label} />
        </div>
      )}
    </li>
  )
}

export function Factors({ data }) {
  if (!data) return null
  const named = data.factors || []
  const shown = named.length
  const bar = Math.round((data.margin_floor ?? CLEAR_MARGIN) * 100)

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
          Nobody chose these, or how many. {data.scorer} wrote its own propositions from{' '}
          {data.films} films&apos; dialogue and scored the films against them; a group is the
          propositions the same films answer the same way. Names came last, so each describes a
          finished result rather than a theory the propositions were sorted into.
        </p>

        <p className="factor-headline">
          <b>{shown}</b> {shown === 1 ? 'factor beats' : 'factors beat'} chance by more
          than {bar}%, and all of them are here
          <span className="factor-headline-sub">
            {data.films} films × {data.items} propositions
            {data.unanimous_items
              ? `, after ${data.unanimous_items} every film agreed with were set aside`
              : ''}
            {' '}· at most {data.max_recoverable} recoverable from this many films
          </span>
        </p>

        {!!data.unanimous_items && (
          <p className="atlas-note">
            <b>Propositions every film agrees with are set aside first</b> —{' '}
            {data.unanimous_items} here. A claim nobody argues with cannot tell two films apart,
            and worse, invents a dimension: each film is judged against its own affirm rate, which
            turns a unanimously affirmed item into a negated copy of how agreeable that film is.
            Those items correlated −1.00 with affirm rate and carried three times the weight of
            everything else. Removing them cut 20 axes to {shown} and made what remains more
            reproducible, not less.
          </p>
        )}

        {!!(data.replication || []).length && (
          <>
            <p className="atlas-note">
              <b>Beating chance is not the same as being real.</b> The test below asks whether a
              factor beats what the margins give away free in <em>this</em> corpus. A stricter test: split the films in half at random and run the analysis separately on each. Most factors pass the first test and fail this one.
            </p>
            <ul className="replication">
              {data.replication.map((row) => (
                <li key={row.k}>
                  <b>{row.overlap.toFixed(2)}</b>
                  <span>
                    {row.k === 1 ? 'the strongest factor alone'
                      : `the strongest ${row.k} together`}
                  </span>
                  <i>chance {row.chance.toFixed(3)}</i>
                </li>
              ))}
            </ul>
            <p className="atlas-note">
              1.00 would mean the two halves found the same thing exactly. The first factor is
              the one that clearly survives; by the third the halves are agreeing much less,
              which is why the compass shows three axes and not all {shown}. This is a lower
              bound — each half has half the films, and the estimator weakens as films are
              removed — so read the gap from chance rather than the number itself.
            </p>
          </>
        )}

        <p className="atlas-note">
          A factor is kept only if it beats the 95th percentile of a null that shuffles each proposition&apos;s own answers, leaving how often it is engaged and affirmed untouched. So it has to explain more than the margins hand out free. Everything that passes is here; the app shows only the strongest few.
        </p>

        <Scree eigenvalues={data.eigenvalues} thresholds={data.null_threshold} />

        <p className="atlas-note">
          <b>How silence is handled.</b> A film&apos;s verdict is recorded only for the
          propositions it takes a position on, and two propositions are compared over the
          films that answered <em>both</em> — so what is measured is agreement, not which films raise the same subjects. Each film is judged against its own affirm rate too: the scorers say &ldquo;affirms&rdquo; far more often than &ldquo;denies&rdquo;. Counting silence as an answer instead made the biggest axis how talkative a film is.
        </p>
        <p className="atlas-note">
          <b>Where this is weakest.</b> This holds while silence is a property of films — some argue about more things than others — rather than scattered at random. An assumption the count rests on, not something it proves.
        </p>
      </section>

      <section aria-labelledby="axes">
        <h2 id="axes">The axes {data.scorer} found</h2>
        {named.length ? (
          <ul className="factors">
            {named.map((factor) => (
              <Factor key={factor.factor_id} factor={factor}
                      reading={{ scorer: data.scorer, variant: data.variant,
                                 bank_version: data.bank_version }} />
            ))}
          </ul>
        ) : (
          // Nothing found is a result, and it has a cause worth printing. The old
          // message here guessed that the naming step had not been run, which for
          // a scorer that HAS been through it reads as a missing chore rather
          // than as the finding it is.
          <p className="atlas-note">
            <b>No axes.</b> Nothing {data.scorer} produced beat chance, so there is nothing to
            name. It scored {data.films} films but engaged only {data.items} propositions —{' '}
            {Math.round(data.density * 100)}% of the grid — and two propositions can only be
            compared over the films that answered both. At this density most pairs share barely
            a film, so there is almost nothing to correlate. That is a shortage of scoring
            rather than a verdict on the model&apos;s opinions.
          </p>
        )}
      </section>
    </>
  )
}

export default Factors
