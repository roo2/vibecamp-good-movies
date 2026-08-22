import React from 'react'

function LandingPage({ onSignIn }) {
  function handleSubmit(event) {
    event.preventDefault()
    onSignIn()
  }

  return (
    <main className="shell landing-shell">
      <section className="hero" aria-label="Moral Atlas introduction">
        <p className="eyebrow">Moral Atlas</p>
        <h1>Find the stories you’ll agree about.</h1>
        <p className="intro">A better way to choose what to watch together — based on what films believe, not just what genre they are.</p>
        <p className="aside-note">Two people. One shared story map.</p>
      </section>

      <section className="card" aria-label="Sign in">
        <div className="card-heading">
          <p className="card-kicker">Welcome back</p>
          <h2>Sign in to your atlas</h2>
          <p className="muted">Your watch arguments are waiting.</p>
        </div>
        <form onSubmit={handleSubmit}>
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" placeholder="you@example.com" required />
          <label htmlFor="password">Password</label>
          <input id="password" name="password" type="password" placeholder="••••••••" required />
          <button type="submit">Sign in <span aria-hidden="true">→</span></button>
        </form>
        <p className="fine-print">Don’t have an account? <a href="#create">Create one</a></p>
        <p className="demo-note">Demo only — sign in is not connected yet.</p>
      </section>
    </main>
  )
}

export default LandingPage
