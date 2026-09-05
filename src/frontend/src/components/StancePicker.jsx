import React from 'react'
import { loadStance, saveStance } from '../services/stanceService.js'

// Choosing a moral position, by picking the claim that rings true.
//
// NOBODY IS ASKED TO WEAR A LABEL. The three positions come from a red-pilled
// canon, a Christian one and a feminist one, and none of those words appears
// here. What appears is a face and a claim, because the claim is the thing the
// axes are actually built from, and it is the thing a person can answer about
// themselves without being sorted into a group.
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
  access, shareToken = null, onChange, onClose, onLoaded, closeLabel = 'Done',
}) {
  const [data, setData] = React.useState(null)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState(null)

  React.useEffect(() => {
    let live = true
    loadStance(access)
      .then((body) => {
        if (!live) return
        setData(body)
        // The page above decides what an already-answered person sees, because
        // only it knows whether they are walking the flow or came back to
        // change their mind.
        onLoaded?.(body)
      })
      .catch(() => live && setError('Could not load the positions.'))
    return () => { live = false }
  }, [access, onLoaded])

  const commit = React.useCallback(async (stanceId, weight) => {
    setSaving(true)
    setError(null)
    try {
      const saved = await saveStance(access, stanceId, weight, shareToken)
      setData((current) => ({ ...current, ...saved }))
      onChange?.(saved)
    } catch {
      setError('That did not save. Try again?')
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
      <h2>Which of these rings truest?</h2>
      <p className="stance-note">
        It steers what you are shown. Only you see it, and you can change it whenever.
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
        onClick={() => commit(null, 0)}
      >
        None of these — just show me good films
      </button>

      {chosen && (
        <label className="stance-weight">
          <span>How much should it steer?</span>
          <input
            type="range" min="0" max="100" step="5"
            value={Math.round(weight * 100)}
            disabled={saving}
            onChange={(event) => {
              const next = Number(event.target.value) / 100
              setData((current) => ({ ...current, weight: next }))
            }}
            onPointerUp={(event) => commit(chosen, Number(event.target.value) / 100)}
            onKeyUp={(event) => commit(chosen, Number(event.target.value) / 100)}
          />
          <output>
            {weight === 0 ? 'Not at all' : `${Math.round(weight * 100)}%`}
          </output>
        </label>
      )}

      {error && <p className="message">{error}</p>}
      {onClose && (
        <button type="button" className="stance-done" onClick={onClose}>{closeLabel}</button>
      )}
    </div>
  )
}
