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
      <section className="phone-screen session-screen" aria-label="Invite your partner">
        <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Something Good To Watch</span></div>
        <div className="session-content">
          <p className="screen-label">{isHost ? 'Step one of two' : `You’re with ${host?.user.name || 'them'}`}</p>
          {isHost ? <>
            <h1>Now get<br /><em>your partner.</em></h1>
            <p className="screen-copy">
              This only works with two of you. Hand them your phone to scan the code, or
              send them the link — you will each answer on your own, without seeing what
              the other said.
            </p>
            <img className="session-qr" src={qrUrl} alt="QR code your partner can scan to join you" />
            <button className="link-button" type="button" onClick={copyLink}>{copied ? 'Link copied' : 'Copy the link for them'}</button>
            <div className="lobby-members" aria-live="polite">
              <strong>{guestCount ? 'They’re in — you can start' : 'Waiting for them to join…'}</strong>
              {groupSession.members?.map((member) => <span key={member.user.id}>{member.user.name}{member.user.id === access.user.id ? ' (you)' : ''}</span>)}
            </div>
          </> : <>
            <h1>You’re in<br /><em>with {host?.user.name || 'them'}.</em></h1>
            <p className="screen-copy">
              You’ll each answer separately, then we find the films you both want to watch.
              {host?.user.name ? ` ${host.user.name} starts you off.` : ' They start you off.'}
            </p>
          </>}
        </div>
        {isHost ? <button className="peach-button" type="button" onClick={onStart} disabled={!guestCount}>{guestCount ? 'Start — both of us are here' : 'Waiting for them…'} <span aria-hidden="true">→</span></button> : <p className="login-footer">Waiting for them to start you both off.</p>}
      </section>
    </main>
  )
}

export default SessionLobbyPage
