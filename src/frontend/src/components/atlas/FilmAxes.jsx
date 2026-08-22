import React from 'react'

// A film's position on an axis is a mean of item verdicts, and a mean is not an
// argument. This is the argument: every proposition the film was scored on for
// that axis, which way it went, and the grounding the scorer gave — so a reader
// can walk the number back to the sentences it was made of, or disagree with it.
//
// All eight axes are listed, including the ones the film never engages. An axis
// a film has nothing to say about is a fact about the film, and hiding the empty
// rows would quietly turn a sparse profile into a confident one.
function FilmAxes({ dimensions, axes, profile }) {
  const [open, setOpen] = React.useState(null)

  const scored = new Map((axes || []).map((axis) => [axis.dim_id, axis]))
  // Before the per-film document arrives, the index's own profile still knows
  // where the film sits — just not why.
  const fallback = new Map((profile || []).map((row) => [row.dim_id, row]))

  const rows = dimensions.map((dim) => {
    const detail = scored.get(dim.dim_id)
    const summary = detail || fallback.get(dim.dim_id)
    return { dim, detail, net: summary?.net ?? null, nItems: summary?.n_items ?? 0 }
  })
  const engaged = rows.filter((row) => row.nItems > 0)

  return (
    <div className="film-axes">
      <div className="axes-head">
        <span>Where it sits on the eight axes</span>
        <em>{engaged.length} of {dimensions.length} engaged</em>
      </div>

      {rows.map(({ dim, detail, net, nItems }) => {
        const isOpen = open === dim.dim_id
        const has = nItems > 0 && net != null
        const positive = has && net > 0
        const neutral = has && net === 0
        const width = has ? Math.abs(net) * 50 : 0
        const pole = !has ? null : neutral ? 'Split — it argues both ways'
          : positive ? dim.pole_high : dim.pole_low

        return (
          <section className={`axis-block${has ? '' : ' silent'}`} key={dim.dim_id}>
            <button
              type="button"
              className="axis-summary"
              aria-expanded={isOpen}
              disabled={!detail?.items?.length}
              onClick={() => setOpen(isOpen ? null : dim.dim_id)}
            >
              <span className="axis-name">
                {dim.name}
                <em>{dim.question}</em>
              </span>

              <span className="axis-meter" aria-hidden="true">
                <i className="zero" />
                {has && (
                  <i
                    className={`fill ${positive ? 'high' : neutral ? 'zero-mark' : 'low'}`}
                    style={{
                      inlineSize: neutral ? '2px' : `${width}%`,
                      insetInlineStart: neutral ? '50%' : positive ? '50%' : `${50 - width}%`,
                    }}
                  />
                )}
              </span>

              <span className="axis-figure">
                {has ? <b>{net > 0 ? '+' : ''}{net.toFixed(2)}</b> : <b className="muted">—</b>}
                <em>{has ? `${nItems} item${nItems === 1 ? '' : 's'}` : 'not engaged'}</em>
              </span>
            </button>

            {has && (
              <p className={`axis-stance ${positive ? 'high' : neutral ? '' : 'low'}`}>{pole}</p>
            )}
            {!has && (
              <p className="axis-stance muted">
                Nothing in the evidence for this film took a position on this question.
              </p>
            )}

            {isOpen && detail?.items?.length > 0 && (
              <ol className="axis-items">
                {detail.items.map((item) => (
                  <li key={item.item_id} className={item.toward || 'neutral'}>
                    <div className="item-head">
                      <span className={`verdict ${item.verdict.replace(' ', '-')}`}>
                        {item.verdict}
                      </span>
                      <q>{item.text}</q>
                    </div>
                    {item.evidence && <p className="item-evidence">{item.evidence}</p>}
                    <span className="item-meta">
                      {item.toward
                        ? `pulls toward ${item.toward === 'high' ? 'the high pole' : 'the low pole'}`
                        : 'no pull'}
                      {item.confidence != null && ` · confidence ${item.confidence.toFixed(2)}`}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </section>
        )
      })}

      {axes?.length > 0 && (
        <p className="axes-foot">
          Read from <b>{axes[0].variant_label}</b>. A verdict is what the film does with the
          proposition; which pole that pulls toward depends on how the statement sits on the
          axis, so a film can affirm a statement and still be pulled to the low pole.
        </p>
      )}
    </div>
  )
}

export default FilmAxes
