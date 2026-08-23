import React from 'react'

// There is no longer one answer to show, so the first thing this page asks is
// whose answer. Each model writes its own bank of propositions, scores films
// against it, and gets its own factors out — so the axes below are that model's
// reading of the corpus, not the corpus's own.
export function ModelPicker({ models, selected, onSelect }) {
  if (!models.length) return null

  return (
    <div className="model-picker">
      <span className="model-picker-label">Read by</span>
      <div className="model-picker-options" role="tablist">
        {models.map((model) => {
          const active = model.scorer === selected
          return (
            <button
              key={`${model.scorer}-${model.variant}`}
              type="button"
              role="tab"
              aria-selected={active}
              className={active ? 'model-option active' : 'model-option'}
              onClick={() => onSelect(model)}
              // Named because "8 axes" means nothing without knowing how much
              // the model actually engaged: a scorer that took a position on
              // six items a film and one that took 272 have not measured the
              // same corpus, whatever their factor counts say.
              title={`${model.films} films · ${model.items} items · ${model.verdicts.toLocaleString()} verdicts`}
            >
              <b>{model.scorer}</b>
              <span>
                {model.factors ? `${model.factors} axes` : 'not named yet'}
                {' · '}
                {model.films} films
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default ModelPicker
