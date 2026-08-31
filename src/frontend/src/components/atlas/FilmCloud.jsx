import React from 'react'

// Every film at once, in the three dimensions the corpus actually produced.
//
// WHY THREE AND NOT TWO. The cloud is not flat. Standardised, its principal
// variances run 1.20 / 1.00 / 0.80 — 40%, 33% and 27% of the spread — so a flat
// projection would discard a real quarter of it, and the axes are close to
// uncorrelated in where they put films (-0.14, -0.05, -0.10).
//
// WHY STILL NO LIBRARY. What this needs beyond a projection is zoom, pan and
// labels: one scalar on the radius, one offset on the centre, and a greedy
// overlap test. three.js brings a scene graph, a camera rig and orbit controls
// — none of which is the hard part here — and would roughly triple an 80KB
// bundle; its labels still need a second renderer on top. At 565 points the
// library earns nothing. That changes if this ever needs tens of thousands of
// points, in which case the answer is WebGL and regl, not a scene graph.
//
// WHAT THE PICTURE CANNOT SHOW, and the caption says so: the axes are not
// equally well measured. A film's position on the first reproduces at 0.89
// across a split of the propositions; on the other two, at about 0.24.
const SIZE = 520
// A slow drift, and only briefly. Its whole job is to say "this turns" — a dot
// cloud is otherwise indistinguishable from a flat scatter, and nothing on the
// page tells you it can be grabbed. At 0.0022 it read as a screensaver rotating
// under a reader trying to look at it. This is about a fifth of that, roughly a
// degree and a half a second, and it stops on its own after DEMO_MS whether or
// not anybody has touched it.
const IDLE_SPIN = 0.00045
const DEMO_MS = 14000
const AXIS_COLOUR = ['#eda36b', '#5cc3c0', '#b48ce0']
const LABEL_BASE = 10          // labels at rest; grows as you zoom in
const LABEL_CAP = 70

function project(p, yaw, pitch) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw)
  const cp = Math.cos(pitch), sp = Math.sin(pitch)
  const x = p.x * cy - p.z * sy
  const z1 = p.x * sy + p.z * cy
  return { x, y: p.y * cp - z1 * sp, z: p.y * sp + z1 * cp }
}

// `sets` are the switched-on groups, each {set_id, name, colour, films}. The
// component derives the per-film colouring from them rather than being handed a
// map, so it can also place each set's CENTRE — which is the thing worth seeing.
// A set of nineteen films scattered through a cloud of 565 is hard to read as a
// position; one marker at its average is not.
//
// `viewer` is the reader's own compass, ALREADY MEASURED FROM THE AVERAGE FILM
// by score_preferences, so it is scaled but not re-centred here. Centring it
// twice would put a typical viewer a full standard deviation from where they
// belong.
export default function FilmCloud({ factors, sets, viewer, onSelect }) {
  const highlight = React.useMemo(() => {
    const out = {}
    for (const s of sets || []) for (const id of s.films || []) out[id] = s.colour
    return Object.keys(out).length ? out : undefined
  }, [sets])
  const canvasRef = React.useRef(null)
  const [tip, setTip] = React.useState(null)
  const repaint = React.useRef(() => {})
  const view = React.useRef({
    yaw: 0.6, pitch: -0.35, zoom: 1, panX: 0, panY: 0,
    mode: null, last: null, idle: true, hoverId: null, pinch: null, started: null,
  })

  // The three axes arrive as separate distributions; a film is a point only if
  // all three placed it.
  const { points, axes, stats } = React.useMemo(() => {
    const list = (factors || []).slice(0, 3)
    if (list.length < 3) return { points: [], axes: [], stats: null }
    const byFilm = new Map()
    list.forEach((factor, k) => {
      for (const row of factor.distribution || []) {
        const seen = byFilm.get(row.film_id) || { title: row.title, v: [] }
        seen.v[k] = row.score
        byFilm.set(row.film_id, seen)
      }
    })
    const raw = [...byFilm.entries()]
      .filter(([, f]) => f.v.length === 3 && f.v.every((n) => typeof n === 'number'))
    // Centred on the average film, not on zero — zero is not the middle of any
    // of these axes, so an origin there would push the corpus into one corner.
    const stats = [0, 1, 2].map((k) => {
      const col = raw.map(([, f]) => f.v[k])
      const mean = col.reduce((a, b) => a + b, 0) / (col.length || 1)
      const sd = Math.sqrt(col.reduce((a, b) => a + (b - mean) ** 2, 0) / (col.length || 1)) || 1
      return { mean, sd }
    })
    const pts = raw.map(([id, f]) => {
      const x = (f.v[0] - stats[0].mean) / stats[0].sd / 3
      const y = -(f.v[1] - stats[1].mean) / stats[1].sd / 3
      const z = (f.v[2] - stats[2].mean) / stats[2].sd / 3
      return { id, title: f.title, raw: f.v, x, y, z, out: Math.hypot(x, y, z) }
    })
    // Label priority: the films furthest from the average one. Those are the
    // informative names — the middle of the cloud is where everything is.
    const order = [...pts].sort((a, b) => b.out - a.out)
    order.forEach((p, i) => { p.rank = i })
    return {
      points: pts, stats,
      axes: list.map((f) => ({ name: f.name, high: f.pole_high_label, low: f.pole_low_label })),
    }
  }, [factors])

  React.useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !points.length) return undefined
    const ctx = canvas.getContext('2d')
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    let frame

    const draw = () => {
      const v = view.current
      const dpr = window.devicePixelRatio || 1
      const w = canvas.clientWidth, h = canvas.clientHeight
      if (canvas.width !== Math.round(w * dpr)) {
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr)
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)
      const cx = w / 2 + v.panX, cy = h / 2 + v.panY
      const r = Math.min(w, h) * 0.42 * v.zoom
      const at = (q) => [cx + q.x * r, cy + q.y * r]

      // Axes, each in its own colour so a reader can tell which line is which
      // without tracing it back to a label.
      const ends = [[1, 0, 0], [0, -1, 0], [0, 0, 1]]
      ctx.lineWidth = 1.4
      // An arrowhead at each end, because a bare line does not say which way
      // the axis runs and the two labels are the only thing that did. Drawn
      // both ways: an axis has two directions and neither is the default.
      const head = (fromX, fromY, toX, toY, colour) => {
        const a = Math.atan2(toY - fromY, toX - fromX)
        ctx.fillStyle = colour
        ctx.beginPath()
        ctx.moveTo(toX, toY)
        ctx.lineTo(toX - 9 * Math.cos(a - 0.36), toY - 9 * Math.sin(a - 0.36))
        ctx.lineTo(toX - 9 * Math.cos(a + 0.36), toY - 9 * Math.sin(a + 0.36))
        ctx.closePath(); ctx.fill()
      }
      ends.forEach((e, k) => {
        const [ax, ay] = at(project({ x: -e[0], y: -e[1], z: -e[2] }, v.yaw, v.pitch))
        const [bx, by] = at(project({ x: e[0], y: e[1], z: e[2] }, v.yaw, v.pitch))
        ctx.strokeStyle = AXIS_COLOUR[k]
        ctx.globalAlpha = 0.5
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke()
        ctx.globalAlpha = 0.85
        head(ax, ay, bx, by, AXIS_COLOUR[k])
        head(bx, by, ax, ay, AXIS_COLOUR[k])
        ctx.globalAlpha = 1
        const label = axes[k]
        if (!label) return
        ctx.fillStyle = AXIS_COLOUR[k]
        ctx.font = '600 13.5px ui-sans-serif, system-ui, sans-serif'
        ctx.textBaseline = 'middle'
        ctx.lineJoin = 'round'
        // Kept inside the frame. The label hangs off the end of an axis, and
        // the end of an axis leaves the canvas as soon as you zoom or pan —
        // taking the only thing that says which pole is which with it. So the
        // anchor is clamped to the visible area and the alignment is chosen
        // from where it lands, not from where the axis points.
        const PAD = 8
        const write = (text, x, y, toward) => {
          const wide = ctx.measureText(text).width
          let px = x + (toward >= cx ? 13 : -13)
          let align = toward >= cx ? 'left' : 'right'
          if (align === 'left' && px + wide > w - PAD) {
            px = Math.min(px, w - PAD); align = 'right'
          } else if (align === 'right' && px - wide < PAD) {
            px = Math.max(px, PAD); align = 'left'
          }
          px = Math.min(Math.max(px, align === 'left' ? PAD : PAD + wide),
                        align === 'left' ? w - PAD - wide : w - PAD)
          const py = Math.min(Math.max(y, PAD + 6), h - PAD - 6)
          ctx.textAlign = align
          ctx.strokeStyle = 'rgba(15,12,10,0.95)'
          ctx.lineWidth = 4
          ctx.strokeText(text, px, py)
          ctx.fillText(text, px, py)
          ctx.lineWidth = 1.4
        }
        write(label.high || '', bx, by, bx)
        write(label.low || '', ax, ay, ax)
      })
      ctx.textAlign = 'left'

      const byId = new Map(points.map((p) => [p.id, p]))
      const drawn = points
        .map((p) => ({ p, q: project(p, v.yaw, v.pitch) }))
        .sort((a, b) => a.q.z - b.q.z)
      for (const { p, q } of drawn) {
        const depth = (q.z + 0.6) / 1.2
        const group = highlight?.[p.id]
        const active = v.hoverId === p.id
        ctx.globalAlpha = group || active ? 1 : 0.3 + depth * 0.42
        ctx.fillStyle = group || (active ? '#f5efe6' : '#8d8478')
        const [px, py] = at(q)
        ctx.beginPath()
        ctx.arc(px, py, (group || active ? 3.6 : 1.8) + depth * 1.2, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1

      // Names, most distinctive first, skipping any that would collide. The
      // budget grows with zoom, so the picture stays readable at rest and
      // fills in as you go looking.
      const budget = Math.min(LABEL_CAP, Math.round(LABEL_BASE * v.zoom * v.zoom))
      const taken = []
      ctx.font = '11px ui-sans-serif, system-ui, sans-serif'
      ctx.textBaseline = 'middle'
      const candidates = drawn
        .filter(({ p }) => p.rank < budget * 3 || v.hoverId === p.id || highlight?.[p.id])
        .sort((a, b) => (a.p.rank ?? 0) - (b.p.rank ?? 0))
      let placed = 0
      for (const { p, q } of candidates) {
        const forced = v.hoverId === p.id
        if (!forced && placed >= budget) break
        const [px, py] = at(q)
        if (px < -40 || px > w + 40 || py < -20 || py > h + 20) continue
        const text = p.title
        const tw = ctx.measureText(text).width
        const box = [px + 7, py - 7, tw + 8, 14]
        const clash = taken.some(([bx, by, bw, bh]) =>
          box[0] < bx + bw && box[0] + box[2] > bx && box[1] < by + bh && box[1] + box[3] > by)
        if (clash && !forced) continue
        taken.push(box)
        placed += 1
        ctx.strokeStyle = 'rgba(15,12,10,0.92)'
        ctx.lineWidth = 3
        ctx.strokeText(text, px + 7, py)
        ctx.fillStyle = forced ? '#f5efe6' : (highlight?.[p.id] || '#b3aa9e')
        ctx.fillText(text, px + 7, py)
      }

      // Set centres and the reader's own position, drawn last so nothing
      // covers them.
      const marks = []
      for (const s of sets || []) {
        const found = (s.films || []).map((id) => byId.get(id)).filter(Boolean)
        if (!found.length) continue
        marks.push({
          colour: s.colour, label: s.name,
          x: found.reduce((a, p) => a + p.x, 0) / found.length,
          y: found.reduce((a, p) => a + p.y, 0) / found.length,
          z: found.reduce((a, p) => a + p.z, 0) / found.length,
        })
      }
      if (viewer && stats) {
        marks.push({
          colour: '#f5efe6', label: viewer.label || 'You', ring: true,
          x: viewer.scores[0] / stats[0].sd / 3,
          y: -viewer.scores[1] / stats[1].sd / 3,
          z: viewer.scores[2] / stats[2].sd / 3,
        })
      }
      // A crosshair along the three axes rather than a ring. A circle competes
      // with the dots it sits among — same shape, slightly bigger — whereas
      // three ticks running parallel to the axes read as a POSITION in the
      // space and stay legible whichever way the cloud is turned.
      const TICK = 0.13
      for (const m of marks) {
        const [mx, my] = at(project(m, v.yaw, v.pitch))
        ctx.strokeStyle = m.colour
        ctx.fillStyle = m.colour
        ctx.lineWidth = m.ring ? 2.4 : 1.8
        for (const e of [[TICK, 0, 0], [0, TICK, 0], [0, 0, TICK]]) {
          const [sx, sy] = at(project(
            { x: m.x - e[0], y: m.y - e[1], z: m.z - e[2] }, v.yaw, v.pitch))
          const [ex, ey] = at(project(
            { x: m.x + e[0], y: m.y + e[1], z: m.z + e[2] }, v.yaw, v.pitch))
          ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex, ey); ctx.stroke()
        }
        ctx.beginPath(); ctx.arc(mx, my, m.ring ? 3.4 : 2.6, 0, Math.PI * 2); ctx.fill()
        ctx.font = '600 11px ui-sans-serif, system-ui, sans-serif'
        ctx.strokeStyle = 'rgba(15,12,10,0.92)'; ctx.lineWidth = 3
        ctx.strokeText(m.label, mx + 13, my)
        ctx.fillText(m.label, mx + 13, my)
      }

      if (!reduced && v.idle) {
        v.started ??= performance.now()
        if (performance.now() - v.started < DEMO_MS) {
          v.yaw += IDLE_SPIN
          frame = requestAnimationFrame(draw)
        } else {
          v.idle = false
        }
      }
    }

    // Registered here rather than as onWheel: React attaches wheel handlers
    // passively, so preventDefault inside one is ignored and the page scrolls
    // away under the cursor while you are trying to zoom.
    // Gentle, and normalised for how the browser reports the wheel: Firefox
    // sends lines rather than pixels, and a trackpad sends many small events
    // where a mouse sends few large ones. Scaling by the actual delta rather
    // than its sign keeps both feeling the same.
    const wheel = (event) => {
      event.preventDefault()
      const v = view.current
      v.idle = false
      const px = event.deltaMode === 1 ? event.deltaY * 16
        : event.deltaMode === 2 ? event.deltaY * 400 : event.deltaY
      const step = Math.max(-60, Math.min(60, px))
      v.zoom = Math.max(0.6, Math.min(9, v.zoom * Math.exp(-step * 0.0016)))
      draw()
    }
    canvas.addEventListener('wheel', wheel, { passive: false })

    repaint.current = draw
    draw()
    if (!reduced && view.current.idle) frame = requestAnimationFrame(draw)
    window.addEventListener('resize', draw)
    return () => {
      cancelAnimationFrame(frame)
      canvas.removeEventListener('wheel', wheel)
      window.removeEventListener('resize', draw)
      repaint.current = () => {}
    }
  }, [points, axes, highlight, sets, viewer, stats])

  const hit = (event) => {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const v = view.current
    const px = event.clientX - rect.left, py = event.clientY - rect.top
    const cx = rect.width / 2 + v.panX, cy = rect.height / 2 + v.panY
    const r = Math.min(rect.width, rect.height) * 0.42 * v.zoom
    let best = null, bestD = 11
    for (const p of points) {
      const q = project(p, v.yaw, v.pitch)
      const d = Math.hypot(cx + q.x * r - px, cy + q.y * r - py)
      if (d < bestD) { bestD = d; best = p }
    }
    return best
  }

  const onDown = (event) => {
    const v = view.current
    v.idle = false
    v.mode = event.shiftKey || event.button === 1 || event.button === 2 ? 'pan' : 'turn'
    v.last = { x: event.clientX, y: event.clientY }
    v.moved = false
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  const onMove = (event) => {
    const v = view.current
    if (v.mode) {
      const dx = event.clientX - v.last.x, dy = event.clientY - v.last.y
      if (Math.abs(dx) + Math.abs(dy) > 2) v.moved = true
      if (v.mode === 'pan') { v.panX += dx; v.panY += dy }
      else {
        v.yaw += dx * 0.008
        v.pitch = Math.max(-1.4, Math.min(1.4, v.pitch + dy * 0.008))
      }
      v.last = { x: event.clientX, y: event.clientY }
      if (v.hoverId) { v.hoverId = null; setTip(null) }
      repaint.current()
      return
    }
    const found = hit(event)
    const id = found?.id ?? null
    if (id !== v.hoverId) {
      v.hoverId = id
      setTip(found ? { title: found.title, raw: found.raw } : null)
      repaint.current()
    }
  }

  const onUp = () => { view.current.mode = null }

  const onClick = (event) => {
    const v = view.current
    if (v.moved || !onSelect) return
    const found = hit(event)
    if (found) onSelect(found.id)
  }

  const reset = () => {
    const v = view.current
    v.zoom = 1; v.panX = 0; v.panY = 0; v.yaw = 0.6; v.pitch = -0.35
    v.hoverId = null; setTip(null)
    // Deliberately does NOT restart the drift: a reader pressing reset wants
    // the view back, not the introduction again.
    repaint.current()
  }

  if (!points.length) return null
  return (
    <div className="film-cloud">
      <canvas
        ref={canvasRef} style={{ inlineSize: '100%', blockSize: `${SIZE}px` }}
        onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp}
        onPointerLeave={() => { onUp(); view.current.hoverId = null; setTip(null); repaint.current() }}
        onClick={onClick} onContextMenu={(e) => e.preventDefault()}
        role="img"
        aria-label={`All ${points.length} films placed on the three axes. `
          + 'The tables below list the same positions.'} />
      <button type="button" className="cloud-reset" onClick={reset}>reset view</button>
      {tip && (
        <div className="cloud-tip">
          <b>{tip.title}</b>
          {axes.map((a, k) => (
            <span key={a.name}>
              {tip.raw[k] >= 0 ? '+' : '−'}{Math.abs(tip.raw[k]).toFixed(2)} {a.name}
            </span>
          ))}
        </div>
      )}
      <p className="cloud-note">
        Drag to turn, scroll to zoom, shift-drag to pan, click a film to open it. Names
        appear for the films furthest from the average one, and more of them as you zoom
        in. Each dot is a film, centred on the average film rather than on zero.
        The width is measured far better than the depth: a film's position on{' '}
        <em>{axes[0]?.name}</em> reproduces at 0.89 across a split of the propositions,
        and on the other two at about 0.24.
      </p>
    </div>
  )
}
