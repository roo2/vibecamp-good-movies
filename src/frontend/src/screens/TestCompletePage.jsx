import React from 'react'
import CompassScreen from './CompassScreen.jsx'

function TestCompletePage({ access, onStartOver }) {
  return <CompassScreen access={access} onContinue={onStartOver} />
}

export default TestCompletePage
