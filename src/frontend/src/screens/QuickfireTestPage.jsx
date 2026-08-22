import React, { useEffect, useRef, useState } from 'react'
import { loadTestQuestions } from '../services/testService.js'

function QuickfireTestPage({ access, shareToken, onComplete }) {
  const [questions, setQuestions] = useState([])
  const [answers, setAnswers] = useState({})
  const [questionIndex, setQuestionIndex] = useState(0)
  const [error, setError] = useState(null)
  const completedRef = useRef(false)

  useEffect(() => {
    let active = true
    loadTestQuestions(access, shareToken).then((items) => active && setQuestions(items)).catch(() => active && setError('Stories could not be loaded. Please try again.'))
    return () => { active = false }
  }, [access, shareToken])

  if (error) return <main className="app-page"><p className="message">{error}</p></main>
  if (questions.length === 0) return <main className="app-page"><p className="message">Preparing your questions…</p></main>

  const question = questions[questionIndex]
  const isLastQuestion = questionIndex === questions.length - 1

  async function completeTest(finalAnswers) {
    if (completedRef.current) return
    completedRef.current = true
    try {
      await onComplete(finalAnswers)
    } catch (submissionError) {
      completedRef.current = false
      setError(submissionError.message)
    }
  }

  function submitChoice(choiceId) {
    const nextAnswers = { ...answers, [question.id]: choiceId }
    setAnswers(nextAnswers)
    if (isLastQuestion) void completeTest(nextAnswers)
    else setQuestionIndex((index) => index + 1)
  }

  return (
    <main className="app-page">
      <section className="phone-screen fork-screen" aria-live="polite">
        <header className="fork-header">
          <button className="back-button" type="button" aria-label="Previous question" disabled={questionIndex === 0} onClick={() => setQuestionIndex((index) => Math.max(0, index - 1))}>←</button>
          <div className="segment-progress" aria-label={`Question ${questionIndex + 1} of ${questions.length}`}>{questions.map((item, index) => <i className={index <= questionIndex ? 'active' : ''} key={item.id} />)}</div>
          <div className="quiz-meta"><span>{questionIndex + 1} / {questions.length}</span></div>
        </header>
        <div className="fork-heading"><p className="screen-label">Quick reaction</p><h1>Two stories. Which one would you rather watch?</h1></div>
        <div className="choice-stack" aria-label="Choose a story">
          {question.choices.map((choice, index) => (
            <React.Fragment key={choice.id}>
              {index === 1 && <div className="or-divider"><i />or<i /></div>}
              <button className={`story-choice ${index === 1 ? 'accent-choice' : ''} ${answers[question.id] === choice.id ? 'selected-story' : ''}`} type="button" aria-pressed={answers[question.id] === choice.id} onClick={() => submitChoice(choice.id)}>
                <span className="choice-label"><b>{index === 0 ? 'A' : 'B'}</b>{choice.label}</span><strong>{choice.copy}</strong>
              </button>
            </React.Fragment>
          ))}
        </div>
        <div className="fork-footer"><button className="neither-button" type="button" onClick={() => submitChoice('neither')}>Neither — show me another pair</button><p>No titles, no posters, no cast. Just the shape of the story, so you answer honestly.</p></div>
      </section>
    </main>
  )
}

export default QuickfireTestPage
