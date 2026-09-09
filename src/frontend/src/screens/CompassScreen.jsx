import React, { useEffect, useRef, useState } from 'react'
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
  const bodyRef = useRef(null)
  const [more, setMore] = useState(false)

  // Whether the reading runs past the bottom of its own region, so the page can
  // say so. Without it a short phone shows four scales of five and looks
  // finished — the list has to admit it is cut, or it is quietly lying about
  // how many there are.
  useEffect(() => {
    const el = bodyRef.current
    if (!el) return undefined
    const check = () => setMore(el.scrollTop + el.clientHeight < el.scrollHeight - 4)
    check()
    el.addEventListener('scroll', check, { passive: true })
    window.addEventListener('resize', check)
    return () => {
      el.removeEventListener('scroll', check)
      window.removeEventListener('resize', check)
    }
  }, [profile, companions])

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
        {/* The reading scrolls; the way onward does not.

            This screen is the one page whose height depends on what it found —
            five taste rows, some with labels that wrap to two lines, plus a
            provisional note when there is one — and on a short phone that came
            to more than the viewport. The button sat below the fold on a page
            with no visible sign that it scrolled, so it read as a screen with
            no way off it, and the fix people found by accident was to swipe.
            Bounding this region means the action is on screen whatever the
            reading turns out to be. */}
        <div className={more ? 'compass-body has-more' : 'compass-body'} ref={bodyRef}>
        <header className="compass-header">
          <span>Your compass</span>
          <span className="compass-view-label">{profile.evidence.films_used} films read</span>
        </header>

        {/* The word carries the colour it carries everywhere else, so the
            page names the half of the reading it is showing. */}
        <h1>Your <em className="lit-taste">taste</em> in films.</h1>
        {/* One line at 390px, deliberately: the count of films read is already
            in the header above it, and this sentence wrapping to two was the
            difference between the five rows fitting a phone and not. */}
        <p className="compass-lede">From the films you know, against 162,000 raters.</p>

        {profile.is_provisional && (
          <p className="compass-provisional">
            Provisional — a few more films will settle these.
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
        </div>

        <div className="compass-action">
          <button className="peach-button" type="button" onClick={onContinue}>
            See tonight’s list <span aria-hidden="true">→</span>
          </button>
          {/* One way on, not three. The three were a corpus lookup, the same
              atlas with the viewer marked, and the atlas plain — all the same
              destination in effect, stacked under the one button anybody came
              here to press. This one lands on the half of the atlas that
              answers the question the screen just raised. */}
          <a className="quiet-link" href="#/atlas?space=taste">Where do these scales come from? →</a>
        </div>
      </section>
    </main>
  )
}

export default CompassScreen
