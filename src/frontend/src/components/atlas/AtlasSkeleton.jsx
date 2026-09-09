import React from 'react'

// What the page will look like, while it is still arriving.
//
// The atlas pulls a 674-film corpus, a model list, every factor for a reading
// and the taste table before it can draw anything, and it used to spend that
// time as one grey line of type on an empty page — which reads as a page that
// has failed rather than one that is working. A shape that matches what lands
// says the same thing more honestly and gives the eye somewhere to be.
//
// Deliberately not a spinner: a spinner says "wait" and nothing else, where
// this says what is coming and roughly how much of it there is.
export default function AtlasSkeleton({ rows = 3, plot = true }) {
  return (
    <div className="atlas-skeleton" role="status" aria-live="polite">
      <span className="sr-only">Loading the atlas…</span>
      <span className="skeleton skeleton-line wide" />
      <span className="skeleton skeleton-line" />
      {plot && <span className="skeleton skeleton-plot" />}
      <div className="atlas-skeleton-rows" aria-hidden="true">
        {Array.from({ length: rows }).map((_, i) => (
          <span className="skeleton skeleton-row" key={i} />
        ))}
      </div>
    </div>
  )
}
