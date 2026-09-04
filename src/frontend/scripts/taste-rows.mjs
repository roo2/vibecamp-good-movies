// Which taste dimensions a film's card will name.
//
// The rule is small and entirely about judgement — how far from typical a film
// has to be before the card asserts anything, which of its dimensions win, and
// which colour each keeps. None of that is visible in a render, so it is tested
// as a function rather than as markup.
//
// The synthetic corpus runs always. The live one runs when a snapshot is passed
// or reachable, because the interesting cases are real: the 2019 Lion King sits
// within a third of a standard deviation of the centre on every dimension, and
// the card used to call it a slapdash spectacle on that basis.
import assert from 'node:assert'
import { readFileSync } from 'node:fs'
import { tasteRowsFor, TASTE_FLOOR } from '../src/components/FilmAxisStrip.jsx'

const SNAPSHOT = 'https://d1t4mo1ivnr71p.cloudfront.net/api/factors/taste'
let live = null
try {
  live = process.argv[2]
    ? JSON.parse(readFileSync(process.argv[2], 'utf8'))
    : await (await fetch(SNAPSHOT, { signal: AbortSignal.timeout(20000) })).json()
} catch {
  console.log('note  no corpus reachable; running the synthetic cases only\n')
}
let pass = 0, fail = 0
const ok = (name, cond) => {
  if (cond) { pass++; console.log(`ok    ${name}`) }
  else { fail++; console.log(`FAIL  ${name}`) }
}

// ---- the film that prompted this ------------------------------------------
if (live) {
const remake = live.films.find((f) => f.title === 'The Lion King' && f.year === 2019)
const original = live.films.find((f) => f.title === 'The Lion King' && f.year === 1994)
const rows2019 = tasteRowsFor(live, remake.film_id, 2)
const rows1994 = tasteRowsFor(live, original.film_id, 2)
ok('the 2019 remake now claims nothing', rows2019.length === 0)
ok('the 1994 film still reads clearly', rows1994.length === 2)
console.log('      1994: ' + rows1994.map((r) =>
  `${r.at >= 0 ? r.dim.pole_high : r.dim.pole_low} (z ${r.z.toFixed(2)})`).join(', '))

// ---- the rule, across the whole corpus ------------------------------------
let none = 0, some = 0, worst = 0
for (const f of live.films) {
  const rows = tasteRowsFor(live, f.film_id, 2)
  rows.length ? some++ : none++
  for (const r of rows) worst = Math.max(worst, Math.abs(r.z) < TASTE_FLOOR ? 1 : 0)
  for (let i = 1; i < rows.length; i++) {
    assert(Math.abs(rows[i - 1].at) >= Math.abs(rows[i].at), 'out of order')
  }
}
ok('nothing below the floor is ever named', worst === 0)
ok('most films still say something', some > none)
console.log(`      ${some} films read, ${none} stay blank (${(none / live.films.length * 100).toFixed(0)}%)`)
}

// ---- a corpus built to break it -------------------------------------------
const dims = [0, 1, 2].map((i) => ({
  dim_id: i, status: 'named', profile_reliability: 0.5 - i * 0.1,
  pole_low: `low${i}`, pole_high: `high${i}`,
}))
const films = []
for (let i = 0; i < 40; i++) {
  films.push({ film_id: `f${i}`, position: { 0: i % 5, 1: i % 5, 2: i % 5 } })
}
// Flat on the two most reliable dimensions, extreme on the third.
films.push({ film_id: 'odd', position: { 0: 2, 1: 2, 2: 40 } })
// Inside the floor on every dimension.
films.push({ film_id: 'dull', position: { 0: 2.1, 1: 2.1, 2: 2.1 } })
const synth = { dimensions: dims, films }
const odd = tasteRowsFor(synth, 'odd', 2)
ok('the strongest dimension is chosen over the first-listed',
   odd.length === 1 && odd[0].dim.dim_id === 2)
ok('and it keeps its palette index from the shared order', odd[0].index === 2)
ok('a film inside the floor everywhere is left blank',
   tasteRowsFor(synth, 'dull', 2).length === 0)
ok('the limit is still respected', tasteRowsFor(synth, 'f0', 1).length <= 1)

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
