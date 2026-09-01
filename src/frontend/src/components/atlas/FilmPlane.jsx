import React from 'react'

// Two axes at a time, drawn flat.
//
// This replaced a rotatable three-axis cloud, and the reason is a finding
// rather than a preference. The third moral axis does not survive its tests —
// its propositions barely agree, no ideological set separates along it, and a
// person cannot be placed on it above noise — so there is no honest third
// dimension left to rotate. A plane also lets a reader see WHERE a film sits
// instead of manipulating a view until it looks like it means something, and
// every position is legible without interaction, which the cloud never was.
//
// SVG rather than canvas: five hundred points is nothing to a browser, and
// hit-testing, focus and titles come free instead of being reimplemented.

const PAD = 54
const SIZE = 560

function extent(values) {
  let lo = Infinity
  let hi = -Infinity
  for (const v of values) {
    if (v < lo) lo = v
    if (v > hi) hi = v
  }
  if (!Number.isFinite(lo)) return [-1, 1]
  // A hair of margin so a film at the extreme is not drawn half outside the frame.
  const pad = (hi - lo) * 0.06 || 1
  return [lo - pad, hi + pad]
}

export default function FilmPlane({
  points, xAxis, yAxis, sets, viewer, onSelect, selectedId,
}) {
  const [hover, setHover] = React.useState(null)

  const { placed, cx, cy, centroids } = React.useMemo(() => {
    if (!points || points.length < 2) return { placed: [], centroids: [] }
    const [x0, x1] = extent(points.map((p) => p.x))
    const [y0, y1] = extent(points.map((p) => p.y))
    const sx = (v) => PAD + ((v - x0) / (x1 - x0)) * (SIZE - PAD * 2)
    // Screen y grows downward; the high pole belongs at the top.
    const sy = (v) => SIZE - PAD - ((v - y0) / (y1 - y0)) * (SIZE - PAD * 2)

    const colour = {}
    for (const s of sets || []) for (const id of s.films || []) colour[id] = s.colour

    const placedPoints = points.map((p) => ({
      ...p, px: sx(p.x), py: sy(p.y), colour: colour[p.id],
    }))

    // A set's centre, drawn as a crosshair. Its own films are what define it, so
    // the marker is the mean of exactly those — not of everything highlighted.
    const marks = (sets || []).map((s) => {
      const mine = placedPoints.filter((p) => (s.films || []).includes(p.id))
      if (mine.length < 3) return null
      return {
        name: s.name, colour: s.colour, n: mine.length,
        px: mine.reduce((a, p) => a + p.px, 0) / mine.length,
        py: mine.reduce((a, p) => a + p.py, 0) / mine.length,
      }
    }).filter(Boolean)

    return {
      placed: placedPoints, centroids: marks,
      cx: sx(0) > PAD && sx(0) < SIZE - PAD ? sx(0) : null,
      cy: sy(0) > PAD && sy(0) < SIZE - PAD ? sy(0) : null,
    }
  }, [points, sets])

  if (!placed.length) return null
  const me = viewer && placed.find((p) => p.id === viewer.id)

  return (
    <figure className="film-plane">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img"
           aria-label={`${points.length} films placed on ${xAxis.high} against ${yAxis.high}`}>
        {cx != null && <line className="plane-rule" x1={cx} y1={PAD} x2={cx} y2={SIZE - PAD} />}
        {cy != null && <line className="plane-rule" x1={PAD} y1={cy} x2={SIZE - PAD} y2={cy} />}

        {placed.map((p) => (
          <circle
            key={p.id} cx={p.px} cy={p.py}
            r={p.id === selectedId ? 5.5 : p.colour ? 4 : 2.6}
            className={`plane-dot${p.colour ? ' in-set' : ''}`}
            style={p.colour ? { fill: p.colour } : undefined}
            onMouseEnter={() => setHover(p)}
            onMouseLeave={() => setHover((h) => (h && h.id === p.id ? null : h))}
            onClick={() => onSelect && onSelect(p.id)}
          ><title>{p.title}</title></circle>
        ))}

        {centroids.map((c) => (
          <g key={c.name} className="plane-centre" style={{ stroke: c.colour }}>
            <line x1={c.px - 9} y1={c.py} x2={c.px + 9} y2={c.py} />
            <line x1={c.px} y1={c.py - 9} x2={c.px} y2={c.py + 9} />
          </g>
        ))}

        {me && <circle className="plane-you" cx={me.px} cy={me.py} r="7" />}

        {/* Pole labels sit inside the frame. Placed outside they were clipped on
            a phone, which is where most of this is read. */}
        <text className="plane-pole" x={SIZE / 2} y={PAD - 16} textAnchor="middle">{yAxis.high}</text>
        <text className="plane-pole" x={SIZE / 2} y={SIZE - PAD + 26} textAnchor="middle">{yAxis.low}</text>
        <text className="plane-pole" x={SIZE - PAD} y={SIZE / 2 - 8} textAnchor="end">{xAxis.high}</text>
        <text className="plane-pole" x={PAD} y={SIZE / 2 - 8} textAnchor="start">{xAxis.low}</text>
      </svg>

      <figcaption>
        {hover
          ? <b>{hover.title}</b>
          : <>{placed.length} films. Each dot is one film; the crosshairs mark the centre of a
              highlighted list.</>}
      </figcaption>
    </figure>
  )
}
