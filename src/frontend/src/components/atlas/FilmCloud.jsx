import React from 'react'

// Every film at once, in the three dimensions the corpus actually produced.
//
// WHY THREE AND NOT TWO. The cloud is not flat. Standardised, its principal
// variances run 1.20 / 1.00 / 0.80 — 40%, 33% and 27% of the spread — so a flat
// projection would discard a real quarter of it, and the axes are close to
// uncorrelated in where they put films (-0.14, -0.05, -0.10). There is no
// degenerate direction to drop.
//
// WHY NO LIBRARY. 565 points with an orthographic projection is a rotation
// matrix and a loop. three.js would roughly triple a 78KB bundle to draw dots.
//
// WHAT THIS CANNOT SHOW, and the caption says so: the axes are not equally
// well measured. A film's position on the first reproduces at 0.89 across a
// split of the propositions; on the other two, at about 0.24. Width is solid,
// depth and height are soft, and a cube invites you to read all three alike.
const SIZE = 460
const IDLE_SPIN = 0.0022

function project(p, yaw, pitch) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw)
  const cp = Math.cos(pitch), sp = Math.sin(pitch)
  const x = p.x * cy - p.z * sy
  const z1 = p.x * sy + p.z * cy
  const y = p.y * cp - z1 * sp
  const z = p.y * sp + z1 * cp
  return { x, y, z }
}

export default function FilmCloud({ factors, highlight }) {
  const canvasRef = React.useRef(null)
  const boxRef = React.useRef(null)
  const [hover, setHover] = React.useState(null)
  const view = React.useRef({ yaw: 0.6, pitch: -0.35, dragging: false, idle: true })
  // Set by the drawing effect so the pointer handlers can repaint immediately
  // rather than waiting for the idle loop, which stops on first interaction.
  const repaint = React.useRef(() => {})

  // The three axes are sent as separate distributions; a film is a point only
  // if all three placed it.
  const { points, axes } = React.useMemo(() => {
    const list = (factors || []).slice(0, 3)
    if (list.length < 3) return { points: [], axes: [] }
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
    // Centre on the average film and scale by spread, so the box is filled
    // evenly and the origin means "typical", not "zero" — which is not the
    // middle of any of these axes.
    const stats = [0, 1, 2].map((k) => {
      const col = raw.map(([, f]) => f.v[k])
      const mean = col.reduce((a, b) => a + b, 0) / (col.length || 1)
      const sd = Math.sqrt(col.reduce((a, b) => a + (b - mean) ** 2, 0) / (col.length || 1)) || 1
      return { mean, sd }
    })
    return {
      points: raw.map(([id, f]) => ({
        id,
        title: f.title,
        raw: f.v,
        x: (f.v[0] - stats[0].mean) / stats[0].sd / 3,
        y: -(f.v[1] - stats[1].mean) / stats[1].sd / 3,
        z: (f.v[2] - stats[2].mean) / stats[2].sd / 3,
      })),
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
      const dpr = window.devicePixelRatio || 1
      const w = canvas.clientWidth, h = canvas.clientHeight
      if (canvas.width !== w * dpr) { canvas.width = w * dpr; canvas.height = h * dpr }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)
      const { yaw, pitch } = view.current
      const cx = w / 2, cy = h / 2, r = Math.min(w, h) * 0.42

      // The three axis lines, drawn behind the films.
      const ends = [[1, 0, 0], [0, -1, 0], [0, 0, 1]]
      ctx.lineWidth = 1
      ends.forEach((e, k) => {
        const a = project({ x: -e[0], y: -e[1], z: -e[2] }, yaw, pitch)
        const b = project({ x: e[0], y: e[1], z: e[2] }, yaw, pitch)
        ctx.strokeStyle = k === 0 ? '#4a3f36' : '#332b25'
        ctx.beginPath()
        ctx.moveTo(cx + a.x * r, cy + a.y * r)
        ctx.lineTo(cx + b.x * r, cy + b.y * r)
        ctx.stroke()
        const label = axes[k]
        if (label) {
          ctx.fillStyle = k === 0 ? '#8d8478' : '#6a6158'
          ctx.font = '10px ui-sans-serif, system-ui, sans-serif'
          ctx.fillText(label.high || '', cx + b.x * r + 4, cy + b.y * r)
          ctx.fillText(label.low || '', cx + a.x * r + 4, cy + a.y * r)
        }
      })

      const drawn = points
        .map((p) => ({ p, q: project(p, yaw, pitch) }))
        .sort((a, b) => a.q.z - b.q.z)
      for (const { p, q } of drawn) {
        const depth = (q.z + 0.6) / 1.2
        const group = highlight?.[p.id]
        ctx.globalAlpha = group ? 1 : 0.28 + depth * 0.42
        ctx.fillStyle = group || (hover?.id === p.id ? '#f5efe6' : '#8d8478')
        ctx.beginPath()
        ctx.arc(cx + q.x * r, cy + q.y * r,
                (group || hover?.id === p.id ? 3.4 : 1.7) + depth * 1.2, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1
      if (!reduced && view.current.idle) {
        view.current.yaw += IDLE_SPIN
        frame = requestAnimationFrame(draw)
      }
    }

    repaint.current = draw
    draw()
    if (!reduced && view.current.idle) frame = requestAnimationFrame(draw)
    window.addEventListener('resize', draw)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', draw)
      repaint.current = () => {}
    }
  }, [points, axes, hover, highlight])

  const pointerAt = (event) => {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const px = event.clientX - rect.left, py = event.clientY - rect.top
    const cx = rect.width / 2, cy = rect.height / 2
    const r = Math.min(rect.width, rect.height) * 0.42
    const { yaw, pitch } = view.current
    let best = null, bestD = 10
    for (const p of points) {
      const q = project(p, yaw, pitch)
      const d = Math.hypot(cx + q.x * r - px, cy + q.y * r - py)
      if (d < bestD) { bestD = d; best = p }
    }
    return best
  }

  const onDown = (event) => {
    view.current.dragging = true
    view.current.idle = false
    view.current.last = { x: event.clientX, y: event.clientY }
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }
  const onMove = (event) => {
    if (view.current.dragging) {
      const { last } = view.current
      view.current.yaw += (event.clientX - last.x) * 0.008
      view.current.pitch = Math.max(-1.4, Math.min(1.4,
        view.current.pitch + (event.clientY - last.y) * 0.008))
      view.current.last = { x: event.clientX, y: event.clientY }
      setHover((h) => (h ? null : h))
      repaint.current()
      return
    }
    const found = pointerAt(event)
    setHover(found ? { id: found.id, title: found.title, raw: found.raw,
                       x: event.clientX, y: event.clientY } : null)
  }
  const onUp = () => { view.current.dragging = false }

  if (!points.length) return null
  return (
    <div className="film-cloud" ref={boxRef}>
      <canvas
        ref={canvasRef} style={{ inlineSize: '100%', blockSize: `${SIZE}px` }}
        onPointerDown={onDown} onPointerMove={onMove}
        onPointerUp={onUp} onPointerLeave={() => { onUp(); setHover(null) }}
        role="img"
        aria-label={`Every film placed on the three axes. ${points.length} films. `
          + `The tables below list the same positions.`} />
      {hover && (
        <div className="cloud-tip" style={{ left: 12, top: 12 }}>
          <b>{hover.title}</b>
          {axes.map((a, k) => (
            <span key={a.name}>
              {hover.raw[k] >= 0 ? '+' : '−'}{Math.abs(hover.raw[k]).toFixed(2)} {a.name}
            </span>
          ))}
        </div>
      )}
      <p className="cloud-note">
        Drag to turn it. Each dot is a film, placed on all three axes and centred on the
        average film rather than on zero. The width is measured far better than the depth:
        a film's position on <em>{axes[0]?.name}</em> reproduces at 0.89 across a split of
        the propositions, and on the other two at about 0.24.
      </p>
    </div>
  )
}
