import React, { useEffect, useMemo, useState } from 'react'

function SessionLobbyPage({ access, groupSession, onStart }) {
  const [copied, setCopied] = useState(false)
  const joinUrl = useMemo(() => `${window.location.origin}${window.location.pathname}#/join/${groupSession.share_token}`, [groupSession.share_token])
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(joinUrl)}`
  const isHost = groupSession.host_user_id === access.user.id
  const host = groupSession.members?.find((member) => member.user.id === groupSession.host_user_id)
  const guestCount = Math.max(0, (groupSession.members?.length || 1) - 1)

  useEffect(() => {
    setCopied(false)
  }, [joinUrl])

  async function copyLink() {
    await navigator.clipboard.writeText(joinUrl)
    setCopied(true)
  }

  return (
    <main className="app-page">
      <section className="phone-screen session-screen" aria-label="Invite a friend">
        <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Something Good To Watch</span></div>
        <div className="session-content">
          <p className="screen-label">{isHost ? 'Step one of two' : 'You’re in'}</p>
          {isHost ? <>
            <h1>Now get<br /><em>a friend.</em></h1>
            <p className="screen-copy">
              This only works with two of you. Hand them your phone to scan the code, or
              send them the link — you will each answer on your own, without seeing what
              the other said.
            </p>
            <img className="session-qr" src={qrUrl} alt="QR code a friend can scan to join you" />
            <button className="link-button" type="button" onClick={copyLink}>{copied ? 'Link copied' : 'Copy the link for them'}</button>
            <div className="lobby-members" aria-live="polite">
              <strong>{guestCount ? 'They’re in' : 'Waiting for them to join…'}</strong>
              {groupSession.members?.map((member) => <span key={member.user.id}>{member.user.id === access.user.id ? 'You' : 'Your friend'}</span>)}
            </div>
          </> : <>
            <h1>You’re in<br /><em>with them.</em></h1>
            <p className="screen-copy">
              You’ll each answer separately, then we find the films you both want to watch.
              They start you off.
            </p>
          </>}
        </div>
        {/* No start button. The only sensible moment to begin is the moment the
            second person arrives, and the app knows when that is — the "host" is
            a role neither of them knows they hold, so waiting on them to press
            something was waiting on nobody in particular. The way out is for the
            person who never got a partner, not for the pair. */}
        {isHost
          ? guestCount
            ? <p className="login-footer">They’re here — starting you both off…</p>
            : <button className="link-button" type="button" onClick={onStart}>Start without them</button>
          : <p className="login-footer">Waiting for them to start you both off.</p>}
      </section>
    </main>
  )
}

export default SessionLobbyPage
