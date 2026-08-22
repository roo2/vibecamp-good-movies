import React from 'react'
import { FATE_LABELS } from '../../services/atlasService.js'

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

function FilmDetail({ film, dimensions, onClose }) {
  const skeleton = film.skeleton
  const names = new Map((dimensions || []).map((dim) => [dim.dim_id, dim]))

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

      {!skeleton && <p className="detail-empty">No skeleton has been extracted for this film yet.</p>}

      {skeleton && (
        <>
          {film.profile?.length > 0 && (
            <div className="detail-field">
              <span>Strongest axes</span>
              <ul className="detail-axes">
                {[...film.profile]
                  .sort((a, b) => Math.abs(b.net) * b.n_items - Math.abs(a.net) * a.n_items)
                  .slice(0, 4)
                  .map((row) => {
                    const dim = names.get(row.dim_id)
                    if (!dim) return null
                    return (
                      <li key={row.dim_id}>
                        <b>{dim.name}</b>
                        {/* The pole wears the same colour it wears in the chart,
                            or the panel and the bars disagree about which end
                            of the axis this film is on. */}
                        <em className={row.net > 0 ? 'high' : 'low'}>
                          {row.net > 0 ? dim.pole_high : dim.pole_low}
                        </em>
                        <span>{row.net > 0 ? '+' : ''}{row.net.toFixed(2)} over {row.n_items} items</span>
                      </li>
                    )
                  })}
              </ul>
            </div>
          )}

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
    </aside>
  )
}

export default FilmDetail
