import React, { useState } from 'react'

function SessionWaitingPage({ status, isHost, canEditAnswer, onBack, onContinue }) {
  const [error, setError] = useState(null)
  // Who is "you" without being told: the host knows they are the host, so the
  // host row is you if you are one and them if you are not. Position in the list
  // is not identity — the host is not always first.
  const isYou = (member) => (member.user.id === status.host_user_id) === isHost
  const complete = status.members.filter((member) => member.completed_at)
  // Only THEY can be pending here. You reached this screen by finishing, and a
  // screen that says "waiting for your partner" because it counted you among the
  // unfinished would be waiting for the person reading it.
  const pending = status.members.filter((member) => !member.completed_at && !isYou(member))

  async function handleContinue() {
    setError(null)
    try { await onContinue() } catch (requestError) { setError(requestError.message) }
  }

  async function handleBack() {
    setError(null)
    try { await onBack() } catch (requestError) { setError(requestError.message) }
  }

  return (
    <main className="app-page waiting-page">
      <section className="phone-screen session-screen waiting-screen" aria-label="Waiting for your friend">
        <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Something Good To Watch</span></div>
        <div className="session-content">
          <p className="screen-label">Almost there</p>
          <h1>{pending.length ? <>Waiting for<br /><em>your friend.</em></> : <>You’re both<br /><em>done.</em></>}</h1>
          <p className="screen-copy">{pending.length
            ? 'They are still answering. Nothing is shared until you have both finished.'
            : 'Neither of you saw the other’s answers. Here is what you have in common.'}</p>
          <div className="member-list">{status.members.map((member) => (
            <div key={member.user.id}><span>{member.completed_at ? '✓' : '○'}</span>{isYou(member) ? 'You' : 'Your friend'}<small>{member.completed_at ? 'Ready' : 'Still answering'}</small></div>
          ))}</div>
          {error && <p className="message" role="alert">{error}</p>}
        </div>
        {/* Nothing to press when you are both done — that page moves on by
            itself. This button is only ever the way out of a partner who
            stopped answering, which is a decision and stays a button. */}
        {isHost && pending.length > 0 && status.can_continue_without_members
          && <button className="peach-button" type="button" onClick={handleContinue}>Carry on without them <span aria-hidden="true">→</span></button>}
        {pending.length === 0 && <p className="login-footer">Reading you both…</p>}
        {isHost && pending.length > 0 && !status.can_continue_without_members && <p className="login-footer">If they get stuck, you can carry on without them after 10 minutes.</p>}
      </section>
    </main>
  )
}

export default SessionWaitingPage
