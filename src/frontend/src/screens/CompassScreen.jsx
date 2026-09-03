import React, { useEffect, useState } from 'react'
import TasteRead from '../components/compass/TasteRead.jsx'
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
        <header className="compass-header">
          <span>Your compass</span>
          <span className="compass-view-label">{profile.evidence.films_used} films read</span>
        </header>

        <h1>What you are drawn to.</h1>
        <p className="compass-lede">Read from the films you know, against 162,000 other raters.</p>

        {profile.is_provisional && (
          <p className="compass-provisional">
            Still provisional — a few more films and these will settle.
          </p>
        )}

        {/* The moral axes are no longer read back to a person here. They are
            derived, published and tested on the atlas, and every film is still
            placed on them — but a dozen ratings is not enough to tell somebody
            what they believe, and the same 162,000 raters that make the taste
            read work put moral prediction at 57% against taste's 83%. Saying
            less, and meaning it, beats a confident sentence about somebody's
            morals drawn from twelve films they have seen. */}
        <TasteRead taste={profile.taste} companions={companions} />

        <div className="compass-action">
          <button className="peach-button" type="button" onClick={onContinue}>
            See tonight’s list <span aria-hidden="true">→</span>
          </button>
          {/* Two ways on for a reader who does not want tonight's list: where the
              scales came from, and what the same scales make of a film they
              already have in mind. */}
          <a className="quiet-link" href="#/corpus">Look up a film you love →</a>
          <a className="quiet-link" href="#/atlas?me=1">See where you sit among the films →</a>
          <a className="quiet-link" href="#/atlas">Where do these scales come from? →</a>
        </div>
      </section>
    </main>
  )
}

export default CompassScreen
