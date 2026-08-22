import React from 'react'

// Every chart here is a real <table> with the bar drawn inside the cell. That is
// not a stylistic choice: it means the accessible table view and the picture are
// the same DOM rather than two things that can drift apart, screen readers get
// row/column semantics for free, and the numbers stay selectable text.
//
// Colour does one of two jobs and never both. Magnitude is a single hue. Polarity
// is the diverging pair — cool #6C8AE0 for the low pole, warm #C68347 for the
// high one, a neutral gauge for zero — validated against this surface (#1c1713)
// for lightness band, chroma, CVD separation and contrast.

// `labelWidth` is per chart because the label column is sized by its longest
// label, and these charts do not share one: an axis name runs to five words
// where a fate is one, and a gutter sized for the former wastes half the plot
// on the latter.
export function MagnitudeBars({ caption, rows, unit = '', note, labelWidth = '260px' }) {
  const max = Math.max(1, ...rows.map((row) => row.value))
  return (
    <figure className="atlas-figure">
      {/* The label width is a custom property rather than a width, so the
          stylesheet can cap it as a share of the viewport: a column wide enough
          for an axis name is wider than a phone. */}
      <table className="atlas-chart" style={{ '--label-w': labelWidth }}>
        {/* Fixed layout with explicit columns. Left to itself the browser gives
            the plot column whatever the labels do not want, which is either no
            bar or a label one character wide depending on which side wins. */}
        <colgroup>
          <col className="col-label" />
          <col />
          <col className="col-value" />
        </colgroup>
        <caption className="sr-only">{caption}</caption>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key ?? row.label}>
              <th scope="row">{row.label}</th>
              <td className="plot">
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{ inlineSize: `${(row.value / max) * 100}%` }}
                    title={row.title || `${row.label}: ${row.value}${unit}`}
                  />
                </div>
              </td>
              <td className="bar-value">{row.value}{unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {note && <figcaption>{note}</figcaption>}
    </figure>
  )
}

// A diverging bar grows from a centre line, so the eye reads sign before size —
// which is the whole question on a moral axis. The zero line is a neutral gauge
// colour, never a third hue.
export function DivergingBars({ caption, rows, lowLabel, highLabel, onSelect, selectedKey }) {
  const max = Math.max(0.001, ...rows.map((row) => Math.abs(row.value)))
  return (
    <figure className="atlas-figure">
      <div className="diverging-legend" aria-hidden="true">
        <span><i className="swatch low" /><span><b>Low pole</b>{lowLabel}</span></span>
        <span><i className="swatch high" /><span><b>High pole</b>{highLabel}</span></span>
      </div>
      <table className="atlas-chart diverging" style={{ '--label-w': '300px' }}>
        <colgroup>
          <col className="col-label" />
          <col />
          <col className="col-value" />
          <col className="col-n" />
        </colgroup>
        <caption className="sr-only">{caption}. Negative is “{lowLabel}”, positive is “{highLabel}”.</caption>
        <tbody>
          {rows.map((row) => {
            const width = (Math.abs(row.value) / max) * 50
            const positive = row.value >= 0
            const selected = selectedKey != null && row.key === selectedKey
            return (
              <tr
                key={row.key}
                className={selected ? 'selected' : undefined}
                onClick={onSelect ? () => onSelect(row) : undefined}
              >
                <th scope="row">
                  {onSelect
                    ? <button type="button" className="row-button">{row.label}</button>
                    : row.label}
                </th>
                <td className="plot">
                  <div className="diverging-track">
                    <span className="zero-line" aria-hidden="true" />
                    <span
                      className={`diverging-fill ${positive ? 'high' : 'low'}`}
                      style={{
                        inlineSize: `${width}%`,
                        insetInlineStart: positive ? '50%' : `${50 - width}%`,
                      }}
                      title={row.title || `${row.label}: ${row.value.toFixed(2)}`}
                    />
                  </div>
                </td>
                <td className="bar-value">{row.value > 0 ? '+' : ''}{row.value.toFixed(2)}</td>
                {/* A film sitting at ±1.00 on two items and one sitting there on
                    twenty draw the same bar. The count is what separates them,
                    so it is on the row rather than hidden in a tooltip. */}
                {row.n != null && <td className="bar-n">{row.n} item{row.n === 1 ? '' : 's'}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
      <figcaption>
        A film’s position is the mean signed verdict of the items it was scored on for
        this axis, so a film judged on few items can sit at the extreme. Read the count
        beside the number before reading the bar.
      </figcaption>
    </figure>
  )
}

export function StatTiles({ tiles }) {
  return (
    <div className="stat-tiles">
      {tiles.map((tile) => (
        <div className="stat-tile" key={tile.label}>
          <strong>{tile.value}</strong>
          <span>{tile.label}</span>
          {tile.hint && <small>{tile.hint}</small>}
        </div>
      ))}
    </div>
  )
}
