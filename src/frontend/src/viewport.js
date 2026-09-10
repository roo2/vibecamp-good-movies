// Measure the viewport instead of asking CSS to infer it.
//
// Every screen in this app is built to be exactly as tall as the window: a
// column with `min-height: 100svh`, a primary action pushed to its bottom with
// `margin-top: auto`. That is the right shape and it has now failed the same
// way three times — the buttons "aren't there until you interact with the page",
// on the taste read, on the compass, on the profile.
//
// The layout is not what is wrong. Measured at 553, 600, 667, 760, 844 and 992,
// the action lands inside the fold at every one, painted, opacity 1, with the
// page unscrolled. What is wrong is the number `svh` resolves to on the FIRST
// paint on a mobile browser, before the toolbar has settled: the column is laid
// out against a height the window does not have, the action goes wherever that
// puts it, and the first scroll or rotate fires a resize, the units re-resolve,
// and the button "appears". Interaction was never the fix — it was the repaint.
//
// So the height stops being inferred. `window.innerHeight` is a measurement of
// the window as it is at the moment it is read, it is correct on the first
// frame, and it is re-read whenever the window changes. `--app-vh` carries it
// to the stylesheet, where every rule that wanted `100svh` prefers it and falls
// back to `100svh` if this never runs.
//
// `visualViewport` is watched as well as `resize`, because on iOS the toolbar
// retracting changes the visual viewport without always firing a window resize
// — which is the exact moment this is about.

const PROPERTY = '--app-vh'

function apply() {
  // The layout viewport, not `visualViewport.height`: the second shrinks when
  // the on-screen keyboard opens, and a screen that reflowed to half its height
  // because somebody focused a text field would be a worse bug than the one
  // this fixes.
  document.documentElement.style.setProperty(PROPERTY, `${window.innerHeight}px`)
}

export function trackViewportHeight() {
  if (typeof window === 'undefined') return
  apply()

  // Twice more on the way in. Mobile browsers report a height during load that
  // they revise once the toolbar is in its resting place, and neither the
  // timing nor the number of revisions is something to guess at — these two are
  // cheap and cover both of the moments it changes.
  window.addEventListener('load', apply, { once: true })
  window.requestAnimationFrame(apply)

  window.addEventListener('resize', apply, { passive: true })
  window.addEventListener('orientationchange', apply, { passive: true })
  window.visualViewport?.addEventListener('resize', apply, { passive: true })

  // Coming back from the back/forward cache, where a restored page can carry
  // the height it had when it left.
  window.addEventListener('pageshow', apply, { passive: true })
}
