import React from 'react'

// What KIND of film someone is drawn to, beside what those films argue.
//
// It belongs here because it is the more useful half. Measured on outside
// raters, which films a person enjoys is predicted far better by what other
// people enjoyed alongside them than by any moral axis — so a compass showing
// only morals was showing the weaker reading as the whole answer.
//
// Built from the compass's own axis markup rather than the atlas film scales it
// used to borrow. Two groups on one screen drawn by two different systems read
// as two instruments, and nothing tells a reader they are meant to be compared.
//
// One thing stays deliberately different: no colour on the poles. The moral
// axes carry the two colours the atlas plot uses for them, and taste is not a
// moral claim — it should not borrow the authority of looking like one.

// Five, and the five are chosen rather than the largest. Sixteen dimensions
// replicate and six can be named, but a profile is READ, not audited, so the
// server hands them over ordered by how reliably each places a person from the
// dozen or so films they actually rated.
//
// Five rather than some other number because that is where the measurement puts
// the break, not because it looked balanced: the top five place a person at
// 0.51, 0.44, 0.43, 0.42 and 0.41, and the sixth falls off a cliff to 0.25.
// People barely differ on that one, so a row for it would be a confident reading
// of noise — which is the only kind of row worth cutting.
const SHOWN = 5

export default function TasteRead({ taste }) {
  const rows = (taste || []).slice(0, SHOWN)
  if (!rows.length) return null

  return (
    <>
      <h2 className="axis-group-head taste">Taste</h2>
      <ul className="moral-axes taste-axes">
        {rows.map((row) => (
          <li key={row.dim_id} className="moral-axis taste">
            <span className="moral-axis-row">
              <span className="moral-axis-poles">
                <span className={row.percentile < 50 ? 'lit' : ''}>{row.pole_low}</span>
                <span className={row.percentile >= 50 ? 'lit' : ''}>{row.pole_high}</span>
              </span>
              <span className="moral-axis-track" aria-hidden="true">
                <i className="moral-axis-mid" />
                <b className="moral-axis-marker" style={{ left: `${row.percentile}%` }} />
              </span>
            </span>
          </li>
        ))}
      </ul>
      <p className="taste-axes-note">Which films the same people enjoy. Nothing moral here.</p>
    </>
  )
}
