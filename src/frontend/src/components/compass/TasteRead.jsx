import React from 'react'

// What KIND of film someone is drawn to, beside what those films argue.
//
// It belongs here because it is the more useful half. Measured on 162,265
// outside raters, which films a person enjoys is predicted far better by what
// other people enjoyed alongside them than by any moral axis — so a compass
// that showed only morals was showing the weaker reading and calling it the
// whole answer.
//
// Borrows the film scales' markup so a reader meets one instrument rather than
// three. What stays different is colour: taste is neutral, because it is not a
// moral claim and should not borrow the authority of looking like one.

export default function TasteRead({ taste }) {
  const rows = (taste || []).slice(0, 5)
  if (!rows.length) return null

  return (
    <section className="taste-read">
      <h2>And what kind of films they are</h2>
      <ul className="film-factors">
        {rows.map((row) => {
          // From the middle, like every other scale here. The middle is the
          // typical film, and the bar is how far from typical these choices sit.
          const magnitude = Math.abs(row.percentile - 50)
          const high = row.percentile >= 50
          return (
            <li key={row.dim_id} className="film-factor taste">
              <span className="film-factor-scale">
                <em className={!high ? 'lit' : ''}>{row.pole_low}</em>
                <span className="film-factor-track">
                  <u className="film-factor-mid" />
                  <i className="film-factor-bar taste"
                     style={high
                       ? { insetInlineStart: '50%', inlineSize: `${magnitude}%` }
                       : { insetInlineEnd: '50%', inlineSize: `${magnitude}%` }} />
                </span>
                <em className={high ? 'lit' : ''}>{row.pole_high}</em>
              </span>
              <span className="film-factor-score">
                {row.percentile}<em>percentile</em>
              </span>
            </li>
          )
        })}
      </ul>
      <p className="atlas-note">
        Discovered from which films the same people enjoy — nothing here is moral. A reading sits
        nearer the middle than any single film does, because it averages everything you told us.
      </p>
    </section>
  )
}
