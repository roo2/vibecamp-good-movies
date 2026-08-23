import React from 'react'
import CompassScreen from './CompassScreen.jsx'

function TestCompletePage({ access, shareToken, onContinue }) {
  return <CompassScreen access={access} shareToken={shareToken} onContinue={onContinue} />
}

export default TestCompletePage
