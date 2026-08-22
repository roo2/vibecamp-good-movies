import React from 'react'
import CompassScreen from './CompassScreen.jsx'

function TestCompletePage({ answers, onStartOver }) {
  return <CompassScreen answers={answers} onContinue={onStartOver} />
}

export default TestCompletePage
