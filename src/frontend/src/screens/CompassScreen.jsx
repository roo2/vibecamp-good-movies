import React, { useEffect, useState } from 'react'
import FlowProgress, { COMPASS_STEP } from '../components/FlowProgress.jsx'
import MoralAxes from '../components/compass/MoralAxes.jsx'
import { loadMoralProfile, loadSessionMoralProfiles } from '../services/profileService.js'

function readingOf({ films_rated: rated, pairs_answered: pairs }) {
  const parts = []
  if (rated) parts.push(`${rated} ${rated === 1 ? 'film you know' : 'films you know'}`)
  if (pairs) parts.push(`${pairs} ${pairs === 1 ? 'story you chose' : 'stories you chose'} blind`)
  return parts.join(' and ')
}

function CompassScreen({ access, shareToken, onContinue }) {
  const [profile, setProfile] = useState(null)
  const [companions, setCompanions] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!access) return
    loadMoralProfile(access)
      .then(setProfile)
      .catch(() => setError('Your compass could not be loaded yet.'))
  }, [access])

  // The others are fetched separately and failure is swallowed on purpose: a
  // companion who has not answered yet, or a session of one, must not stop you
  // seeing your own reading.
  useEffect(() => {
    if (!access || !shareToken) return undefined
    let live = true
    loadSessionMoralProfiles(access, shareToken)
      .then((payload) => live && setCompanions(payload.companions || []))
      .catch(() => live && setCompanions([]))
    return () => { live = false }
  }, [access, shareToken])

  if (error) return <main className="app-page"><p className="message">{error}</p></main>
  if (!profile) return <main className="app-page"><p className="message">Reading your compass…</p></main>

  const reading = readingOf(profile.evidence)

  return (
    <main className="app-page">
      <section className="phone-screen compass-screen">
        <FlowProgress current={COMPASS_STEP} />
        <header className="compass-header">
          <span>Your compass · {profile.scores.length} axes</span>
          <span className="compass-view-label">{profile.evidence.films_used} films read</span>
        </header>

        <h1>Where the films put you.</h1>
        <p className="compass-lede">
          This compass reads your choices against the values films explore.{' '}
          {reading ? (
            <>
              We read <strong>{reading}</strong> against the moral propositions each
              film argues for, and this is where that leaves you.
            </>
          ) : (
            <>You have not told us about any films yet, so there is nothing to read you against.</>
          )}
        </p>

        {profile.is_provisional && (
          <p className="compass-provisional">
            Still provisional — a few more films and these will settle.
          </p>
        )}

        <div className="compass-reading"><span aria-hidden="true">◇</span><p>{profile.summary}</p></div>

        <MoralAxes scores={profile.scores} companions={companions} />

        <div className="compass-action">
          <p>{companions.length ? 'Tap an axis to see the question, and where each of you landed on it.' : 'Tap an axis to see the question behind it.'}</p>
          <button className="peach-button" type="button" onClick={onContinue}>
            See tonight’s list <span aria-hidden="true">→</span>
          </button>
        </div>
      </section>
    </main>
  )
}

export default CompassScreen
