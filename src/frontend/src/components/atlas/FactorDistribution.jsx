import React from 'react'

// Where every film sits on one axis.
//
// A histogram rather than the top and bottom few, because those two lists always
// look decisive — they are the extremes by construction. The shape in between is
// what says whether the axis separates films or merely records something the
// whole corpus agrees about, and on this data that distinction is real: one
// factor has 154 films averaging +0.84, which is a high eigenvalue and almost no
// discrimination.

const BINS = 17  // odd, so zero gets a bin of its own rather than a boundary

function bin(scores) {
  const counts = new Array(BINS).fill(0)
  for (const score of scores) {
    const index = Math.min(BINS - 1, Math.max(0, Math.round(((score + 1) / 2) * (BINS - 1))))
    counts[index] += 1
  }
  return counts
}

export function FactorDistribution({ scores, poleLow, poleHigh }) {
  if (!scores?.length) return null
  const counts = bin(scores)
  const tallest = Math.max(...counts)
  const mean = scores.reduce((total, score) => total + score, 0) / scores.length
  const positive = scores.filter((score) => score > 0.2).length
  const negative = scores.filter((score) => score < -0.2).length
  const middle = scores.length - positive - negative

  return (
    <div className="distribution">
      <div className="distribution-bars" role="img"
           aria-label={`Score distribution across ${scores.length} films`}>
        {counts.map((count, index) => (
          <div className="distribution-bin" key={index}
               title={`${count} film${count === 1 ? '' : 's'}`}>
            <i style={{ blockSize: `${tallest ? (count / tallest) * 100 : 0}%` }} />
          </div>
        ))}
        {/* The midline is where a film that affirmed and denied in equal measure
            would land, so a distribution piled to one side of it is the axis
            telling you the corpus agrees rather than that films differ. */}
        <u className="distribution-mid" />
      </div>
      <div className="distribution-scale">
        <span>{poleLow ? 'denies' : '−1'}</span>
        <span className="distribution-mean">
          {scores.length} films · mean {mean >= 0 ? '+' : ''}{mean.toFixed(2)}
        </span>
        <span>{poleHigh ? 'affirms' : '+1'}</span>
      </div>
      <p className="distribution-split">
        {positive} lean toward affirming · {middle} near the middle · {negative} toward denying
        {positive / scores.length > 0.85 && (
          <em> — almost every film agrees here, so this axis says more about the
            corpus than it distinguishes between films.</em>
        )}
      </p>
    </div>
  )
}

export function FilmAnchors({ high, low }) {
  if (!high?.length && !low?.length) return null
  return (
    <div className="anchors">
      <div>
        <span className="anchors-label">Furthest toward affirming</span>
        <ul>
          {high.map((film) => (
            <li key={film.film_id}>
              <b>{film.title}</b>
              <em>{film.score >= 0 ? '+' : ''}{film.score.toFixed(2)}</em>
              <span>{film.items} items</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <span className="anchors-label">Furthest toward denying</span>
        <ul>
          {low.map((film) => (
            <li key={film.film_id}>
              <b>{film.title}</b>
              <em>{film.score >= 0 ? '+' : ''}{film.score.toFixed(2)}</em>
              <span>{film.items} items</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

// Each proposition with how the corpus split on it. An item nobody ever denies
// carries no information about differences between films however often it is
// affirmed, so the two counts are shown rather than one engagement total.
export function FactorPropositions({ propositions }) {
  if (!propositions?.length) return null
  return (
    <table className="atlas-table proposition-table">
      <thead>
        <tr><th>proposition</th><th>affirmed</th><th>denied</th></tr>
      </thead>
      <tbody>
        {propositions.map((row) => (
          <tr key={row.item_id}>
            <td>{row.text}</td>
            <td><b>{row.affirms}</b></td>
            <td>{row.denies || <span className="never-denied" title="No film denied this, so it cannot separate films">0</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
