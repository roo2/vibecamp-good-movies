import React from 'react'
import { loadFilmAxes } from '../../services/factorService.js'
import Verdicts from './Verdicts.jsx'

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

export function FactorDistribution({ films, poleLow, poleHigh, reading, factorId }) {
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
          <AnchorList films={[...chosen].sort((a, b) => b.score - a.score)}
                      reading={reading} factorId={factorId} />
        </div>
      ) : (
        <p className="distribution-hint">Click a bar to see which films are in it.</p>
      )}
    </div>
  )
}


// Why one film sits where it does on one axis.
//
// A list of films under an axis is an assertion until you can open one. This
// fetches that film's verdicts and shows only the propositions belonging to
// this factor — the actual sentences it affirmed and denied, which is the
// evidence the position was computed from and the thing a doubtful reader
// wants first.
export function FilmOnAxis({ reading, factorId, film }) {
  const [state, setState] = React.useState({ status: 'loading' })

  React.useEffect(() => {
    let live = true
    setState({ status: 'loading' })
    loadFilmAxes(reading, film.film_id)
      .then((data) => {
        if (!live) return
        const match = (data.factors || []).find((f) => f.factor_id === factorId)
        setState({ status: 'ready', factor: match })
      })
      .catch(() => live && setState({ status: 'failed' }))
    return () => { live = false }
  }, [reading?.scorer, reading?.variant, reading?.bank_version, factorId, film.film_id])

  if (state.status === 'loading') return <p className="film-why-note">Reading its answers…</p>
  if (state.status === 'failed' || !state.factor?.verdicts?.length) {
    return <p className="film-why-note">No recorded answers for this film on this axis.</p>
  }

  const verdicts = state.factor.verdicts
  const high = verdicts.filter((v) => v.points_to === 'high').length
  const flipped = verdicts.filter((v) => v.reverse_keyed).length
  const heaviest = Math.max(...verdicts.map((v) => v.weight || 0), 0.0001)

  return (
    <div className="film-why">
      {/* Counted by the pole each answer SUPPORTS, not by whether it was an
          affirmation. Those differ: a factor holds propositions that contradict
          each other, so denying one of them asserts what affirming another
          does, and a bare tally of affirmations explains nothing. */}
      <p className="film-why-note">
        {high} of {verdicts.length} answers point to <b>{state.factor.pole_high_label}</b>
        {' '}— which is what puts it at <b>{signed(film.score)}</b>.
        {!!flipped && ` ${flipped} of them by denying the opposite.`}
      </p>
      <Verdicts verdicts={verdicts}
                poleHigh={state.factor.pole_high_label}
                poleLow={state.factor.pole_low_label} />
    </div>
  )
}

function AnchorList({ films, reading, factorId }) {
  const [openId, setOpenId] = React.useState(null)
  return (
    <ul>
      {films.map((film) => (
        <li key={film.film_id} className={openId === film.film_id ? 'open' : ''}>
          <button type="button" aria-expanded={openId === film.film_id}
                  onClick={() => setOpenId(openId === film.film_id ? null : film.film_id)}>
            <b>{film.title}</b>
            <em>{signed(film.score)}</em>
            <span>{film.items} item{film.items === 1 ? '' : 's'}</span>
          </button>
          {openId === film.film_id && (
            <FilmOnAxis reading={reading} factorId={factorId} film={film} />
          )}
        </li>
      ))}
    </ul>
  )
}

export function FilmAnchors({ high, low, poleHigh, poleLow, highLabel, lowLabel,
                              reading, factorId }) {
  if (!high?.length && !low?.length) return null
  // Each column says what its end of the axis MEANS, not just which way it
  // points. "Furthest toward affirming" is only informative to a reader who has
  // kept the pole sentence in their head from four lines up.
  return (
    <div className="anchors">
      <div className="anchors-side high">
        <span className="anchors-label">Most {highLabel || 'affirming'}</span>
        {poleHigh && <p className="anchors-pole">{poleHigh}</p>}
        <AnchorList films={high} reading={reading} factorId={factorId} />
      </div>
      <div className="anchors-side low">
        <span className="anchors-label">Most {lowLabel || 'denying'}</span>
        {poleLow && <p className="anchors-pole">{poleLow}</p>}
        <AnchorList films={low} reading={reading} factorId={factorId} />
      </div>
    </div>
  )
}

// Each proposition with how the corpus split on it, and how much it defines the
// axis. An item nobody ever denies carries no information about differences
// between films however often it is affirmed, so the two counts are shown
// rather than one engagement total.
//
// The strength is SIGNED, and the sign is not decoration. A factor holds
// propositions that contradict each other — films answer them together, which
// is what makes them one axis — so affirming one and denying another can put a
// film at the same end. Magnitude alone would leave a reader to guess which
// sentences run backwards, and on this corpus a third of them do.
export function FactorPropositions({ propositions, poleHigh, poleLow }) {
  if (!propositions?.length) return null
  const strongest = Math.max(...propositions.map((r) => Math.abs(r.loading || 0)), 0.0001)
  return (
    <table className="atlas-table proposition-table">
      <thead>
        <tr>
          <th>proposition</th>
          <th title="How much this proposition defines the axis, and which end affirming it puts a film on">strength</th>
          <th>affirmed</th><th>denied</th>
        </tr>
      </thead>
      <tbody>
        {propositions.map((row) => {
          const loading = row.loading
          const high = (loading ?? 0) >= 0
          const pole = high ? poleHigh : poleLow
          return (
            <tr key={row.item_id}>
              <td>{row.text}</td>
              <td className={`prop-strength ${high ? 'adds' : 'subtracts'}`}
                  title={pole ? `Affirming this puts a film toward ${pole}` : undefined}>
                {loading == null ? '—' : (
                  <>
                    {/* The track is a FIXED width and the fill is a percentage
                        of it. Sizing the fill against the cell instead made its
                        width depend on a column the table was still resolving —
                        the first column claims 100% and squeezes the rest — so
                        the bar overflowed into the neighbouring count. */}
                    <span className="prop-bar">
                      <i style={{ inlineSize: `${Math.round((Math.abs(loading) / strongest) * 100)}%` }} />
                    </span>
                    <span className="prop-num">{high ? '+' : '−'}{Math.abs(loading).toFixed(2)}</span>
                  </>
                )}
              </td>
              <td><b>{row.affirms}</b></td>
              <td>{row.denies || <span className="never-denied" title="No film denied this, so it cannot separate films">0</span>}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
