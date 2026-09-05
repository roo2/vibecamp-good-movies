// Render every screen once, with nothing mocked but the browser.
//
// Effects do not run under server rendering, so this does not prove a page
// LOOKS right. It proves each module body executes — which is the class of
// failure that blanks a page with no error visible to the user and nothing in
// the network tab: a const read before its declaration, an import left behind
// by a refactor, a reference to state that was deleted.
//
// Both have happened here. Removing the model picker left a setWithdrawn call
// behind, caught by a one-off render. Adding the axis picker to the corpus page
// put a useMemo over `factors` above the line declaring it, which was not
// caught, shipped, and turned #/corpus black.
//
// Screens are imported explicitly rather than read from the directory: a
// bundler cannot follow a computed path, and a list you have to edit is a list
// that says what is covered.
import { readFileSync } from 'node:fs'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import StancePicker from '../src/components/StancePicker.jsx'
import AtlasPage from '../src/screens/AtlasPage.jsx'
import CompassScreen from '../src/screens/CompassScreen.jsx'
import CorpusPage from '../src/screens/CorpusPage.jsx'
import LandingPage from '../src/screens/LandingPage.jsx'
import MatchPage from '../src/screens/MatchPage.jsx'
import SeenItPage from '../src/screens/SeenItPage.jsx'
import SessionLobbyPage from '../src/screens/SessionLobbyPage.jsx'
import SessionWaitingPage from '../src/screens/SessionWaitingPage.jsx'
import ShortlistPage from '../src/screens/ShortlistPage.jsx'
import StancePage from '../src/screens/StancePage.jsx'
import TastePage from '../src/screens/TastePage.jsx'
import TestCompletePage from '../src/screens/TestCompletePage.jsx'

// Not a screen, but it renders over one and only when a button is pressed, so
// nothing else here would execute its module body.
const SCREENS = {
  StancePicker, StancePage,
  AtlasPage, CompassScreen, CorpusPage, LandingPage, MatchPage, SeenItPage,
  SessionLobbyPage, SessionWaitingPage, ShortlistPage, TastePage, TestCompletePage,
}

globalThis.window = {
  location: { hash: '#/', origin: 'https://example.test', pathname: '/' },
  addEventListener() {}, removeEventListener() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  requestAnimationFrame: (f) => f(), scrollTo() {},
}
globalThis.document = {
  documentElement: { style: {} }, addEventListener() {}, removeEventListener() {},
}
globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
// Never resolves: every screen must survive its own loading state, which is what
// a viewer sees first anyway.
globalThis.fetch = () => new Promise(() => {})

const props = {
  onBack() {}, onContinue() {}, onAtlas() {}, navigate() {},
  // A signed-in shape rather than null: several screens read access.user on
  // the first render, and the signed-OUT path is guarded by the router.
  access: { token: 't', user: { id: 'u', name: '' } },
  shareToken: null, solo: true,
  // Prop names differ between screens; each needs whichever shape it reads on
  // its first render.
  session: { share_token: 't', members: [], ready: false, status: 'waiting' },
  groupSession: { share_token: 't', members: [], ready: false },
  status: { members: [], ready: false },
}

let failed = 0
for (const [name, Screen] of Object.entries(SCREENS)) {
  try {
    renderToStaticMarkup(React.createElement(Screen, props))
    console.log(`ok    ${name}`)
  } catch (error) {
    failed += 1
    console.log(`FAIL  ${name}: ${error.constructor.name}: ${String(error.message).slice(0, 100)}`)
  }
}
const total = Object.keys(SCREENS).length
// Every route the app navigates to must be a route it knows.
//
// `currentRoute` resolves an unknown hash to '/', which is right for a typo and
// a trap for a new screen: the URL changes, nothing throws, and the landing page
// renders forever. Shipping '/stance' without adding it to the set did exactly
// that, and nothing above caught it — rendering the screen directly works fine,
// because the screen was never the problem.
const source = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')
const declared = new Set(
  [...(source.match(/const routes = new Set\(\[([^\]]*)\]/) || [null, ''])[1]
    .matchAll(/'([^']+)'/g)].map((hit) => hit[1]))
const targets = [...source.matchAll(/navigate\('([^']+)'\)/g)].map((hit) => hit[1])
const orphans = [...new Set(targets)].filter((route) => !declared.has(route)
  && !route.startsWith('/join/'))
if (orphans.length) {
  console.error(`FAIL  navigates to routes it does not know: ${orphans.join(', ')}`)
  console.error('      add them to `routes` in App.jsx, or they resolve to the landing page')
  failed += 1
}
else {
  console.log(`ok    ${targets.length} navigate targets, all declared among ${declared.size} routes`)
}

console.log(`\n${total - failed} of ${total} screens execute`)
process.exit(failed ? 1 : 0)

