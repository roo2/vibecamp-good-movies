import React, { useCallback, useEffect, useRef, useState } from 'react'
import LandingPage from './screens/LandingPage.jsx'
import TestCompletePage from './screens/TestCompletePage.jsx'
import SessionLobbyPage from './screens/SessionLobbyPage.jsx'
import SessionWaitingPage from './screens/SessionWaitingPage.jsx'
import SeenItPage from './screens/SeenItPage.jsx'
import ShortlistPage from './screens/ShortlistPage.jsx'
import MatchPage from './screens/MatchPage.jsx'
import AtlasPage from './screens/AtlasPage.jsx'
import CorpusPage from './screens/CorpusPage.jsx'
import { loadAccess, startAccess } from './services/accessService.js'
import { submitMovieReaction } from './services/movieService.js'
import { submitTestResult } from './services/resultService.js'
import { beginResultsWait, continueWithoutMembers, createGroupSession, joinGroupSession, loadGroupSession, loadGroupSessionStatus, startGroupSession } from './services/groupSessionService.js'

const routes = new Set(['/', '/atlas', '/corpus', '/lobby', '/seen-it', '/complete', '/shortlist', '/match', '/waiting'])

// The dataset explorer is the public face of the work: it reads a published
// file, holds nothing about anyone, and is the thing you show someone before
// they have any reason to sign in. So it sits outside the session guard.
const PUBLIC_ROUTES = new Set(['/atlas', '/corpus'])

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
  const [shortlist, setShortlist] = useState([])
  // How many agreed films they have already been shown, so "keep looking"
  // returns to swiping instead of bouncing straight back to the same three.
  const [matchesSeen, setMatchesSeen] = useState(0)

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

  // Alone and together are the same machinery with one fewer person in it: a
  // solo run is a group of one, so it needs no lobby to invite nobody to and no
  // wait for nobody to finish. It starts itself and goes straight to the films.
  const handleStart = useCallback(async (mode) => {
    const nextAccess = await startAccess()
    setAccess(nextAccess)
    const joinToken = currentRoute().startsWith('/join/') ? currentRoute().split('/')[2] : null
    if (joinToken) return
    const nextGroupSession = await createGroupSession(nextAccess)
    setGroupSession({ shareToken: nextGroupSession.share_token })
    if (mode === 'solo') {
      await startGroupSession(nextAccess, nextGroupSession.share_token)
      navigate('/seen-it')
      return
    }
    navigate('/lobby')
  }, [navigate])

  const refreshSessionStatus = useCallback(async () => {
    if (!access || !groupSession?.shareToken) return null
    const nextStatus = await loadGroupSessionStatus(access, groupSession.shareToken)
    setSessionStatus(nextStatus)
    return nextStatus
  }, [access, groupSession])

  // Both waiting screens move on by themselves.
  //
  // They used to wait for the host to press a button, which meant a couple who
  // were both ready sat looking at a screen until whichever of them held the
  // "host" role — a thing neither of them knows they are — noticed. Every one of
  // those presses had exactly one sensible answer, so the screen gives it.
  //
  // The guard is a ref rather than state: the poll runs every four seconds and
  // starting a session twice, or continuing one twice, is worse than waiting.
  const advancing = useRef(false)

  useEffect(() => {
    if (route !== '/waiting' && route !== '/lobby') return undefined
    async function updateStatus() {
      const nextStatus = await refreshSessionStatus()
      if (!nextStatus) return
      const isHost = nextStatus.host_user_id === access?.user?.id
      const members = nextStatus.members || []
      const everyoneReady = members.length > 0 && members.every((member) => member.completed_at)

      if (route === '/lobby') {
        if (nextStatus.status === 'in_progress') { navigate('/seen-it'); return }
        // Your partner is here and nothing else has to happen first.
        if (isHost && nextStatus.status === 'lobby' && members.length > 1 && !advancing.current) {
          advancing.current = true
          try {
            await startGroupSession(access, groupSession.shareToken)
            navigate('/seen-it')
          } finally {
            advancing.current = false
          }
        }
        return
      }

      if (nextStatus.status === 'results_started' || everyoneReady) {
        // Only the host may end the wait for the session, but neither person
        // should be made to sit through the other's round trip to do it.
        if (isHost && nextStatus.status !== 'results_started' && !advancing.current) {
          advancing.current = true
          continueWithoutMembers(access, groupSession.shareToken)
            .catch(() => {})
            .finally(() => { advancing.current = false })
        }
        navigate('/complete')
      }
    }
    updateStatus()
    const timer = window.setInterval(updateStatus, 4000)
    return () => window.clearInterval(timer)
  }, [route, refreshSessionStatus, navigate, access, groupSession])

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
    // Nobody else in the room: there is nothing to wait for, and a waiting screen
    // that says "waiting for your partner" to someone who has none is a bug with
    // a friendly face on it.
    const members = status?.members || []
    const everyoneReady = members.length > 0 && members.every((member) => member.completed_at)
    // Nobody else in the room, or nobody left to wait for: either way there is
    // nothing a waiting screen could tell them.
    if (members.length <= 1 || everyoneReady) {
      if (status?.host_user_id === access.user.id && members.length > 1) {
        continueWithoutMembers(access, groupSession.shareToken).catch(() => {})
      }
      navigate('/complete')
      return
    }
    if (status?.host_user_id === access.user.id) await beginResultsWait(access, groupSession.shareToken)
    navigate('/waiting')
  }, [access, groupSession, navigate, refreshSessionStatus])

  const handleContinue = useCallback(async () => {
    await continueWithoutMembers(access, groupSession.shareToken)
    navigate('/complete')
  }, [access, groupSession, navigate])

  const handleKeepLooking = useCallback(() => {
    setMatchesSeen(shortlist.length)
    navigate('/shortlist')
  }, [navigate, shortlist])

  const handleStartOver = useCallback(() => {
    setShortlist([])
    setMatchesSeen(0)
    navigate('/')
  }, [navigate])

  if (route === '/atlas') {
    return <AtlasPage onBack={() => navigate('/')} access={access} />
  }

  if (route === '/corpus') {
    return <CorpusPage onBack={() => navigate('/')} />
  }

  if (!access && route !== '/' && !PUBLIC_ROUTES.has(route) && !route.startsWith('/join/')) {
    return <LandingPage onStart={handleStart} />
  }

  if (route === '/seen-it') {
    // Reacting to the last film is the end of the test now that the blind pairs
    // are gone. The empty answer map is not a placeholder for something missing:
    // there are no pair answers to send, and submitting is still what marks this
    // member complete for the others waiting on them.
    return <SeenItPage access={access} shareToken={groupSession?.shareToken} onSubmit={handleMovieReaction} onComplete={() => handleComplete({})} />
  }

  if (route === '/lobby' && groupSession) {
    return <SessionLobbyPage access={access} groupSession={{ ...sessionStatus, share_token: groupSession.shareToken, host_user_id: sessionStatus?.host_user_id }} onStart={handleStartSession} />
  }

  if (route === '/waiting' && sessionStatus) {
    return <SessionWaitingPage status={sessionStatus} isHost={sessionStatus.host_user_id === access.user.id} canEditAnswer={false} onContinue={handleContinue} />
  }

  if (route === '/complete') {
    return <TestCompletePage access={access} shareToken={groupSession?.shareToken} onContinue={() => navigate('/shortlist')} />
  }
  // One person is a room of one — the copy differs, the machinery does not.
  const solo = (sessionStatus?.members?.length || 1) <= 1

  if (route === '/shortlist') {
    return <ShortlistPage access={access} shareToken={groupSession?.shareToken} matchesSeen={matchesSeen} solo={solo}
                          onDone={(films) => { setShortlist(films); navigate('/match') }} />
  }
  if (route === '/match') {
    return <MatchPage access={access} shareToken={groupSession?.shareToken} films={shortlist} solo={solo} onKeepLooking={handleKeepLooking} onStartOver={handleStartOver} />
  }

  return <LandingPage onStart={handleStart} joining={route.startsWith('/join/')} />
}

export default App
