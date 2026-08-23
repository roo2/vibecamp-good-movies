import React, { useState } from 'react'
import FlowProgress, { WAITING_STEP } from '../components/FlowProgress.jsx'

function SessionWaitingPage({ status, isHost, canEditAnswer, onBack, onContinue }) {
  const [error, setError] = useState(null)
  const complete = status.members.filter((member) => member.completed_at)
  const pending = status.members.filter((member) => !member.completed_at)

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
      <section className="phone-screen session-screen waiting-screen" aria-label="Waiting for session results">
        <FlowProgress current={WAITING_STEP} onBack={canEditAnswer ? handleBack : undefined} backLabel="Change your last answer" />
        <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Something Good To Watch</span></div>
        <div className="session-content">
          <p className="screen-label">Shared session</p>
          <h1>{pending.length ? <>Waiting for<br /><em>the others.</em></> : <>Everyone’s<br /><em>ready.</em></>}</h1>
          <p className="screen-copy">{complete.length} of {status.members.length} participant{status.members.length === 1 ? '' : 's'} completed.</p>
          <div className="member-list">{status.members.map((member) => <div key={member.user.id}><span>{member.completed_at ? '✓' : '○'}</span>{member.user.name}<small>{member.completed_at ? 'Ready' : 'In progress'}</small></div>)}</div>
          {error && <p className="message" role="alert">{error}</p>}
        </div>
        {isHost && (pending.length === 0 || status.can_continue_without_members) && <button className="peach-button" type="button" onClick={handleContinue}>See joint result <span aria-hidden="true">→</span></button>}
        {isHost && pending.length > 0 && !status.can_continue_without_members && <p className="login-footer">You can continue without unfinished people after 10 minutes.</p>}
      </section>
    </main>
  )
}

export default SessionWaitingPage
