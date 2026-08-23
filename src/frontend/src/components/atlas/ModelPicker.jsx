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
          // Compared on scorer alone, two runs by the same model both read as
          // selected. The endpoint now returns one row per model, and this
          // matches the same way, so the two cannot drift apart again.
          const active = model.scorer === selected
          return (
            <button
              key={model.scorer}
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
              {/* A model with verdicts but no names has been scored and not yet
                  analysed, which is a different state from having no data — the
                  button stays, because picking it should say so rather than
                  hide the run. */}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default ModelPicker
