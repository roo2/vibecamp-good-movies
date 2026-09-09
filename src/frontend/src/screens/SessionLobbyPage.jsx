import React, { useEffect, useMemo, useState } from 'react'

function SessionLobbyPage({ access, groupSession, onStart }) {
  const [copied, setCopied] = useState(false)
  const [failed, setFailed] = useState(false)
  const joinUrl = useMemo(() => `${window.location.origin}${window.location.pathname}#/join/${groupSession.share_token}`, [groupSession.share_token])
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(joinUrl)}`
  const isHost = groupSession.host_user_id === access.user.id
  const host = groupSession.members?.find((member) => member.user.id === groupSession.host_user_id)
  const guestCount = Math.max(0, (groupSession.members?.length || 1) - 1)

  useEffect(() => {
    setCopied(false)
    setFailed(false)
  }, [joinUrl])

  // The share sheet where there is one, the clipboard where there is not.
  //
  // `navigator.share` is the phone's own send-to-a-person dialog — Messages,
  // WhatsApp, whatever they actually use — and this is the one thing on the
  // screen whose whole purpose is to reach one specific person. It is on iOS
  // Safari and Android Chrome and absent from most desktop browsers, so it is
  // feature-detected rather than assumed, and the fallback is the behaviour
  // that was here before.
  //
  // A share sheet dismissed without sending rejects with AbortError, which is
  // not a failure and must not be reported as one.
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function'

  async function sendLink() {
    if (canShare) {
      try {
        await navigator.share({
          title: 'Something Good To Watch',
          text: 'Find a film we both want to watch',
          url: joinUrl,
        })
        return
      } catch (error) {
        if (error?.name === 'AbortError') return
        // Anything else — a browser that lists the API and refuses it, a
        // context it will not run in — falls through to the clipboard rather
        // than leaving the button dead.
      }
    }
    try {
      await navigator.clipboard.writeText(joinUrl)
      setCopied(true)
    } catch {
      setFailed(true)
    }
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
            <button className="link-button share-button" type="button" onClick={sendLink}>
              {/* The system share glyph, drawn rather than an emoji: an emoji
                  renders as a different picture on every platform, and this one
                  has to read as the button the operating system is about to
                  open. Swapped for a clipboard where there is no sheet. */}
              <svg className="share-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                {canShare ? (
                  <>
                    <path d="M12 3v12" />
                    <path d="M8 7l4-4 4 4" />
                    <path d="M5 13v6a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-6" />
                  </>
                ) : (
                  <>
                    <rect x="9" y="3" width="9" height="12" rx="1.5" />
                    <path d="M15 18v2a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h2" />
                  </>
                )}
              </svg>
              {copied ? 'Link copied' : canShare ? 'Send them the link' : 'Copy the link for them'}
            </button>
            {failed && (
              <p className="screen-copy" role="alert">
                That did not copy. The link is in the address bar — send them that.
              </p>
            )}
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
