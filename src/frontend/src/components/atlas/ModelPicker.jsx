import React from 'react'

// There is no longer one answer to show, so the first thing this page asks is
// whose answer. But "whose" turned out to have two halves, and collapsing them
// hid the more interesting one: a reading is a set of QUESTIONS written by one
// model and ANSWERED by another, and the two roles fail differently.
//
// Measured across all four combinations of deepseek and dolphin: as a writer,
// dolphin produces 98 contested propositions out of 218 where deepseek produces
// 72 out of 297 — it asks the sharper questions. As a reader, deepseek recovers
// six axes from either bank while dolphin recovers one from its own and
// fourteen from deepseek's, most of them built on a handful of propositions.
// Same model, opposite failures, depending on whose questions it was handed.
export function ModelPicker({ models, selected, onSelect, withdrawn = [] }) {
  if (!models.length) return null

  return (
    <div className="model-picker">
      {/* "Read by" named one half of a two-part fact. Every button is now
          "who wrote the questions → who answered them", including the ones
          where those are the same model: naming the reader alone put deepseek
          first on both "deepseek" and "deepseek → dolphin", where it meant the
          answerer on one and the asker on the other. */}
      <span className="model-picker-label">Questions <i aria-hidden="true">→</i> answers</span>
      <div className="model-picker-options" role="tablist">
        {models.map((model) => {
          // Compared on the whole reading, not on the scorer: the same model
          // appears more than once now — once per bank it has read — and
          // matching on scorer alone lit all of its buttons at once.
          const active = model.reading_id === selected
          const ownWork = model.wrote === model.scorer
          return (
            <button
              key={model.reading_id}
              type="button"
              role="tab"
              aria-selected={active}
              className={active ? 'model-option active' : 'model-option'}
              onClick={() => onSelect(model)}
              // Named because "8 axes" means nothing without knowing how much
              // the model actually engaged: a scorer that took a position on
              // six items a film and one that took 272 have not measured the
              // same corpus, whatever their factor counts say.
              title={`${model.wrote} wrote the propositions, ${model.scorer} answered them`
                     + ` · ${model.films} films · ${model.items} items`
                     + ` · ${model.verdicts.toLocaleString()} verdicts`}
            >
              {/* Both halves, always. A model reading its own questions repeats
                  its name, which looks redundant and is the point: it says the
                  asker and the answerer are the same, which is a fact about the
                  reading rather than a formatting accident. */}
              <b>
                {model.wrote}
                <i aria-hidden="true">→</i>
                {model.scorer}
                {ownWork && <em> its own</em>}
              </b>
              <span>
                {model.factors ? `${model.factors} axes` : 'no axes'}
                {' · '}
                {model.films} films
              </span>
              {/* "no axes" rather than "not named yet": a model can reach zero
                  by never being analysed or by being analysed and finding
                  nothing, and from here those look identical. The first is a
                  chore and the second is a result, so the label claims neither
                  — the page itself says which once you pick the model. */}
            </button>
          )
        })}
      </div>
      {/* Said out loud. A model that was tried and could not do it is a result;
          removed silently, the page reads as though it was never asked. */}
      {withdrawn.map((model) => (
        <p className="model-withdrawn" key={model.scorer}>
          <b>{model.scorer}</b> was run and withdrawn — {model.reason}.
        </p>
      ))}
    </div>
  )
}

export default ModelPicker
