import React from 'react'
import { loadStance, saveStance } from '../services/stanceService.js'

// How much a chosen position drives the ranking. One value, not a question.
//
// It used to be asked: three named amounts appeared under the tiles and picking
// one was what moved you on. Nobody needs to answer it. The two ends were never
// really on offer — a nudge is barely distinguishable from not answering, and
// the far end is the setting the caption had to warn people about, because a
// deck ordered mostly by what a film argues is reliably less watchable (on
// 162,265 outside raters, neighbour films order a liked film above a disliked
// one 83% of the time against the moral axes' 57%). Half and half was the
// answer worth having and the one nearly everybody took, so it is the answer.
//
// The cost is that the far end is no longer reachable from the interface. That
// is the intended trade: a second question on the cheapest screen in the flow
// bought a setting whose extremes were either invisible or discouraged.
const DEFAULT_WEIGHT = 0.5

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
// FOUR ANSWERS, ONE TAP. Declining is the fourth tile rather than a thin line
// under the other three, because for most people it is the right answer: on
// outside raters, weighting morality does not improve what gets recommended.
// An option that is correct for most readers should not be the smallest thing
// on the screen. The control is here to STEER, and steering somewhere you do
// not want to go is not a feature.
//
// A tap answers and moves on. There is nothing else to ask — the amount is
// settled, and the tiles say everything they are going to say before they are
// touched, so there is nothing to be discovered by selecting one and looking.
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
  const declined = chosen === null && data.answered

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
              onClick={() => commit(stance.stance_id, DEFAULT_WEIGHT)
                .then((ok) => ok && onClose?.())}
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
        <li>
          <button
            type="button"
            className={`stance-decline ${declined ? 'chosen' : ''}`}
            aria-pressed={declined}
            disabled={saving}
            onClick={() => commit(null, 0).then((ok) => ok && onClose?.())}
          >
            {/* Holds the column the three faces occupy, so the fourth tile is
                the same shape rather than a shorter one pretending to be. */}
            <span className="stance-blank" aria-hidden="true" />
            <span className="stance-words">
              <strong>No position</strong>
              <q>Just show me good films.</q>
            </span>
          </button>
        </li>
      </ul>


      {error && <p className="message">{error}</p>}
      {onClose && (
        <button type="button" className="stance-done" onClick={onClose}>{closeLabel}</button>
      )}
    </div>
  )
}
