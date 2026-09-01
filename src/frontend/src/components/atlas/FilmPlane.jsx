import React from 'react'

// Two axes at a time, drawn flat.
//
// This replaced a rotatable three-axis cloud, and the reason is a finding
// rather than a preference. The third moral axis does not survive its tests —
// its propositions barely agree, no ideological set separates along it, and a
// person cannot be placed on it above noise — so there is no honest third
// dimension left to rotate. A plane also lets a reader see WHERE a film sits
// instead of manipulating a view until it looks like it means something.
//
// SVG rather than canvas: five hundred points is nothing to a browser, and
// hit-testing, focus and titles come free instead of being reimplemented.

const SIZE = 600
// Padding and type are in viewBox units, so they shrink with the plot. At 390px
// wide a 600-unit box renders 11-unit labels at about seven real pixels, which
// is unreadable — so a narrow screen gets bigger units to end up with bigger
// pixels. Measured against the rendered width rather than a breakpoint, because
// the plot sits in a 600px column on the atlas and full-bleed on a phone.
const PAD_WIDE = 46
const PAD_NARROW = 62

// One colour per axis, used for its rule, its ticks and both its pole labels,
// so a label is tied to its axis by something other than position. Carried over
// from the cloud this replaced, where they identified the same two axes.
const AXIS_COLOUR = ['#eda36b', '#5cc3c0']

// A set's crosshair has to be findable among its own dots, which are already
// that colour. Lightening rather than darkening keeps it visible on the dark
// theme too, where a darker marker would sink into the ground.
function brighter(hex, amount = 0.45) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '')
  if (!m) return hex
  const n = parseInt(m[1], 16)
  const mix = (c) => Math.round(c + (255 - c) * amount)
  return `rgb(${mix((n >> 16) & 255)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`
}

function extent(values) {
  let lo = Infinity
  let hi = -Infinity
  for (const v of values) {
    if (v < lo) lo = v
    if (v > hi) hi = v
  }
  if (!Number.isFinite(lo)) return [-1, 1]
  const pad = (hi - lo) * 0.06 || 1
  return [lo - pad, hi + pad]
}

export default function FilmPlane({
  points, xAxis, yAxis, sets, viewer, onSelect, selectedId, matchIds,
}) {
  const [hover, setHover] = React.useState(null)
  const box = React.useRef(null)
  const [narrow, setNarrow] = React.useState(false)

  React.useEffect(() => {
    const el = box.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const watch = new ResizeObserver(([entry]) => {
      setNarrow(entry.contentRect.width < 520)
    })
    watch.observe(el)
    return () => watch.disconnect()
  }, [])

  const PAD = narrow ? PAD_NARROW : PAD_WIDE

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

    // A set's centre is the mean of ITS films, not of everything highlighted.
    const marks = (sets || []).map((s) => {
      const mine = placedPoints.filter((p) => (s.films || []).includes(p.id))
      if (mine.length < 3) return null
      return {
        name: s.name, colour: brighter(s.colour), n: mine.length,
        px: mine.reduce((a, p) => a + p.px, 0) / mine.length,
        py: mine.reduce((a, p) => a + p.py, 0) / mine.length,
      }
    }).filter(Boolean)

    return {
      placed: placedPoints, centroids: marks,
      cx: sx(0) > PAD && sx(0) < SIZE - PAD ? sx(0) : null,
      cy: sy(0) > PAD && sy(0) < SIZE - PAD ? sy(0) : null,
    }
  }, [points, sets, PAD])

  if (!placed.length) return null
  const me = viewer && placed.find((p) => p.id === viewer.id)

  return (
    <figure className={narrow ? 'film-plane narrow' : 'film-plane'} ref={box}>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img"
           aria-label={`${points.length} films placed on ${xAxis.high} against ${yAxis.high}`}>
        {cy != null && (
          <line className="plane-rule" style={{ stroke: AXIS_COLOUR[0] }}
                x1={PAD - 10} y1={cy} x2={SIZE - PAD + 10} y2={cy} />
        )}
        {cx != null && (
          <line className="plane-rule" style={{ stroke: AXIS_COLOUR[1] }}
                x1={cx} y1={PAD - 10} x2={cx} y2={SIZE - PAD + 10} />
        )}

        {placed.map((p) => {
          // A search match is drawn like a selection-in-waiting: findable at a
          // glance without pretending it has been opened.
          const matched = matchIds ? matchIds.has(p.id) : false
          const base = narrow ? 4.2 : 2.6
          const r = p.id === selectedId ? base + 3 : matched ? base + 2 : base
          return (
            <g key={p.id}
               className={`plane-mark${p.colour ? ' in-set' : ''}`
                 + (matched ? ' matched' : '') + (p.id === selectedId ? ' chosen' : '')}
               style={p.colour ? { stroke: p.colour } : undefined}
               onMouseEnter={() => setHover(p)}
               onMouseLeave={() => setHover((h) => (h && h.id === p.id ? null : h))}
               onClick={() => onSelect && onSelect(p.id)}>
              {/* A cross reads at this size where a filled dot turns to mush,
                  and overlapping crosses stay countable. */}
              <path d={`M${p.px - r} ${p.py}H${p.px + r}M${p.px} ${p.py - r}V${p.py + r}`} />
              {/* The visible mark is three pixels wide; the target is not. */}
              <circle className="plane-hit" cx={p.px} cy={p.py} r="7" />
              <title>{p.title}</title>
            </g>
          )
        })}

        {centroids.map((c) => (
          <g key={c.name} className="plane-centre" style={{ stroke: c.colour }}>
            <circle cx={c.px} cy={c.py} r="7" />
            <line x1={c.px - 11} y1={c.py} x2={c.px + 11} y2={c.py} />
            <line x1={c.px} y1={c.py - 11} x2={c.px} y2={c.py + 11} />
          </g>
        ))}

        {me && <circle className="plane-you" cx={me.px} cy={me.py} r="6.5" />}

        {/* Pole labels sit inside the frame and carry their axis's colour.
            Placed outside they were clipped on a phone, which is where most of
            this is read. */}
        <text className="plane-pole" style={{ fill: AXIS_COLOUR[1] }}
              x={SIZE / 2} y={PAD - 14} textAnchor="middle">{yAxis.high}</text>
        <text className="plane-pole" style={{ fill: AXIS_COLOUR[1] }}
              x={SIZE / 2} y={SIZE - PAD + 24} textAnchor="middle">{yAxis.low}</text>
        <text className="plane-pole" style={{ fill: AXIS_COLOUR[0] }}
              x={SIZE - PAD + 8} y={SIZE / 2 - 7} textAnchor="end">{xAxis.high}</text>
        <text className="plane-pole" style={{ fill: AXIS_COLOUR[0] }}
              x={PAD - 8} y={SIZE / 2 - 7} textAnchor="start">{xAxis.low}</text>
      </svg>

      <figcaption>
        {hover
          ? <b>{hover.title}</b>
          : <>{placed.length} films, positioned with taste held constant. Rings mark the centre
              of a highlighted list.</>}
      </figcaption>
    </figure>
  )
}
