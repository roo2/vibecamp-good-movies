// What the deck does with a hand of cards it has already seen.
//
// The bug this covers reads as a black screen. Swiping posts the vote and moves
// on without waiting for it, so the server — which only knows a film is spent
// once its vote arrives — can deal the same films straight back. The deck drops
// every one of them as stale, ends up with nothing to show, and renders
// "Finding films for you…", which on a phone is a faint grey line on a near
// black page. It never recovered: the refill runs from an effect watching the
// queue length and the loading state, and after an empty hand neither has
// changed, so nothing asks again. Reloading the page cleared the record of what
// had been swiped and dealt the same films back, which is why a refresh
// "fixed" it.
//
// Tested as functions rather than as markup because none of it is visible in a
// render — the screen looks identical whether it is about to recover or has
// stopped forever.
import assert from 'node:assert'
import { freshCards, hasNewCards } from '../src/screens/ShortlistPage.jsx'

let pass = 0, fail = 0
const ok = (name, cond) => {
  if (cond) { pass++; console.log(`ok    ${name}`) }
  else { fail++; console.log(`FAIL  ${name}`) }
}

const card = (id) => ({ id, title: id })
const swiped = (...ids) => new Set(ids)

// ---- the merge -------------------------------------------------------------
ok('a card already in hand is not dealt twice',
   freshCards([card('a'), card('b')], [card('a')], swiped()).length === 1)
ok('a card already swiped is dropped even though the server still offers it',
   freshCards([card('a'), card('b')], [], swiped('a')).map((f) => f.id).join() === 'b')
ok('genuinely new cards all come through',
   freshCards([card('c'), card('d')], [card('a')], swiped('b')).length === 2)
ok('a null card from the one-at-a-time shape is not merged',
   freshCards([null], [], swiped()).length === 0)

// ---- the retry decision ----------------------------------------------------
// This is the whole fix. The queue-merge behaviour above was already correct;
// what was missing was noticing that it had produced nothing.
ok('a hand of nothing but films this person swiped counts as no cards',
   hasNewCards([card('a'), card('b')], swiped('a', 'b')) === false)
ok('one unseen film in the hand is enough to carry on',
   hasNewCards([card('a'), card('b')], swiped('a')) === true)
ok('an empty hand is no cards',
   hasNewCards([], swiped()) === false)
// The refill fires at two cards left, so the server's six are usually the two
// still in hand plus four whose votes are in flight. Nothing merges — but the
// two in hand are still showable, and swiping them changes the queue length,
// which is what asks again. No retry is needed and none is wanted.
const inHand = [card('e'), card('f')]
const dealtEarly = [card('a'), card('b'), card('c'), card('d'), card('e'), card('f')]
const votesEarly = swiped('a', 'b', 'c', 'd')
ok('a refill that merges nothing while cards remain in hand is not a failure',
   freshCards(dealtEarly, inHand, votesEarly).length === 0
   && hasNewCards(dealtEarly, votesEarly) === true)

// And the moment that produced the stuck screen: the last two have been swiped
// too, so the hand is empty and every card the server deals is one of the six
// whose votes have not landed. Before the fix this was read as an answer, the
// queue stayed empty, and nothing ever asked again.
const dealtStuck = [card('a'), card('b'), card('c'), card('d'), card('e'), card('f')]
const votesStuck = swiped('a', 'b', 'c', 'd', 'e', 'f')
ok('an empty hand dealt only spent films is a race, not an ending',
   freshCards(dealtStuck, [], votesStuck).length === 0
   && hasNewCards(dealtStuck, votesStuck) === false)

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
