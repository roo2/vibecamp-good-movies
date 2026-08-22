import React, { useCallback, useEffect, useState } from 'react'
import LandingPage from './screens/LandingPage.jsx'
import QuickfireTestPage from './screens/QuickfireTestPage.jsx'
import TestCompletePage from './screens/TestCompletePage.jsx'
import SessionLobbyPage from './screens/SessionLobbyPage.jsx'
import SessionWaitingPage from './screens/SessionWaitingPage.jsx'
import SeenItPage from './screens/SeenItPage.jsx'
import ShortlistPage from './screens/ShortlistPage.jsx'
import MatchPage from './screens/MatchPage.jsx'
import AtlasPage from './screens/AtlasPage.jsx'
import { loadAccess, startAccess } from './services/accessService.js'
import { submitMovieReaction } from './services/movieService.js'
import { submitTestResult } from './services/resultService.js'
import { beginResultsWait, continueWithoutMembers, createGroupSession, joinGroupSession, loadGroupSession, loadGroupSessionStatus, startGroupSession } from './services/groupSessionService.js'

const routes = new Set(['/', '/atlas', '/lobby', '/seen-it', '/quickfire', '/complete', '/shortlist', '/match', '/waiting'])

// The dataset explorer is the public face of the work: it reads a published
// file, holds nothing about anyone, and is the thing you show someone before
// they have any reason to sign in. So it sits outside the session guard.
const PUBLIC_ROUTES = new Set(['/atlas'])

function currentRoute() {
  // A route may carry a query — `#/atlas?film=parasite-2019` — so that a view
  // inside a page is linkable. Only the path decides which screen renders.
  const route = (window.location.hash.slice(1) || '/').split('?')[0]
  return routes.has(route) || route.startsWith('/join/') ? route : '/'
}

function App() {
  const [route, setRoute] = useState(currentRoute)
  const [access, setAccess] = useState(loadAccess)
  const [groupSession, setGroupSession] = useState(loadGroupSession)
  const [sessionStatus, setSessionStatus] = useState(null)
  const [selectedFilm, setSelectedFilm] = useState(null)

  const navigate = useCallback((nextRoute) => {
    window.location.hash = nextRoute
  }, [])

  useEffect(() => {
    const handleHashChange = () => setRoute(currentRoute())
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  useEffect(() => {
    const joinToken = route.startsWith('/join/') ? route.split('/')[2] : null
    if (!access || !joinToken) return
    joinGroupSession(access, joinToken)
      .then((nextGroupSession) => {
        setGroupSession({ shareToken: nextGroupSession.share_token })
        navigate('/lobby')
      })
      .catch(console.error)
  }, [access, navigate, route])

  const handleSignIn = useCallback(async (name) => {
    const nextAccess = await startAccess(name)
    setAccess(nextAccess)
    const joinToken = currentRoute().startsWith('/join/') ? currentRoute().split('/')[2] : null
    if (joinToken) return
    const nextGroupSession = await createGroupSession(nextAccess)
    setGroupSession({ shareToken: nextGroupSession.share_token })
    navigate('/lobby')
  }, [navigate])

  const refreshSessionStatus = useCallback(async () => {
    if (!access || !groupSession?.shareToken) return null
    const nextStatus = await loadGroupSessionStatus(access, groupSession.shareToken)
    setSessionStatus(nextStatus)
    return nextStatus
  }, [access, groupSession])

  useEffect(() => {
    if (route !== '/waiting' && route !== '/lobby') return undefined
    async function updateStatus() {
      const nextStatus = await refreshSessionStatus()
      if (route === '/lobby' && nextStatus?.status === 'in_progress') navigate('/seen-it')
      if (route === '/waiting' && nextStatus?.status === 'results_started') navigate('/complete')
    }
    updateStatus()
    const timer = window.setInterval(updateStatus, 4000)
    return () => window.clearInterval(timer)
  }, [route, refreshSessionStatus, navigate])

  const handleStartSession = useCallback(async () => {
    await startGroupSession(access, groupSession.shareToken)
    navigate('/seen-it')
  }, [access, groupSession, navigate])

  const handleMovieReaction = useCallback(async (filmId, reaction, shareToken) => {
    await submitMovieReaction(access, filmId, reaction, shareToken)
  }, [access])

  const handleComplete = useCallback(async (answers) => {
    if (!access) {
      navigate('/')
      return
    }
    await submitTestResult(access, answers, groupSession?.shareToken)
    const status = await refreshSessionStatus()
    if (status?.host_user_id === access.user.id) await beginResultsWait(access, groupSession.shareToken)
    navigate('/waiting')
  }, [access, groupSession, navigate, refreshSessionStatus])

  const handleContinue = useCallback(async () => {
    await continueWithoutMembers(access, groupSession.shareToken)
    navigate('/complete')
  }, [access, groupSession, navigate])

  if (route === '/atlas') {
    return <AtlasPage onBack={() => navigate('/')} />
  }

  if (!access && route !== '/' && !PUBLIC_ROUTES.has(route) && !route.startsWith('/join/')) {
    return <LandingPage onSignIn={handleSignIn} />
  }

  if (route === '/seen-it') {
    return <SeenItPage access={access} shareToken={groupSession?.shareToken} onSubmit={handleMovieReaction} onComplete={() => navigate('/quickfire')} />
  }

  if (route === '/lobby' && groupSession) {
    return <SessionLobbyPage access={access} groupSession={{ ...sessionStatus, share_token: groupSession.shareToken, host_user_id: sessionStatus?.host_user_id }} onStart={handleStartSession} />
  }

  if (route === '/waiting' && sessionStatus) {
    return <SessionWaitingPage status={sessionStatus} isHost={sessionStatus.host_user_id === access.user.id} onContinue={handleContinue} />
  }

  if (route === '/quickfire') {
    return <QuickfireTestPage access={access} shareToken={groupSession?.shareToken} onComplete={handleComplete} />
  }

  if (route === '/complete') {
    return <TestCompletePage access={access} onContinue={() => navigate('/shortlist')} />
  }
  if (route === '/shortlist') {
    return <ShortlistPage access={access} shareToken={groupSession?.shareToken} onDone={(film) => { setSelectedFilm(film); navigate('/match') }} />
  }
  if (route === '/match') {
    return <MatchPage access={access} shareToken={groupSession?.shareToken} film={selectedFilm} onContinue={() => navigate('/')} />
  }

  return <LandingPage onSignIn={handleSignIn} joining={route.startsWith('/join/')} />
}

export default App
