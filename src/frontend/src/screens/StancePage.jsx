import React from 'react'
import StancePicker from '../components/StancePicker.jsx'

// The first thing the flow asks, before a single film.
//
// It comes first because it is the only question here whose answer cannot be
// worked out from anything else. Everything after this — twenty films, then the
// deck — says what somebody LIKES, and liking is not believing: placing 160,952
// outside raters twice from disjoint halves of their liked films, the three
// moral axes agree at 0.54 / 0.24 / 0.04, and at 0.08 / 0.12 / -0.06 once taste
// is taken out of the film positions. Asked last it would look like a footnote
// to the ratings; asked first it is what the ratings are read against.
//
// It is also the cheapest screen in the flow — one tap, or one tap to decline —
// which is a good place to begin something that is about to ask for twenty.
//
// NO PROGRESS BAR. That bar counts films and only films, and this is not one: a
// "1 / 21" here would promise a different shape of task than the one that
// follows.
// NOTHING SKIPS PAST THIS SCREEN. It used to move anybody who had already
// answered straight on to the films, so that a guest reaching it by the same
// route as the host was not asked twice. The cost was worse than the saving:
// reloading the page bounced you into the quiz, because a reload is
// indistinguishable from arriving, and the screen you were looking at vanished
// under you. Somebody who has answered sees their answer already selected,
// which is not the same as being asked again.
export default function StancePage({ access, shareToken, onContinue }) {
  return (
    <main className="app-page">
      <section className="phone-screen stance-screen">
        <p className="screen-label">Your moral position</p>
        <StancePicker
          access={access}
          shareToken={shareToken}
          onClose={onContinue}
          closeLabel="Continue"
        />
      </section>
    </main>
  )
}
