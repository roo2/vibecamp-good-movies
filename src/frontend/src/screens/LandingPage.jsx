import React from 'react'

import { APP_VERSION } from '../config/version'

function LandingPage({ onSignIn, joining = false }) {
  const [error, setError] = React.useState(null)
  const [submitting, setSubmitting] = React.useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setError(null)
    setSubmitting(true)
    try {
      await onSignIn(form.get('name'))
    } catch (submissionError) {
      setError(submissionError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="app-page login-page">
      <section className="phone-screen login-screen" aria-label="Sign in">
        <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Something Good To Watch</span></div>
        <div className="login-content">
          <p className="screen-label">{joining ? 'Your partner invited you' : 'For two people · 90 seconds each'}</p>
          {/* Only the word that carries the promise is lit. Emphasis on a whole
              phrase is emphasis on nothing — the eye needs one place to land. */}
          <h1>{joining ? <>Watch something<br /><em>together.</em></> : <>Find something<br /><em>good</em> to watch.</>}</h1>
          <p className="screen-copy">{joining
            ? 'Put your name in and you’ll be answering alongside them. You won’t see each other’s answers.'
            : 'Every film argues for something. You and your partner each spend ninety seconds on films you already know — separately, no peeking — and we find the ones whose moral message you both agree with. You’ll end up with a shortlist of three.'}</p>
        </div>
        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="name">Your name</label>
          <input id="name" name="name" type="text" placeholder="Your name" autoComplete="name" required maxLength="80" />
          {error && <p className="message" role="alert">{error}</p>}
          <button className="peach-button" type="submit" disabled={submitting}>{submitting ? 'Joining…' : <>{joining ? 'Join them' : 'Continue'} <span aria-hidden="true">→</span></>}</button>
        </form>
        <p className="login-footer">
          {joining ? 'Just a name — they are waiting for you.' : 'Just a name to start. You’ll invite your partner next.'}
          <br />
          <a className="quiet-link" href="#/atlas">See the dataset behind it →</a>
          <br />
          <span className="build-marker">v{APP_VERSION}</span>
        </p>
      </section>
    </main>
  )
}

export default LandingPage
