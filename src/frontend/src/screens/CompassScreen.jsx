import React, { useEffect, useState } from 'react'
import CompassMap from '../components/compass/CompassMap.jsx'
import { loadCompassProfile } from '../services/profileService.js'

function CompassScreen({ answers, onContinue }) {
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadCompassProfile({ answers }).then(setProfile).catch(() => setError('Your compass could not be loaded yet.'))
  }, [answers])

  if (error) return <main className="app-page"><p className="message">{error}</p></main>
  if (!profile) return <main className="app-page"><p className="message">Reading your compass…</p></main>

  return (
    <main className="app-page">
      <section className="phone-screen compass-screen">
        <header className="compass-header"><span>Your compass · the map</span><span className="compass-view-label">See the 6 bars</span></header>
        <h1>Everything we read in you, flattened onto two questions.</h1>
        <p className="compass-lede">These two directions came out of the films themselves — nobody chose them. Together they account for <strong>{profile.varianceExplained}%</strong> of what separates one story from another.</p>
        <CompassMap profile={profile} />
        <div className="compass-reading"><span aria-hidden="true">◇</span><p>{profile.interpretation}</p></div>
        <div className="compass-action"><p>You’ll be able to refine this once live scoring is connected.</p><button className="peach-button" type="button" onClick={onContinue}>That’s me — find someone to watch with</button></div>
      </section>
    </main>
  )
}

export default CompassScreen
