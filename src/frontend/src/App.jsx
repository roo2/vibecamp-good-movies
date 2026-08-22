import React, { useCallback, useEffect, useState } from 'react'
import { TEST_DURATION_SECONDS } from './config/test.js'
import LandingPage from './screens/LandingPage.jsx'
import TestIntroPage from './screens/TestIntroPage.jsx'
import QuickfireTestPage from './screens/QuickfireTestPage.jsx'
import TestCompletePage from './screens/TestCompletePage.jsx'

const routes = new Set(['/', '/test-intro', '/quickfire', '/complete'])

function currentRoute() {
  const route = window.location.hash.slice(1) || '/'
  return routes.has(route) ? route : '/'
}

function App() {
  const [route, setRoute] = useState(currentRoute)
  const [result, setResult] = useState(null)

  useEffect(() => {
    const handleHashChange = () => setRoute(currentRoute())
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  const navigate = useCallback((nextRoute) => {
    window.location.hash = nextRoute
  }, [])

  const handleComplete = useCallback((answers) => {
    setResult(answers)
    navigate('/complete')
  }, [navigate])

  if (route === '/test-intro') {
    return <TestIntroPage durationSeconds={TEST_DURATION_SECONDS} onContinue={() => navigate('/quickfire')} />
  }

  if (route === '/quickfire') {
    return <QuickfireTestPage durationSeconds={TEST_DURATION_SECONDS} onComplete={handleComplete} />
  }

  if (route === '/complete') {
    return <TestCompletePage answers={result} onStartOver={() => navigate('/')} />
  }

  return <LandingPage onSignIn={() => navigate('/test-intro')} />
}

export default App
