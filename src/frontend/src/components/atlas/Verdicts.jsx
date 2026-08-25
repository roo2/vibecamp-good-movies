import React from 'react'

// The propositions behind one film's position on one axis.
//
// Shared by the atlas and the film page so a verdict never reads two ways.
//
// The row leads with the EFFECT, not with what the film said. Those come apart:
// a factor holds propositions that contradict each other, so a film can affirm
// a proposition and thereby take the low side of the axis. Showing the word
// "affirms" in the colour that means "subtracts" is accurate and unreadable —
// the eye takes the word and the colour as a contradiction and stops.
//
// So: a signed chip says which way this pushes, coloured to match; the sentence
// follows; and what the film actually said is demoted to the line underneath,
// where it explains the chip rather than competing with it.
export default function Verdicts({ verdicts, poleHigh, poleLow }) {
  if (!verdicts?.length) return null
  const heaviest = Math.max(...verdicts.map((v) => v.weight || 0), 0.0001)

  return (
    <ul className="verdicts">
      {verdicts.map((verdict) => {
        const adds = verdict.points_to === 'high'
        const pole = adds ? poleHigh : poleLow
        return (
          <li key={verdict.item_id} className={adds ? 'adds' : 'subtracts'}>
            <span className="verdict-sign" aria-hidden="true">{adds ? '+' : '−'}</span>
            <span className="verdict-body">
              <span className="verdict-text">{verdict.text}</span>
              <span className="verdict-effect">
                <b>{verdict.emphatic
                  ? (verdict.verdict === 'affirms' ? 'Strongly affirmed' : 'Strongly denied')
                  : (verdict.verdict === 'affirms' ? 'Affirmed' : 'Denied')}</b>
                <i aria-hidden="true">→</i>
                <em>{pole}</em>
                {verdict.reverse_keyed && (
                  <u title="Affirming this proposition means taking the opposite side of the axis from how the sentence reads">
                    reads backwards
                  </u>
                )}
              </span>
              {verdict.weight != null && (
                <span className="verdict-weight"
                      title={`How central this proposition is to the axis (${verdict.weight})`}>
                  <i style={{ inlineSize: `${Math.round((verdict.weight / heaviest) * 100)}%` }} />
                </span>
              )}
              {verdict.evidence && <span className="verdict-evidence">{verdict.evidence}</span>}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
