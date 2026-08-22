import React, { useEffect, useState } from 'react'
import MoralAxes from '../components/compass/MoralAxes.jsx'
import { loadMoralProfile } from '../services/profileService.js'

function readingOf({ films_rated: rated, pairs_answered: pairs }) {
  const parts = []
  if (rated) parts.push(`${rated} ${rated === 1 ? 'film you know' : 'films you know'}`)
  if (pairs) parts.push(`${pairs} ${pairs === 1 ? 'story you chose' : 'stories you chose'} blind`)
  return parts.join(' and ')
}

function CompassScreen({ access, onContinue }) {
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!access) return
    loadMoralProfile(access)
      .then(setProfile)
      .catch(() => setError('Your compass could not be loaded yet.'))
  }, [access])

  if (error) return <main className="app-page"><p className="message">{error}</p></main>
  if (!profile) return <main className="app-page"><p className="message">Reading your compass…</p></main>

  const reading = readingOf(profile.evidence)

  return (
    <main className="app-page">
      <section className="phone-screen compass-screen">
        <header className="compass-header">
          <span>Your compass · {profile.scores.length} axes</span>
          <span className="compass-view-label">{profile.evidence.films_used} films read</span>
        </header>

        <h1>Where the films put you.</h1>
        <p className="compass-lede">
          These axes came out of the films themselves — nobody chose them.{' '}
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

        <MoralAxes scores={profile.scores} />

        <div className="compass-action">
          <p>Tap an axis to see the question behind it.</p>
          <button className="peach-button" type="button" onClick={onContinue}>
            That’s me — find someone to watch with
          </button>
        </div>
      </section>
    </main>
  )
}

export default CompassScreen
