import React, { useEffect, useRef, useState } from 'react'
import FlowProgress from '../components/FlowProgress.jsx'
import { loadTestQuestions } from '../services/testService.js'

const EMPTY_ANSWERS = {}

function QuickfireTestPage({ access, shareToken, initialAnswers = EMPTY_ANSWERS, startAtLast = false, onComplete }) {
  const [questions, setQuestions] = useState([])
  const [answers, setAnswers] = useState(initialAnswers)
  const [questionIndex, setQuestionIndex] = useState(0)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const completedRef = useRef(false)

  useEffect(() => {
    let active = true
    loadTestQuestions(access, shareToken).then((items) => {
      if (!active) return
      setQuestions(items)
      if (startAtLast) setQuestionIndex(Math.max(0, items.length - 1))
    }).catch(() => active && setError('Stories could not be loaded. Please try again.'))
    return () => { active = false }
  }, [access, shareToken, startAtLast])

  if (error) return <main className="app-page"><p className="message">{error}</p></main>
  if (questions.length === 0) return <main className="app-page"><p className="message">Preparing your questions…</p></main>

  const question = questions[questionIndex]
  const isLastQuestion = questionIndex === questions.length - 1

  async function completeTest(finalAnswers) {
    if (completedRef.current) return
    completedRef.current = true
    setSubmitting(true)
    try {
      await onComplete(finalAnswers)
    } catch (submissionError) {
      completedRef.current = false
      setSubmitting(false)
      setError(submissionError.message)
    }
  }

  function submitChoice(choiceId) {
    if (completedRef.current) return
    const nextAnswers = { ...answers, [question.id]: choiceId }
    setAnswers(nextAnswers)
    if (isLastQuestion) void completeTest(nextAnswers)
    else setQuestionIndex((index) => index + 1)
  }

  return (
    <main className="app-page quickfire-page">
      <section className="phone-screen fork-screen" aria-live="polite">
        <FlowProgress current={5 + questionIndex + 1} onBack={questionIndex > 0 ? () => setQuestionIndex((index) => index - 1) : undefined} backLabel="Previous question" />
        <div className="fork-heading"><p className="screen-label">Quick reaction</p><h1>Which one would you rather watch?</h1></div>
        <div className="choice-stack" aria-label="Choose a story">
          {question.choices.map((choice, index) => (
            <React.Fragment key={choice.id}>
              {index === 1 && <div className="or-divider"><i />or<i /></div>}
              <button className={`story-choice ${index === 1 ? 'accent-choice' : ''} ${answers[question.id] === choice.id ? 'selected-story' : ''}`} type="button" aria-pressed={answers[question.id] === choice.id} disabled={submitting} onClick={() => submitChoice(choice.id)}>
                <span className="choice-label"><b>{index === 0 ? 'A' : 'B'}</b>{choice.label}</span><strong>{choice.copy}</strong>
              </button>
            </React.Fragment>
          ))}
        </div>
        <div className="fork-footer"><button className="neither-button" type="button" disabled={submitting} onClick={() => submitChoice('neither')}>Neither — show me another pair</button><p>No titles, no posters, no cast. Just the shape of the story, so you answer honestly.</p></div>
      </section>
    </main>
  )
}

export default QuickfireTestPage
