import React from 'react'

// The rest of the page assumes eight axes, because eight is what the deriving
// prompt was asked for — the Reduction note says so itself, and calls that the
// step to be suspicious of. This section is the answer to that suspicion: the
// only number here that was not supplied by anybody.
//
// A factor is kept when its eigenvalue beats the 95th percentile of a null built
// by permuting each item's own column, which destroys the relationships between
// items while leaving each item's engagement rate and affirm/deny balance
// untouched. So "more structure than a random matrix of exactly this shape and
// these margins" is the bar.

const pctMargin = (value) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`

// Below this a retained factor is technically above the line and practically on
// it — on the 40-film corpus the last three move between runs as the null is
// resampled, so presenting them like the leading factors would overstate them.
const CLEAR_MARGIN = 0.05

function Scree({ report }) {
  const rows = report.eigenvalues.map((observed, index) => ({
    index: index + 1,
    observed,
    threshold: report.null_threshold[index],
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
              {/* The null is a line rather than a second bar: it is a threshold
                  to clear, not a quantity to compare lengths with. */}
              <u className="scree-null" style={{ insetInlineStart: `${(row.threshold / ceiling) * 100}%` }} />
            </div>
            <span className="scree-margin">{pctMargin(margin)}</span>
          </div>
        )
      })}
    </div>
  )
}

export function Dimensionality({ dimensionality }) {
  if (!dimensionality?.available) return null
  const reports = dimensionality.scorers || []
  const primary = reports[0]
  const convergence = dimensionality.convergence

  return (
    <section aria-labelledby="how-many">
      <h2 id="how-many">How many dimensions are there, really?</h2>
      <p className="atlas-note">
        Every other number on this page takes eight axes as given, because eight is what the
        deriving prompt asked for — a model asked for eight will always return eight. This is
        the one section where the count is a result. It ignores the axes entirely and reads
        only how films responded to items: propositions that the same films answer the same way
        are being driven by the same underlying thing.
      </p>

      {reports.map((report) => {
        const clear = report.n_clear_factors
        return (
          <div className="dimensionality-card" key={report.scorer}>
            <header>
              <strong>{report.scorer}</strong>
              <span>
                {report.films} films × {report.items} items
                {report.dropped_items ? ` · ${report.dropped_items} items dropped as too rarely scored` : ''}
              </span>
            </header>
            <p className="dimensionality-headline">
              <b>{report.n_factors}</b> factors clear the null;{' '}
              <b>{clear}</b> clear it by more than 5%.
            </p>
            <Scree report={report} />
            <p className="atlas-note">
              Bars are the observed eigenvalues, the tick is the 95th percentile of the null,
              and the figure on the right is how far each factor clears it.{' '}
              {report.films < 100 ? (
                <>
                  With only {report.films} films against {report.items} items the matrix has rank
                  at most {report.max_recoverable}, so this is an estimate with wide uncertainty:
                  the factors sitting within a few percent of the line move between runs as the
                  null is resampled. Eight is inside the supported range — which means the
                  prompt&apos;s answer is not contradicted, and also not confirmed.
                </>
              ) : (
                <>
                  At {report.films} films the estimate is no longer starved of respondents, so
                  the factors clearing by a wide margin are the ones worth reading as real.
                </>
              )}
            </p>
          </div>
        )
      })}

      {convergence && (
        <div className="dimensionality-card">
          <header><strong>Do independent scorers agree?</strong></header>
          <p className="dimensionality-headline">
            {Object.entries(convergence.counts).map(([scorer, count]) => (
              <span key={scorer} className="count-chip">{scorer}: <b>{count}</b></span>
            ))}
          </p>
          <p className="atlas-note">
            {convergence.same_count
              ? 'They land on the same count.'
              : `They differ by ${convergence.spread}.`}{' '}
            Agreeing on the number is not the same as agreeing on the grouping — two scorers can
            both say eight and cut the material completely differently — so the grouping is
            compared separately, by adjusted Rand index, which scores about zero for two
            unrelated partitions of the same shape.
          </p>
          <table className="atlas-table">
            <thead>
              <tr><th>pair</th><th>items</th><th>ARI</th><th>NMI</th><th>chance</th></tr>
            </thead>
            <tbody>
              {Object.entries(convergence.grouping_agreement).map(([pair, row]) => (
                <tr key={pair}>
                  <td>{pair}</td>
                  <td>{row.n_items}</td>
                  <td><b>{row.ari?.toFixed(3)}</b></td>
                  <td>{row.nmi?.toFixed(3)}</td>
                  <td>{row.chance?.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {primary && (
        <p className="atlas-note">
          One caveat this section cannot design away. Scoring is sparse — a verdict is recorded
          only where a film takes a position — and on this corpus {' '}
          most pairs of items share no film at all. Silence is therefore kept as a third value
          rather than treated as missing, which makes the arithmetic well posed but means two
          items can look related because the same films <em>engage</em> them, not because those
          films <em>agree</em> about them. Some of what is measured here is salience.
        </p>
      )}
    </section>
  )
}

export default Dimensionality
