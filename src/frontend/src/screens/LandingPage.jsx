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
          <p className="screen-label">{joining ? 'Joining a shared session' : 'A 90-second quiz'}</p>
          {/* Only the word that carries the promise is lit. Emphasis on a whole
              phrase is emphasis on nothing — the eye needs one place to land. */}
          <h1>{joining ? <>Join your<br /><em>movie people.</em></> : <>Find something<br /><em>good</em> to watch.</>}</h1>
          <p className="screen-copy">{joining
            ? 'Start with your name, then you’ll enter their session.'
            : 'Every film argues for something. Ninety seconds of films you already know is enough to read what you each believe — and to find one whose moral message resonates with both you and your partner.'}</p>
        </div>
        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="name">Your name</label>
          <input id="name" name="name" type="text" placeholder="Your name" autoComplete="name" required maxLength="80" />
          {error && <p className="message" role="alert">{error}</p>}
          <button className="peach-button" type="submit" disabled={submitting}>{submitting ? 'Joining…' : <>{joining ? 'Join session' : 'Continue'} <span aria-hidden="true">→</span></>}</button>
        </form>
        <p className="login-footer">
          For now this is a simple name-only session.
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
