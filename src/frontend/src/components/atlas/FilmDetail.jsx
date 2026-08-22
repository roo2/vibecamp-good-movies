import React from 'react'
import { FATE_LABELS, loadFilmEvidence } from '../../services/atlasService.js'
import FilmAxes from './FilmAxes.jsx'

function Field({ label, value }) {
  if (!value) return null
  return (
    <div className="detail-field">
      <span>{label}</span>
      <p>{value}</p>
    </div>
  )
}

function ListField({ label, values }) {
  if (!values?.length) return null
  return (
    <div className="detail-field">
      <span>{label}</span>
      <ul>{values.map((value, index) => <li key={index}>{value}</li>)}</ul>
    </div>
  )
}

// The source text every claim about this film was read from. It is the point of
// the corpus that this is checkable, so it is here rather than described — but
// it is fetched per film, and only once the panel is open.
function Evidence({ state }) {
  const film = state.film
  if (!film.evidence_layers?.length) return null

  return (
    <div className="detail-field evidence">
      <span>Read from</span>
      {state.status === 'loading' && <p className="detail-muted">Fetching the source text…</p>}
      {state.status === 'failed' && <p className="detail-muted">{state.message}</p>}
      {state.status === 'ready' && state.document.layers.map((layer) => (
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
  )
}

function FilmDetail({ film, dimensions, onClose }) {
  const skeleton = film.skeleton
  const [state, setState] = React.useState({ status: 'loading', film })

  React.useEffect(() => {
    let live = true
    setState({ status: 'loading', film })
    loadFilmEvidence(film.id)
      .then((document) => live && setState({ status: 'ready', film, document }))
      .catch((error) => live && setState({ status: 'failed', film, message: error.message }))
    return () => { live = false }
  }, [film])

  return (
    <aside className="film-detail" aria-label={`${film.title} in full`}>
      <div className="detail-head">
        <div>
          <h3>{film.title} <span>{film.year}</span></h3>
          {skeleton && (
            <p className="detail-provenance">
              Read from <b>{film.variant_label}</b> · {film.model} · confidence{' '}
              {skeleton.confidence != null ? skeleton.confidence.toFixed(2) : '—'}
            </p>
          )}
        </div>
        <button type="button" className="close-button" onClick={onClose} aria-label="Close">×</button>
      </div>

      {film.description && <p className="detail-blurb">{film.description}</p>}

      {/* The axes lead. They are the instrument this project built, and the
          skeleton below is the reading they were derived from — not the other
          way round. */}
      <FilmAxes
        dimensions={dimensions || []}
        axes={state.document?.axes}
        profile={film.profile}
      />
      {state.status === 'loading' && (
        <p className="detail-muted">Fetching the verdicts behind these positions…</p>
      )}
      {state.status === 'failed' && <p className="detail-muted">{state.message}</p>}

      {!skeleton && <p className="detail-empty">No skeleton has been extracted for this film yet.</p>}

      {skeleton && (
        <>
          <h4 className="detail-section">What the film was read as saying</h4>
          <Field label="Source of legitimate authority" value={skeleton.legitimacy_source} />
          <Field label="Who holds power at the open" value={skeleton.opening_power} />
          <Field label="Who holds power at the close" value={skeleton.closing_power} />
          <Field label="What is restored" value={skeleton.what_is_restored} />
          <Field label="What is overturned" value={skeleton.what_is_overturned} />
          <Field label="Antagonist" value={skeleton.antagonist} />
          <Field
            label={skeleton.antagonist_origin_given ? 'Their backstory (given)' : 'Their backstory'}
            value={skeleton.antagonist_origin || (skeleton.antagonist_origin_given ? '' : 'Not supplied — the film offers no mitigating origin.')}
          />
          <Field label="What happens to them" value={FATE_LABELS[skeleton.antagonist_fate] || skeleton.antagonist_fate} />
          <Field label="Protagonist’s flaw" value={skeleton.protagonist_flaw} />
          <Field label="What changes in them" value={skeleton.protagonist_change} />
          <ListField label="Whose inner life the film grants" values={skeleton.interiority_granted} />
          <ListField label="Whose it withholds" values={skeleton.interiority_withheld} />
          <ListField label="Who the narrative punishes" values={skeleton.punished} />
          <ListField label="Who it forgives" values={skeleton.forgiven} />
          <Field label="Final image" value={skeleton.final_image} />
          <Field label="Last spoken line" value={skeleton.final_spoken_line && `“${skeleton.final_spoken_line}”`} />
          <Field label="Tonal register" value={skeleton.tonal_register} />
          {skeleton.depicts_but_does_not_endorse && (
            <div className="detail-field flagged">
              <span>Depicts but does not endorse</span>
              <p>{skeleton.endorsement_evidence}</p>
            </div>
          )}
          <Field label="What it adapts" value={skeleton.source_text} />
          <Field label="How it inverts the source" value={skeleton.inverts_source_how} />

          {skeleton.evidence_quotes?.length > 0 && (
            <div className="detail-field">
              <span>Grounding quotes</span>
              <ul className="detail-quotes">
                {skeleton.evidence_quotes.map((quote, index) => <li key={index}>“{quote}”</li>)}
              </ul>
            </div>
          )}

          {skeleton.unsupported_fields?.length > 0 && (
            <div className="detail-field unsupported">
              <span>Fields the model would not claim from the evidence</span>
              <ul>{skeleton.unsupported_fields.map((field, index) => <li key={index}>{field}</li>)}</ul>
            </div>
          )}
        </>
      )}

      <Evidence state={state} />
    </aside>
  )
}

export default FilmDetail
