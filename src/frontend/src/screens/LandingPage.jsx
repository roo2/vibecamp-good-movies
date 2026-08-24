import React from 'react'

import { APP_VERSION } from '../config/version'

// The way in, and the only place the two paths diverge.
//
// There is no name field. Asking two people on a sofa to type their names was a
// toll booth in front of a ninety-second quiz, and nothing downstream needed the
// answer: there are at most two of you, and "you" and "your partner" tell you
// apart perfectly well.
//
// Alone is a real way to use this, not a degraded one. The instrument reads one
// person perfectly well — it is what it does before it compares anybody — so the
// solo path gets its own button and its own sentence rather than being the thing
// you do when nobody else is around.
function LandingPage({ onStart, joining = false }) {
  const [error, setError] = React.useState(null)
  const [starting, setStarting] = React.useState(null)

  async function begin(mode) {
    setError(null)
    setStarting(mode)
    try {
      await onStart(mode)
    } catch (startError) {
      setError(startError.message)
      setStarting(null)
    }
  }

  return (
    <main className="app-page login-page">
      <section className="phone-screen login-screen" aria-label="Start">
        <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Something Good To Watch</span></div>
        <div className="login-content">
          <p className="screen-label">{joining ? 'A friend invited you' : '90 seconds · no sign-up'}</p>
          {/* Only the word that carries the promise is lit. Emphasis on a whole
              phrase is emphasis on nothing — the eye needs one place to land. */}
          <h1>{joining ? <>Watch something<br /><em>together.</em></> : <>Find something<br /><em>good</em> to watch.</>}</h1>
          <p className="screen-copy">{joining
            ? 'They are already answering. You will each answer on your own — neither of you sees the other’s answers until the end.'
            : 'Every film argues for something. Spend ninety seconds on films you already know, and we will read what you believe out of what you liked — then find films that argue for it.'}</p>
        </div>

        {error && <p className="message" role="alert">{error}</p>}

        {joining ? (
          <div className="start-choices">
            <button className="peach-button" type="button" disabled={starting} onClick={() => begin('join')}>
              {starting ? 'Joining…' : <>Join them <span aria-hidden="true">→</span></>}
            </button>
          </div>
        ) : (
          <div className="start-choices">
            <button className="peach-button" type="button" disabled={starting} onClick={() => begin('pair')}>
              {starting === 'pair' ? 'Setting up…' : <>With a friend <span aria-hidden="true">→</span></>}
            </button>
            <button className="start-secondary" type="button" disabled={starting} onClick={() => begin('solo')}>
              {starting === 'solo' ? 'Starting…' : 'Just me'}
              <small>Find out what your taste says about you</small>
            </button>
          </div>
        )}

        <p className="login-footer">
          {joining ? 'No sign-up — they are waiting for you.' : 'Nothing to sign up for, and no names needed.'}
          <br />
          <a className="quiet-link" href="#/corpus">Look up a film →</a>
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
