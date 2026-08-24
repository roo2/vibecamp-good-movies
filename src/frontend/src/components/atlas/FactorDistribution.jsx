import React from 'react'

// Where every film sits on one axis.
//
// A histogram rather than the top and bottom few, because those two lists always
// look decisive — they are the extremes by construction. The shape in between is
// what says whether the axis separates films or merely records something the
// whole corpus agrees about, and on this data that distinction is real: one
// factor has 154 films averaging +0.84, which is a high eigenvalue and almost no
// discrimination.
//
// The bins are clickable. A histogram of anonymous bars can be doubted but not
// checked: a reader who thinks the pile at −1 looks wrong has no way to ask
// which films are in it. Opening a bin answers that with names.

const BINS = 17  // odd, so zero gets a bin of its own rather than a boundary

const binOf = (score) =>
  Math.min(BINS - 1, Math.max(0, Math.round(((score + 1) / 2) * (BINS - 1))))

// The centre bin is neither side. Everything left of it denies, right affirms —
// the same orange/teal the bars and verdict labels use everywhere else, so the
// direction is legible before any label is read.
const sideOf = (index) => (index === (BINS - 1) / 2 ? 'mid' : index < (BINS - 1) / 2 ? 'low' : 'high')

const signed = (value) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}`

export function FactorDistribution({ films, poleLow, poleHigh }) {
  const [open, setOpen] = React.useState(null)
  if (!films?.length) return null

  // This endpoint used to send bare scores and now sends whole films. Accept
  // either: the page and the API deploy separately, and a bundle that reaches
  // browsers before the API does would otherwise read .score off a number and
  // draw an empty histogram — a silent blank where the shape should be.
  const rows = films.map((film, index) => (
    typeof film === 'number' ? { film_id: `n${index}`, title: null, score: film } : film))

  const bins = Array.from({ length: BINS }, () => [])
  for (const film of rows) bins[binOf(film.score)].push(film)

  const tallest = Math.max(...bins.map((bin) => bin.length))
  const mean = rows.reduce((total, film) => total + film.score, 0) / rows.length
  const positive = rows.filter((film) => film.score > 0.2).length
  const negative = rows.filter((film) => film.score < -0.2).length
  const middle = rows.length - positive - negative
  const chosen = open == null ? null : bins[open]

  return (
    <div className="distribution">
      <div className="distribution-bars"
           aria-label={`Score distribution across ${rows.length} films`}>
        {bins.map((bin, index) => {
          const at = (index / (BINS - 1)) * 2 - 1
          return (
            <button type="button" key={index}
                    className={`distribution-bin ${sideOf(index)} ${open === index ? 'open' : ''}`}
                    aria-pressed={open === index}
                    disabled={!bin.length}
                    onClick={() => setOpen(open === index ? null : index)}
                    title={`${bin.length} film${bin.length === 1 ? '' : 's'} near ${signed(at)}`}>
              <i style={{ blockSize: `${tallest ? (bin.length / tallest) * 100 : 0}%` }} />
            </button>
          )
        })}
        {/* The midline is where a film that affirmed and denied in equal measure
            would land, so a distribution piled to one side of it is the axis
            telling you the corpus agrees rather than that films differ. */}
        <u className="distribution-mid" />
      </div>
      <div className="distribution-scale">
        <span className="scale-low">← {poleLow || '−1'}</span>
        <span className="distribution-mean">
          {rows.length} films · mean {signed(mean)}
        </span>
        <span className="scale-high">{poleHigh || '+1'} →</span>
      </div>
      <p className="distribution-split">
        <b className="low">{negative}</b> toward {poleLow || 'denying'} · {middle} near the
        middle · <b className="high">{positive}</b> toward {poleHigh || 'affirming'}
        {positive / rows.length > 0.85 && (
          <em> — almost every film agrees here, so this axis says more about the
            corpus than it distinguishes between films.</em>
        )}
      </p>

      {chosen?.length ? (
        <div className={`distribution-open ${sideOf(open)}`}>
          <span className="distribution-open-label">
            {chosen.length} film{chosen.length === 1 ? '' : 's'} around{' '}
            {signed((open / (BINS - 1)) * 2 - 1)}
            {sideOf(open) === 'mid' ? ' — weighed it both ways'
              : sideOf(open) === 'low' ? ` — ${poleLow || 'toward −1'}`
              : ` — ${poleHigh || 'toward +1'}`}
          </span>
          <ul>
            {[...chosen].sort((a, b) => b.score - a.score).map((film) => (
              <li key={film.film_id}>
                <b>{film.title ?? 'a film'}</b>
                <em>{signed(film.score)}</em>
                {film.items != null && <span>{film.items} item{film.items === 1 ? '' : 's'}</span>}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="distribution-hint">Click a bar to see which films are in it.</p>
      )}
    </div>
  )
}

export function FilmAnchors({ high, low, poleHigh, poleLow, highLabel, lowLabel }) {
  if (!high?.length && !low?.length) return null
  // Each column says what its end of the axis MEANS, not just which way it
  // points. "Furthest toward affirming" is only informative to a reader who has
  // kept the pole sentence in their head from four lines up.
  return (
    <div className="anchors">
      <div className="anchors-side high">
        <span className="anchors-label">Most {highLabel || 'affirming'}</span>
        {poleHigh && <p className="anchors-pole">{poleHigh}</p>}
        <ul>
          {high.map((film) => (
            <li key={film.film_id}>
              <b>{film.title}</b>
              <em>{signed(film.score)}</em>
              <span>{film.items} item{film.items === 1 ? '' : 's'}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="anchors-side low">
        <span className="anchors-label">Most {lowLabel || 'denying'}</span>
        {poleLow && <p className="anchors-pole">{poleLow}</p>}
        <ul>
          {low.map((film) => (
            <li key={film.film_id}>
              <b>{film.title}</b>
              <em>{signed(film.score)}</em>
              <span>{film.items} item{film.items === 1 ? '' : 's'}</span>
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
