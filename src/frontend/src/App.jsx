import React, { useCallback, useEffect, useState } from 'react'
import { TEST_DURATION_SECONDS } from './config/test.js'
import LandingPage from './screens/LandingPage.jsx'
import TestIntroPage from './screens/TestIntroPage.jsx'
import QuickfireTestPage from './screens/QuickfireTestPage.jsx'
import TestCompletePage from './screens/TestCompletePage.jsx'
import SeenItPage from './screens/SeenItPage.jsx'
import { loadAccess, startAccess } from './services/accessService.js'
import { submitMovieReaction } from './services/movieService.js'
import { submitTestResult } from './services/resultService.js'

const routes = new Set(['/', '/seen-it', '/test-intro', '/quickfire', '/complete'])

function currentRoute() {
  const route = window.location.hash.slice(1) || '/'
  return routes.has(route) ? route : '/'
}

function App() {
  const [route, setRoute] = useState(currentRoute)
  const [result, setResult] = useState(null)
  const [access, setAccess] = useState(loadAccess)

  useEffect(() => {
    const handleHashChange = () => setRoute(currentRoute())
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  const navigate = useCallback((nextRoute) => {
    window.location.hash = nextRoute
  }, [])

  const handleSignIn = useCallback(async (name) => {
    const nextAccess = await startAccess(name)
    setAccess(nextAccess)
    navigate('/seen-it')
  }, [navigate])

  const handleMovieReaction = useCallback(async (filmId, reaction) => {
    await submitMovieReaction(access, filmId, reaction)
    navigate('/test-intro')
  }, [access, navigate])

  const handleComplete = useCallback(async (answers) => {
    if (!access) {
      navigate('/')
      return
    }
    await submitTestResult(access, answers)
    setResult(answers)
    navigate('/complete')
  }, [access, navigate])

  if (!access && route !== '/') {
    return <LandingPage onSignIn={handleSignIn} />
  }

  if (route === '/seen-it') {
    return <SeenItPage onSubmit={handleMovieReaction} />
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

  return <LandingPage onSignIn={handleSignIn} />
}

export default App
