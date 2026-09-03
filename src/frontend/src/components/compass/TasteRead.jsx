import React from 'react'

// What KIND of film someone is drawn to.
//
// This is now the whole reading, and that is a finding rather than a
// simplification. Measured on 162,000 outside raters, which films a person
// enjoys is predicted at 83% by what other people enjoyed alongside them and at
// 57% by any moral axis — so a compass leading with morals was leading with the
// weaker half. The moral axes are still derived, still published on the atlas,
// and still what the film pages are read on; they are just not a claim worth
// making about a PERSON from a dozen ratings.
//
// Colour arrived with that change. These rows used to be deliberately grey,
// because the moral axes above them carried the atlas plot's two colours and
// taste borrowing them would have looked like a moral claim. With the moral
// axes gone there is nothing to be mistaken for, and five unlabelled grey rows
// were hard to tell apart at a glance — so each dimension now owns a hue and
// keeps it.

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

// One hue per row, in the order the server sends them, so a dimension keeps its
// colour between somebody's own profile and the film pages. Chosen for
// separation on the dark ground rather than for prettiness: amber, teal,
// violet, rose and green stay distinguishable to a red-green colourblind reader
// because they differ in lightness as well as hue.
const HUES = ['#eda36b', '#5cc3c0', '#b58ce0', '#e0899a', '#93c56b']

// "78th percentile" is precise and unreadable. What a person wants to know is
// which end they are at and how far, which is three words.
function lean(percentile) {
  const distance = Math.abs(percentile - 50)
  if (distance < 8) return 'right in the middle'
  if (distance < 20) return 'leans'
  if (distance < 35) return 'clearly'
  return 'strongly'
}

export default function TasteRead({ taste, companions = [] }) {
  const rows = (taste || []).slice(0, SHOWN)
  if (!rows.length) return null

  return (
    <section className="taste-read">
      <h2 className="taste-read-head">What you are drawn to</h2>
      <ul className="taste-axes">
        {rows.map((row, index) => {
          const high = row.percentile >= 50
          const label = high ? row.pole_high : row.pole_low
          const strength = lean(row.percentile)
          // Every companion who has been read on this same dimension.
          const others = companions
            .map((c) => ({
              name: c.name,
              row: (c.profile?.taste || []).find((t) => t.dim_id === row.dim_id),
            }))
            .filter((c) => c.row)
          return (
            <li key={row.dim_id} className="taste-axis" style={{ '--hue': HUES[index % HUES.length] }}>
              <p className="taste-axis-read">
                {strength === 'right in the middle'
                  ? <>You sit <b>between {row.pole_low.toLowerCase()} and {row.pole_high.toLowerCase()}</b>.</>
                  : <>You {strength === 'leans' ? 'lean toward' : ''}{strength === 'clearly' ? 'clearly prefer' : ''}{strength === 'strongly' ? 'strongly prefer' : ''} <b>{label.toLowerCase()}</b>.</>}
              </p>
              <span className="taste-axis-poles">
                <span className={high ? '' : 'lit'}>{row.pole_low}</span>
                <span className={high ? 'lit' : ''}>{row.pole_high}</span>
              </span>
              <span className="taste-axis-track">
                <i className="taste-axis-mid" />
                <i
                  className="taste-axis-band"
                  style={high
                    ? { left: '50%', width: `${row.percentile - 50}%` }
                    : { left: `${row.percentile}%`, width: `${50 - row.percentile}%` }}
                />
                {others.map((other) => (
                  <b
                    key={other.name || other.row.dim_id}
                    className="taste-axis-marker companion"
                    style={{ left: `${other.row.percentile}%` }}
                    title={`${other.name || 'They'}: ${other.row.percentile}`}
                  />
                ))}
                <b className="taste-axis-marker" style={{ left: `${row.percentile}%` }} />
              </span>
            </li>
          )
        })}
      </ul>
      <p className="taste-axes-note">
        Built from which films the same people enjoy, across 162,000 outside raters.
        {companions.length > 0 && ' Hollow markers are the others in your session.'}
      </p>
    </section>
  )
}
