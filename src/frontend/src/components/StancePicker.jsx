import React from 'react'
import { loadStance, saveStance } from '../services/stanceService.js'

// How much the chosen position drives the ranking, as three named amounts.
//
// A slider was worse in both directions: fiddly to land on a value, and it
// implied a precision the number does not have — nothing here is calibrated
// finely enough that 0.55 differs from 0.60 in a way anybody could perceive.
// Five buttons were the same mistake in smaller print. Three are as many
// distinctions as the thing being set can carry, and they fit at a size worth
// tapping.
//
// The captions name the real trade rather than the mechanism. Turning this up
// does NOT make recommendations better — on 162,265 outside raters, neighbour
// films order a liked film above a disliked one 83% of the time against the
// moral axes' 57% — so it buys agreement with what you believe at the cost of
// how well the deck predicts what you will enjoy. Saying "more moral weight"
// would hide that; saying which of the two you get more of does not.
// The top is 0.8, not 1. At full weight the ranking drops co-preference
// entirely, and co-preference is the only part of it that predicts enjoyment —
// 83% against the axes' 57%. A deck ordered purely by what a film argues is
// reliably less watchable, so the strongest setting keeps a fifth of the say
// with enjoyment rather than offering a way to turn the good half off.
const STEER = [
  { weight: 0.25, label: 'A nudge', caption: 'Mostly films you are likely to enjoy, tipped your way.' },
  { weight: 0.5, label: 'Half and half', caption: 'An even mix of what you will enjoy and what you believe.' },
  { weight: 0.8, label: 'As far as it goes', caption: 'Led by what you believe. Enjoyment keeps a fifth of the say, so the deck stays watchable.' },
]
// A stored weight need not be one of the five — earlier versions wrote any value
// the slider could reach — so the nearest is shown rather than none of them.
const nearestLevel = (weight) => STEER.reduce((best, level) =>
  Math.abs(level.weight - weight) < Math.abs(best.weight - weight) ? level : best, STEER[0])

// Choosing a moral position.
//
// THE POSITIONS ARE NAMED, and the screen says the word morality. An earlier
// version showed only a face and a claim and named nothing, so that nobody was
// asked to wear a label. That made the screen ambiguous rather than gentle:
// this product measures two different things about a film — what it argues for,
// and what kind of film it is — and three unlabelled quotes leave the reader to
// guess which of the two is being asked about.
//
// The label leads and the claim supports it, because the label is what somebody
// scans and the claim is what makes it mean something specific.
//
// The face is a signpost, not the coordinates. Those come from the whole canon
// behind it — Wonder Woman herself sits at -0.17 on self-determination where her
// canon sits at -0.43, so using her film's own position would place people
// somewhere weaker than the position they picked.
//
// A prominent way out, because for most people this is the right answer: on
// outside raters, weighting morality does not improve what gets recommended.
// The control is here to STEER, and steering somewhere you do not want to go is
// not a feature.
export default function StancePicker({
  access, shareToken = null, onChange, onClose, closeLabel = 'Done',
}) {
  const [data, setData] = React.useState(null)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState(null)

  // Depends on `access` alone, and must keep doing so. A callback prop is a new
  // function on every render of whatever passes it, so taking one as a
  // dependency here means fetch, setData, re-render, new callback, fetch again,
  // forever. That happened, and from the outside it looked like the button after
  // the landing page did nothing.
  React.useEffect(() => {
    let live = true
    loadStance(access)
      .then((body) => {
        if (!live) return
        setData(body)
      })
      .catch(() => live && setError('Could not load the positions.'))
    return () => { live = false }
  }, [access])

  const commit = React.useCallback(async (stanceId, weight) => {
    setSaving(true)
    setError(null)
    try {
      const saved = await saveStance(access, stanceId, weight, shareToken)
      setData((current) => ({ ...current, ...saved }))
      onChange?.(saved)
      return true
    } catch {
      setError('That did not save. Try again?')
      return false
    } finally {
      setSaving(false)
    }
  }, [access, shareToken, onChange])

  if (error && !data) return <p className="message">{error}</p>
  if (!data) return <p className="message">Reading the positions…</p>

  const chosen = data.stance_id
  // A first choice arrives with the weight already meaning something. Zero would
  // store a position and then ignore it, which reads as the control being broken.
  const weight = data.weight ?? 0

  return (
    <div className="stance-picker">
      <h2>Where do you stand?</h2>
      <p className="stance-note">
        This one is about <strong>morality</strong> — what a film argues for, not what
        kind of film it is. It steers what you are shown. Only you see it, and you can
        change it whenever.
      </p>

      <ul className="stance-options">
        {data.stances.map((stance) => (
          <li key={stance.stance_id}>
            <button
              type="button"
              className={stance.stance_id === chosen ? 'chosen' : ''}
              aria-pressed={stance.stance_id === chosen}
              disabled={saving}
              onClick={() => commit(stance.stance_id,
                stance.stance_id === chosen ? weight : (weight || 0.5))}
            >
              {stance.artwork_url && (
                // A character image is a figure and must not be cropped; a
                // poster is a composition and has to be, or the tile is mostly
                // title treatment. They cannot share a fit.
                <img
                  className={stance.shows_character ? 'is-character' : 'is-poster'}
                  src={stance.artwork_url} alt="" loading="lazy"
                />
              )}
              <span className="stance-words">
                <strong>{stance.label}</strong>
                <q>{stance.line}</q>
                <small>{stance.character}</small>
              </span>
            </button>
          </li>
        ))}
      </ul>

      <button
        type="button"
        className={`stance-none ${chosen === null && data.answered ? 'chosen' : ''}`}
        aria-pressed={chosen === null && data.answered}
        disabled={saving}
        onClick={() => commit(null, 0).then((ok) => ok && onClose?.())}
      >
        None of these — just show me good films
      </button>

      {chosen && (
        <div className="stance-weight">
          <span>How much should it steer?</span>
          <div className="stance-levels" role="group" aria-label="How much should it steer?">
            {STEER.map((level) => (
              <button
                key={level.weight}
                type="button"
                className={level === nearestLevel(weight) ? 'chosen' : ''}
                aria-pressed={level === nearestLevel(weight)}
                disabled={saving}
                onClick={() => commit(chosen, level.weight).then((ok) => ok && onClose?.())}
              >
                {level.label}
              </button>
            ))}
          </div>
          <p className="stance-caption">{nearestLevel(weight).caption}</p>
        </div>
      )}

      {error && <p className="message">{error}</p>}
      {onClose && (
        <button type="button" className="stance-done" onClick={onClose}>{closeLabel}</button>
      )}
    </div>
  )
}
