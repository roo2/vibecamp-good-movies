import React from 'react'
import { loadFilmEvidence } from '../../services/atlasService.js'

// This panel used to lead with the moral skeleton: legitimacy source, who holds
// power at the open and close, the antagonist's fate, whose interiority the film
// grants. All of it came from one model on 40 of 570 films, and nothing in the
// current pipeline reads it — propositions are now harvested from the dialogue
// directly, which is the whole point of dropping plot summaries and reception.
// Rendering it here would advertise as the film's reading something that is one
// model's reading of a seventh of the corpus.
//
// What is left is what a reader actually needs to argue with a verdict: the film,
// and the words it was scored from.
function FilmDetail({ film, onClose }) {
  const [state, setState] = React.useState({ status: 'loading' })

  React.useEffect(() => {
    if (!film) return undefined
    let live = true
    setState({ status: 'loading' })
    loadFilmEvidence(film.id)
      .then((document) => live && setState({ status: 'ready', document }))
      .catch((error) => live && setState({ status: 'failed', message: error.message }))
    return () => { live = false }
  }, [film])

  if (!film) return null

  return (
    <aside className="film-detail" aria-label={`${film.title} in full`}>
      <div className="detail-head">
        <div>
          <h3>{film.title} <span>{film.year}</span></h3>
          <p className="detail-provenance">
            Scored from this film&apos;s own dialogue.
          </p>
        </div>
        <button type="button" className="close-button" onClick={onClose} aria-label="Close">×</button>
      </div>

      {film.description && <p className="detail-blurb">{film.description}</p>}

      {state.status === 'loading' && <p className="detail-muted">Fetching the source text…</p>}
      {state.status === 'failed' && <p className="detail-muted">{state.message}</p>}

      {state.status === 'ready' && (
        <div className="detail-field evidence">
          <span>Read from</span>
          {state.document.layers.map((layer) => (
            <details key={layer.layer}>
              <summary>
                {layer.label}
                <em>{layer.words ? `${layer.words.toLocaleString()} words` : ''}</em>
              </summary>
              {layer.source_url && (
                <a className="evidence-source" href={layer.source_url} target="_blank" rel="noreferrer">
                  {layer.source_url}
                </a>
              )}
              <pre>{layer.content}</pre>
            </details>
          ))}
        </div>
      )}
    </aside>
  )
}

export default FilmDetail
