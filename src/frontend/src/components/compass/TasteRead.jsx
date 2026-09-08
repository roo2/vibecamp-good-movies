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

// No sentence over each row any more.
//
// "You lean toward silly fun." sat directly above two labels reading Silly fun
// and Serious storytelling with a marker nearer the first — three ways of
// saying one thing, and the wordiest of the three led. What is left is the two
// names and the position between them, which was always the whole reading; the
// names are large enough now to BE the row rather than caption it.

export default function TasteRead({ taste, companions = [] }) {
  const rows = (taste || []).slice(0, SHOWN)
  if (!rows.length) return null

  return (
    <section className="taste-read">
      {/* No heading. The screen's own h1 is "What you are drawn to." and this
          said it again, three lines below itself. */}
      <ul className="taste-axes">
        {rows.map((row, index) => {
          const high = row.percentile >= 50
          // Every companion who has been read on this same dimension.
          const others = companions
            .map((c) => ({
              name: c.name,
              row: (c.profile?.taste || []).find((t) => t.dim_id === row.dim_id),
            }))
            .filter((c) => c.row)
          return (
            <li key={row.dim_id} className="taste-axis" style={{ '--hue': HUES[index % HUES.length] }}>
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
      {/* Where the rows come from is already said above the fold, in the lede.
          What is left here is a legend, and only when there is something to
          read one for. */}
      {companions.length > 0 && (
        <p className="taste-axes-note">Hollow markers are the others in your session.</p>
      )}
    </section>
  )
}
