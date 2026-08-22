import React from 'react'

function formatTime(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function Countdown({ secondsRemaining }) {
  return (
    <div className="countdown" aria-label={`${secondsRemaining} seconds remaining`}>
      <span>Time left</span>
      <strong>{formatTime(secondsRemaining)}</strong>
    </div>
  )
}

export { formatTime }
export default Countdown
