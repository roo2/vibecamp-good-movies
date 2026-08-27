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
// Sixty-five propositions is a lot to meet at once, and the ones that matter
// are at the top — this is sorted by weight. So the heaviest dozen show, and the
// rest are one click away rather than absent: a reader working out why a score
// is lower than the visible propositions suggest needs the tail, and everyone
// else does not.
const HEAVIEST = 12

export default function Verdicts({ verdicts, poleHigh, poleLow }) {
  const [all, setAll] = React.useState(false)
  if (!verdicts?.length) return null
  const heaviest = Math.max(...verdicts.map((v) => v.weight || 0), 0.0001)
  const shown = all ? verdicts : verdicts.slice(0, HEAVIEST)
  const hidden = verdicts.length - shown.length

  return (
    <>
    <ul className="verdicts">
      {shown.map((verdict) => {
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
      {hidden > 0 && (
        <button type="button" className="verdicts-more" onClick={() => setAll(true)}>
          Show the other {hidden} propositions that count toward this axis
        </button>
      )}
      {all && verdicts.length > HEAVIEST && (
        <button type="button" className="verdicts-more" onClick={() => setAll(false)}>
          Show only the heaviest {HEAVIEST}
        </button>
      )}
    </>
  )
}
