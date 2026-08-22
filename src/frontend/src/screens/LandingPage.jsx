import React from 'react'

function LandingPage({ onSignIn }) {
  function handleSubmit(event) {
    event.preventDefault()
    onSignIn()
  }

  return (
    <main className="app-page login-page">
      <section className="phone-screen login-screen" aria-label="Sign in">
        <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Moral Atlas</span></div>
        <div className="login-content">
          <p className="screen-label">Welcome back</p>
          <h1>Find your way<br />back to the <em>stories.</em></h1>
          <p className="screen-copy">Sign in to return to the map you and your people are building together.</p>
        </div>
        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" placeholder="you@example.com" required />
          <label htmlFor="password">Password</label>
          <input id="password" name="password" type="password" placeholder="••••••••" required />
          <button className="peach-button" type="submit">Sign in <span aria-hidden="true">→</span></button>
        </form>
        <p className="login-footer">Demo only — sign in is not connected yet.</p>
      </section>
    </main>
  )
}

export default LandingPage
