import React from 'react'

function TestCompletePage({ answers, onStartOver }) {
  const answerCount = Object.keys(answers || {}).length
  return (
    <main className="flow-shell">
      <section className="flow-card complete-card">
        <p className="eyebrow">Moral Atlas</p>
        <p className="step-label">All done</p>
        <h1>That’s your first sketch.</h1>
        <p className="flow-copy">You answered {answerCount} quick-fire questions. When the backend is connected, this is where we’ll turn those instincts into your story map.</p>
        <button className="primary-button" type="button" onClick={onStartOver}>Back to the start</button>
      </section>
    </main>
  )
}

export default TestCompletePage
