import React from 'react'

function LandingPage({ onSignIn }) {
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
        <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Moral Atlas</span></div>
        <div className="login-content">
          <p className="screen-label">Welcome back</p>
          <h1>Find your way<br />back to the <em>stories.</em></h1>
          <p className="screen-copy">Start with a name. You can add a fuller sign-in method later.</p>
        </div>
        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="name">Your name</label>
          <input id="name" name="name" type="text" placeholder="Ada" autoComplete="name" required maxLength="80" />
          {error && <p className="message" role="alert">{error}</p>}
          <button className="peach-button" type="submit" disabled={submitting}>{submitting ? 'Starting…' : <>Continue <span aria-hidden="true">→</span></>}</button>
        </form>
        <p className="login-footer">For now this is a simple name-only session.</p>
      </section>
    </main>
  )
}

export default LandingPage
