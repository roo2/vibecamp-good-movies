import React from 'react'
import FilmDetail from './FilmDetail.jsx'
import FilmPlane from './FilmPlane.jsx'
import { planePoints } from '../../services/atlasService.js'

// The plot and the film panel, side by side, driven by one selection.
//
// They used to be separate: a plot you could click, and somewhere further down
// the page a panel that appeared. Reading one film meant scrolling away from
// the thing that gave it context, and a position is only legible next to where
// every other film landed — "0.47 on redemptive" means nothing alone.
//
// Shared by the atlas and the corpus lookup rather than written twice. Those
// two pages have already drifted apart once, when one defaulted to the reading
// with the most verdicts and the other to the reading the product uses, and the
// same film quietly showed different numbers depending on which you opened.
//
// Search and the plot are two routes to the same act. Typing highlights every
// match in place, so a reader sees WHERE the matches are before choosing one —
// which a dropdown of titles cannot show.

export default function FilmExplorer({
  films, factors, taste, reading, selectedId, onSelect,
  sets, viewer, space = 'moral', onSpaceChange,
}) {
  const [query, setQuery] = React.useState('')
  const plane = React.useMemo(
    () => planePoints(factors, taste, space), [factors, taste, space])

  const all = films || []
  const matches = React.useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return []
    return all.filter((f) => `${f.title} ${f.year ?? ''}`.toLowerCase().includes(needle))
  }, [all, query])
  const matchIds = React.useMemo(
    () => (matches.length ? new Set(matches.map((f) => f.id)) : null), [matches])

  const selected = all.find((f) => f.id === selectedId)
  // The plot carries films the corpus list may not; falling back to the point
  // keeps a click from opening an empty panel.
  const point = plane?.points.find((p) => p.id === selectedId)
  const title = selected?.title || point?.title

  if (!plane) return null

  return (
    <section className="film-explorer">
      <div className="explorer-plot">
        {onSpaceChange && (
          <div className="plane-axis-pick" role="tablist" aria-label="Which axes to plot">
            <button type="button" role="tab" aria-selected={space === 'moral'}
                    className={space === 'moral' ? 'on' : undefined}
                    onClick={() => onSpaceChange('moral')}>
              What films argue
            </button>
            <button type="button" role="tab" aria-selected={space === 'taste'}
                    className={space === 'taste' ? 'on' : undefined}
                    onClick={() => onSpaceChange('taste')}>
              What people choose by
            </button>
          </div>
        )}

        <input
          className="atlas-search"
          value={query}
          placeholder="Search for a film"
          aria-label="Search for a film"
          onChange={(event) => setQuery(event.target.value)}
        />

        {query.trim() && (
          <p className="atlas-note explorer-matches">
            {matches.length
              ? <>{matches.length} highlighted{matches.length <= 8 && ' — '}
                {matches.length <= 8 && matches.map((f, i) => (
                  <React.Fragment key={f.id}>
                    {i > 0 && ', '}
                    <button type="button" className="link-button"
                            onClick={() => onSelect(f.id)}>{f.title}</button>
                  </React.Fragment>
                ))}</>
              : <>Nothing matches &ldquo;{query.trim()}&rdquo;. The corpus is {all.length} films,
                  so plenty of cinema is not in it yet.</>}
          </p>
        )}

        <FilmPlane points={plane.points} xAxis={plane.xAxis} yAxis={plane.yAxis}
                   sets={space === 'moral' ? sets : []}
                   viewer={space === 'moral' ? viewer : null}
                   selectedId={selectedId} matchIds={matchIds}
                   onSelect={onSelect} />
      </div>

      <div className="explorer-panel">
        {title ? (
          // FilmDetail already carries the axes, the taste position and the
          // dialogue a claim was read from. Rendering its parts again here put
          // every axis on the screen twice.
          <FilmDetail
            film={selected || { id: selectedId, title }}
            scorer={reading?.scorer} variant={reading?.variant}
            bank={reading?.bank_version} taste={taste}
            onClose={() => onSelect(null)} />
        ) : (
          <p className="atlas-note explorer-empty">
            Pick a film — click a point, or search. Every dot is one film, placed by what its
            dialogue argues with taste held constant, so two films near each other are making
            similar moral claims rather than merely appealing to the same people.
          </p>
        )}
      </div>
    </section>
  )
}
