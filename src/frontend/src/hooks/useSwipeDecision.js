import { useEffect, useRef, useState } from 'react'

const SWIPE_THRESHOLD = 72
const MAX_DRAG = 140
const EXIT_DISTANCE = 520
const EXIT_DURATION_MS = 160

export default function useSwipeDecision({ disabled = false, onLeft, onRight }) {
  const startRef = useRef(null)
  const offsetRef = useRef(0)
  const decisionTimerRef = useRef(null)
  const [offset, setOffset] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [committed, setCommitted] = useState(false)

  useEffect(() => () => window.clearTimeout(decisionTimerRef.current), [])

  function reset() {
    startRef.current = null
    offsetRef.current = 0
    decisionTimerRef.current = null
    setOffset(0)
    setDragging(false)
    setCommitted(false)
  }

  function handlePointerDown(event) {
    if (disabled || committed || decisionTimerRef.current !== null || event.button !== 0) return
    startRef.current = { pointerId: event.pointerId, x: event.clientX }
    setDragging(true)
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  function handlePointerMove(event) {
    if (!startRef.current || startRef.current.pointerId !== event.pointerId) return
    const nextOffset = Math.max(-MAX_DRAG, Math.min(MAX_DRAG, event.clientX - startRef.current.x))
    offsetRef.current = nextOffset
    setOffset(nextOffset)
  }

  function handlePointerUp(event) {
    if (!startRef.current || startRef.current.pointerId !== event.pointerId) return
    const finalOffset = offsetRef.current
    const decision = finalOffset <= -SWIPE_THRESHOLD ? onLeft : finalOffset >= SWIPE_THRESHOLD ? onRight : null
    if (decision) {
      startRef.current = null
      setDragging(false)
      setCommitted(true)
      setOffset(finalOffset < 0 ? -EXIT_DISTANCE : EXIT_DISTANCE)
      decisionTimerRef.current = window.setTimeout(() => {
        reset()
        void decision()
      }, EXIT_DURATION_MS)
      return
    }
    reset()
  }

  const strength = Math.min(Math.abs(offset) / SWIPE_THRESHOLD, 1)
  return {
    direction: offset < -10 ? 'left' : offset > 10 ? 'right' : null,
    committed,
    strength,
    style: {
      transform: `translate3d(${offset}px, 0, 0) rotate(${offset / 28}deg)`,
      transition: dragging ? 'none' : undefined,
    },
    handlers: {
      onPointerDown: handlePointerDown,
      onPointerMove: handlePointerMove,
      onPointerUp: handlePointerUp,
      onPointerCancel: reset,
    },
  }
}
