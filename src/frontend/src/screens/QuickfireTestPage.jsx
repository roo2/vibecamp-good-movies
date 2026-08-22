import React, { useEffect, useState } from 'react'
import Countdown from '../components/Countdown.jsx'
import { loadTestQuestions } from '../services/testService.js'

function QuickfireTestPage({ durationSeconds, onComplete }) {
  const [questions, setQuestions] = useState([])
  const [answers, setAnswers] = useState({})
  const [questionIndex, setQuestionIndex] = useState(0)
  const [secondsRemaining, setSecondsRemaining] = useState(durationSeconds)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    loadTestQuestions()
      .then((items) => active && setQuestions(items))
      .catch(() => active && setError('Questions could not be loaded. Please try again.'))
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (questions.length === 0 || secondsRemaining === 0) return undefined
    const interval = window.setInterval(() => {
      setSecondsRemaining((seconds) => Math.max(seconds - 1, 0))
    }, 1000)
    return () => window.clearInterval(interval)
  }, [questions.length, secondsRemaining])

  useEffect(() => {
    if (questions.length > 0 && secondsRemaining === 0) onComplete(answers)
  }, [answers, onComplete, questions.length, secondsRemaining])

  if (error) {
    return <main className="flow-shell"><p className="error-message">{error}</p></main>
  }

  if (questions.length === 0) {
    return <main className="flow-shell"><p className="loading-message">Preparing your questions…</p></main>
  }

  const question = questions[questionIndex]
  const selectedAnswer = answers[question.id]
  const isLastQuestion = questionIndex === questions.length - 1

  function selectAnswer(option) {
    setAnswers((current) => ({ ...current, [question.id]: option }))
  }

  function continueTest() {
    if (isLastQuestion) {
      onComplete(answers)
      return
    }
    setQuestionIndex((index) => index + 1)
  }

  return (
    <main className="flow-shell quiz-shell">
      <section className="quiz-card" aria-live="polite">
        <header className="quiz-header">
          <div><p className="eyebrow">Moral Atlas</p><p className="question-count">Question {questionIndex + 1} of {questions.length}</p></div>
          <Countdown secondsRemaining={secondsRemaining} />
        </header>
        <div className="progress-track" aria-hidden="true"><div style={{ width: `${((questionIndex + 1) / questions.length) * 100}%` }} /></div>
        <p className="step-label">Go with your first instinct</p>
        <h1 className="question-prompt">{question.prompt}</h1>
        <div className="options" role="radiogroup" aria-label={question.prompt}>
          {question.options.map((option) => (
            <button className={`option ${selectedAnswer === option ? 'selected' : ''}`} type="button" role="radio" aria-checked={selectedAnswer === option} key={option} onClick={() => selectAnswer(option)}>
              <span className="option-marker" aria-hidden="true" />{option}
            </button>
          ))}
        </div>
        <button className="primary-button" type="button" disabled={!selectedAnswer} onClick={continueTest}>{isLastQuestion ? 'See my result' : 'Next question'} <span aria-hidden="true">→</span></button>
      </section>
    </main>
  )
}

export default QuickfireTestPage
