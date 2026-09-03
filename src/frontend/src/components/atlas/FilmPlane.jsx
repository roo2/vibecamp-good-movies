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

// How far in a reader may go. Past about six the corpus is a handful of dots
// with nothing around them to read a position against.
const MAX_ZOOM = 6

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

const FIT = { x: 0, y: 0, w: SIZE }

// The window can be moved and narrowed but never taken outside the plot: a
// reader who pans off the edge has no way to know which way is back.
function clampView(v) {
  const w = Math.min(SIZE, Math.max(SIZE / MAX_ZOOM, v.w))
  return {
    w,
    x: Math.min(Math.max(v.x, 0), SIZE - w),
    y: Math.min(Math.max(v.y, 0), SIZE - w),
  }
}

// What each space actually plots, in the caption's own words.
const CAPTION = {
  moral: 'placed by what their dialogue argues.',
  taste: 'placed by which films the same people enjoy.',
  adjusted: 'placed by what their dialogue argues once the part taste predicts '
    + 'is removed — so a film sits where it is MORE than its taste explains.',
}

export default function FilmPlane({
  points, xAxis, yAxis, sets, viewer, onSelect, selectedId, matchIds, space = 'moral',
}) {
  const [hover, setHover] = React.useState(null)
  const box = React.useRef(null)
  const svgRef = React.useRef(null)
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

  // ---- the zoom window ------------------------------------------------------
  //
  // Held as a window onto the 600-unit plot rather than as a scale factor,
  // because every gesture here is really "keep THIS point still and change how
  // much fits around it", which a window expresses directly.
  const [view, setView] = React.useState(FIT)
  const viewRef = React.useRef(view)
  viewRef.current = view
  const zoom = SIZE / view.w
  const zoomed = zoom > 1.001

  // Pan and pinch move the window, so the marks inside must shrink by the same
  // factor or zooming in only magnifies the overlap it was meant to separate.
  // Done with one custom property rather than per-point maths: six hundred
  // React nodes cannot be re-rendered on every frame of a pinch.
  const planeStyle = { '--z': zoom }

  const toPlot = React.useCallback((clientX, clientY) => {
    const rect = svgRef.current?.getBoundingClientRect()
    const v = viewRef.current
    if (!rect || !rect.width) return { x: v.x, y: v.y }
    return {
      x: v.x + ((clientX - rect.left) / rect.width) * v.w,
      y: v.y + ((clientY - rect.top) / rect.height) * v.w,
    }
  }, [])

  // Scale about a fixed point: whatever was under the fingers stays under them.
  const zoomAbout = React.useCallback((factor, clientX, clientY) => {
    setView((v) => {
      const rect = svgRef.current?.getBoundingClientRect()
      const w = Math.min(SIZE, Math.max(SIZE / MAX_ZOOM, v.w / factor))
      if (!rect || !rect.width) return clampView({ ...v, w })
      const fx = (clientX - rect.left) / rect.width
      const fy = (clientY - rect.top) / rect.height
      return clampView({ w, x: v.x + (v.w - w) * fx, y: v.y + (v.w - w) * fy })
    })
  }, [])

  const nudge = (factor) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    zoomAbout(factor, rect.left + rect.width / 2, rect.top + rect.height / 2)
  }

  // ---- gestures -------------------------------------------------------------
  const touches = React.useRef(new Map())
  const pinch = React.useRef(null)
  const drag = React.useRef(null)
  const moved = React.useRef(false)

  const down = (e) => {
    touches.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    moved.current = false
    if (touches.current.size === 2) {
      const [a, b] = [...touches.current.values()]
      pinch.current = { dist: Math.hypot(a.x - b.x, a.y - b.y) }
      drag.current = null
    } else if (touches.current.size === 1 && zoomed) {
      // Only claim one-finger drags once there is somewhere to pan to;
      // otherwise the gesture belongs to the page, which has to stay scrollable.
      drag.current = toPlot(e.clientX, e.clientY)
      e.currentTarget.setPointerCapture?.(e.pointerId)
    }
  }

  const move = (e) => {
    if (!touches.current.has(e.pointerId)) return
    touches.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (touches.current.size >= 2 && pinch.current) {
      const [a, b] = [...touches.current.values()]
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      if (pinch.current.dist > 0 && dist > 0) {
        moved.current = true
        zoomAbout(dist / pinch.current.dist, (a.x + b.x) / 2, (a.y + b.y) / 2)
      }
      pinch.current = { dist }
      return
    }
    if (drag.current) {
      const at = toPlot(e.clientX, e.clientY)
      const dx = at.x - drag.current.x
      const dy = at.y - drag.current.y
      if (Math.abs(dx) > 1 || Math.abs(dy) > 1) moved.current = true
      setView((v) => clampView({ ...v, x: v.x - dx, y: v.y - dy }))
    }
  }

  const up = (e) => {
    touches.current.delete(e.pointerId)
    if (touches.current.size < 2) pinch.current = null
    if (touches.current.size === 0) drag.current = null
  }

  // Trackpad pinch and ctrl+wheel arrive as a wheel event, and the listener has
  // to be non-passive to stop the browser zooming the whole page instead.
  React.useEffect(() => {
    const el = svgRef.current
    if (!el) return undefined
    const onWheel = (e) => {
      if (!e.ctrlKey && !e.metaKey) return
      e.preventDefault()
      zoomAbout(Math.exp(-e.deltaY / 220), e.clientX, e.clientY)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [zoomAbout])

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
  const highlighting = centroids.length > 0
    || (sets || []).some((s) => (s.films || []).length > 0)

  // Centres and the viewer marker are drawn in the OUTER coordinates, mapped
  // through the window by hand. Inside the panned group they would grow with
  // the zoom, and the one thing a reader is looking for is the hardest thing to
  // let balloon over the dots it is meant to summarise.
  const out = (px, py) => ({ x: (px - view.x) * zoom, y: (py - view.y) * zoom })

  return (
    <figure
      className={`film-plane${narrow ? ' narrow' : ''}${highlighting ? ' has-set' : ''}`
        + (zoomed ? ' zoomed' : '')}
      style={planeStyle} ref={box}>
      <svg ref={svgRef} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img"
           // At rest the page must still scroll under a finger; once there is
           // somewhere to pan to, the gesture becomes the plot's. Two fingers
           // are ours either way, because pan-y already forbids the browser's
           // own pinch on this element.
           style={{ touchAction: zoomed ? 'none' : 'pan-y' }}
           onPointerDown={down} onPointerMove={move}
           onPointerUp={up} onPointerCancel={up} onPointerLeave={up}
           onDoubleClick={(e) => zoomAbout(1.8, e.clientX, e.clientY)}
           aria-label={`${points.length} films placed on ${xAxis.high} against ${yAxis.high}`}>
        <g transform={`scale(${zoom}) translate(${-view.x} ${-view.y})`}>
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
                 onClick={() => { if (!moved.current && onSelect) onSelect(p.id) }}>
                {/* A cross reads at this size where a filled dot turns to mush,
                    and overlapping crosses stay countable. */}
                <path d={`M${p.px - r} ${p.py}H${p.px + r}M${p.px} ${p.py - r}V${p.py + r}`} />
                {/* The visible mark is three pixels wide; the target is not. */}
                <circle className="plane-hit" cx={p.px} cy={p.py} r="7" />
                <title>{p.title}</title>
              </g>
            )
          })}
        </g>

        {/* Set centres, drawn over everything and named. A ring the same colour
            as its own dots was invisible inside them; this one carries a dark
            halo, a filled core and detached arms, none of which the dots have. */}
        {centroids.map((c) => {
          const at = out(c.px, c.py)
          if (at.x < 0 || at.y < 0 || at.x > SIZE || at.y > SIZE) return null
          const arms = [[0, -1], [0, 1], [-1, 0], [1, 0]]
          const flip = at.x > SIZE - 150
          return (
            <g key={c.name} className="plane-centre">
              <g className="halo">
                <circle cx={at.x} cy={at.y} r="10" />
                {arms.map(([ax, ay]) => (
                  <line key={`h${ax}${ay}`}
                        x1={at.x + ax * 14} y1={at.y + ay * 14}
                        x2={at.x + ax * 23} y2={at.y + ay * 23} />
                ))}
              </g>
              <g style={{ stroke: c.colour }}>
                <circle cx={at.x} cy={at.y} r="10" />
                {arms.map(([ax, ay]) => (
                  <line key={`${ax}${ay}`}
                        x1={at.x + ax * 14} y1={at.y + ay * 14}
                        x2={at.x + ax * 23} y2={at.y + ay * 23} />
                ))}
              </g>
              <circle className="core" cx={at.x} cy={at.y} r="3" style={{ fill: c.colour }} />
              <text className="plane-centre-label" style={{ fill: c.colour }}
                    x={at.x + (flip ? -27 : 27)} y={at.y + 4}
                    textAnchor={flip ? 'end' : 'start'}>
                {c.name} <tspan className="n">({c.n})</tspan>
              </text>
            </g>
          )
        })}

        {me && (() => {
          const at = out(me.px, me.py)
          return <circle className="plane-you" cx={at.x} cy={at.y} r="6.5" />
        })()}

        {/* Pole labels sit inside the frame and carry their axis's colour.
            Placed outside they were clipped on a phone, which is where most of
            this is read. Outside the panned group: they name the whole axis,
            not a place on it, so they stay put when the window moves. */}
        <text className="plane-pole" style={{ fill: AXIS_COLOUR[1] }}
              x={SIZE / 2} y={PAD - 14} textAnchor="middle">{yAxis.high}</text>
        <text className="plane-pole" style={{ fill: AXIS_COLOUR[1] }}
              x={SIZE / 2} y={SIZE - PAD + 24} textAnchor="middle">{yAxis.low}</text>
        <text className="plane-pole" style={{ fill: AXIS_COLOUR[0] }}
              x={SIZE - PAD + 8} y={SIZE / 2 - 7} textAnchor="end">{xAxis.high}</text>
        <text className="plane-pole" style={{ fill: AXIS_COLOUR[0] }}
              x={PAD - 8} y={SIZE / 2 - 7} textAnchor="start">{xAxis.low}</text>
      </svg>

      <div className="plane-zoom">
        <button type="button" onClick={() => nudge(1 / 1.6)}
                disabled={!zoomed} aria-label="Zoom out">&minus;</button>
        <button type="button" onClick={() => nudge(1.6)}
                disabled={zoom >= MAX_ZOOM - 0.001} aria-label="Zoom in">+</button>
        <button type="button" className="plane-zoom-reset" onClick={() => setView(FIT)}
                disabled={!zoomed}>Fit</button>
        <span aria-hidden="true">{zoom.toFixed(1)}&times;</span>
      </div>

      {/* The caption has to name the quantity actually drawn. It said "with
          taste held constant" in every space, which described the residual —
          and once the default became the plain moral position it was telling
          the reader the opposite of what was on screen. */}
      <figcaption>
        {hover
          ? <b>{hover.title}</b>
          : <>{placed.length} films, {CAPTION[space] || CAPTION.moral}
              {highlighting
                ? ' Ringed crosshairs mark the centre of each highlighted list.'
                : ' Pinch, scroll with ctrl held, or double-tap to zoom in.'}</>}
      </figcaption>
    </figure>
  )
}
