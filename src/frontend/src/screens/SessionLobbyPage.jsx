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
      <section className="phone-screen session-screen" aria-label="Session lobby">
        <div className="brand"><span className="brand-mark" aria-hidden="true">⊕</span><span>Moral Atlas</span></div>
        <div className="session-content">
          <p className="screen-label">{isHost ? 'Your shared session' : 'You joined a session'}</p>
          {isHost ? <>
            <h1>Invite your<br /><em>movie people.</em></h1>
            <p className="screen-copy">They can scan the code or use the link, then complete their own path.</p>
            <img className="session-qr" src={qrUrl} alt="QR code for joining this session" />
            <button className="link-button" type="button" onClick={copyLink}>{copied ? 'Link copied' : 'Copy invite link'}</button>
            <div className="lobby-members" aria-live="polite">
              <strong>{guestCount ? `${guestCount} person${guestCount === 1 ? '' : 's'} joined` : 'Waiting for people to join'}</strong>
              {groupSession.members?.map((member) => <span key={member.user.id}>{member.user.name}{member.user.id === access.user.id ? ' (you)' : ''}</span>)}
            </div>
          </> : <>
            <h1>Joining<br /><em>{host?.user.name || 'their'}’s session.</em></h1>
            <p className="screen-copy">You’re in. {host?.user.name || 'The host'} will start when everyone is ready.</p>
          </>}
        </div>
        {isHost ? <button className="peach-button" type="button" onClick={onStart}>Start session <span aria-hidden="true">→</span></button> : <p className="login-footer">Waiting for the host to start.</p>}
      </section>
    </main>
  )
}

export default SessionLobbyPage
