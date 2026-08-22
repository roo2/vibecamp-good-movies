import React, { useCallback, useEffect, useState } from 'react'
import { TEST_DURATION_SECONDS } from './config/test.js'
import LandingPage from './screens/LandingPage.jsx'
import TestIntroPage from './screens/TestIntroPage.jsx'
import QuickfireTestPage from './screens/QuickfireTestPage.jsx'
import TestCompletePage from './screens/TestCompletePage.jsx'
import SessionLobbyPage from './screens/SessionLobbyPage.jsx'
import SessionWaitingPage from './screens/SessionWaitingPage.jsx'
import SeenItPage from './screens/SeenItPage.jsx'
import { loadAccess, startAccess } from './services/accessService.js'
import { submitMovieReaction } from './services/movieService.js'
import { submitTestResult } from './services/resultService.js'
import { beginResultsWait, continueWithoutMembers, createGroupSession, joinGroupSession, loadGroupSession, loadGroupSessionStatus, startGroupSession } from './services/groupSessionService.js'

const routes = new Set(['/', '/lobby', '/seen-it', '/test-intro', '/quickfire', '/complete', '/waiting'])

function currentRoute() {
  const route = window.location.hash.slice(1) || '/'
  return routes.has(route) || route.startsWith('/join/') ? route : '/'
}

function App() {
  const [route, setRoute] = useState(currentRoute)
  const [result, setResult] = useState(null)
  const [access, setAccess] = useState(loadAccess)
  const [groupSession, setGroupSession] = useState(loadGroupSession)
  const [sessionStatus, setSessionStatus] = useState(null)

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

  const handleMovieReaction = useCallback(async (filmId, reaction) => {
    await submitMovieReaction(access, filmId, reaction)
  }, [access])

  const handleComplete = useCallback(async (answers) => {
    if (!access) {
      navigate('/')
      return
    }
    await submitTestResult(access, answers, groupSession?.shareToken)
    setResult(answers)
    const status = await refreshSessionStatus()
    if (status?.host_user_id === access.user.id) await beginResultsWait(access, groupSession.shareToken)
    navigate('/waiting')
  }, [access, groupSession, navigate, refreshSessionStatus])

  const handleContinue = useCallback(async () => {
    await continueWithoutMembers(access, groupSession.shareToken)
    navigate('/complete')
  }, [access, groupSession, navigate])

  if (!access && route !== '/' && !route.startsWith('/join/')) {
    return <LandingPage onSignIn={handleSignIn} />
  }

  if (route === '/seen-it') {
    return <SeenItPage onSubmit={handleMovieReaction} onComplete={() => navigate('/test-intro')} />
  }

  if (route === '/lobby' && groupSession) {
    return <SessionLobbyPage access={access} groupSession={{ ...sessionStatus, share_token: groupSession.shareToken, host_user_id: sessionStatus?.host_user_id }} onStart={handleStartSession} />
  }

  if (route === '/waiting' && sessionStatus) {
    return <SessionWaitingPage status={sessionStatus} isHost={sessionStatus.host_user_id === access.user.id} onContinue={handleContinue} />
  }

  if (route === '/test-intro') {
    return <TestIntroPage durationSeconds={TEST_DURATION_SECONDS} onContinue={() => navigate('/quickfire')} />
  }

  if (route === '/quickfire') {
    return <QuickfireTestPage durationSeconds={TEST_DURATION_SECONDS} onComplete={handleComplete} />
  }

  if (route === '/complete') {
    return <TestCompletePage answers={result} onStartOver={() => navigate('/')} />
  }

  return <LandingPage onSignIn={handleSignIn} joining={route.startsWith('/join/')} />
}

export default App
