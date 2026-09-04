// One colour per POLE, assigned centrally and used everywhere.
//
// Before this, colour meant three different things in three places: the plot
// gave each AXIS one colour shared by both its ends, the film panel coloured by
// which end a film sat at, and the taste rows coloured by which dimension. So
// the same amber marked "the horizontal axis" on the plot, "the high end" in the
// panel, and "the first taste dimension" in the profile. A reader could not
// carry anything they learnt from one view into another.
//
// Now a pole has a colour, and it keeps it: Redemption is the same amber on the
// plot, in the film panel and on a person's compass.
//
// The two families are kept apart by construction rather than by care. The moral
// poles take six hues spaced around the wheel. Taste takes five hues of its own,
// none of them a moral hue, and distinguishes its two ends by LIGHTNESS within
// the dimension's hue rather than by a seventh, eleventh, sixteenth colour —
// past about six, hues stop being tellable apart on a dark ground, and a
// dimension whose ends are a pale and a saturated version of one colour reads as
// one axis with two directions, which is what it is.

// Moral poles, low end first. Ordered by axis, so axis 0's two ends are the
// first pair. Six distinct hues: violet, amber, coral, teal, green, blue.
const MORAL = [
  { low: '#9b7fd4', high: '#eda36b' },
  { low: '#e0797f', high: '#5cc3c0' },
  { low: '#8fbf6a', high: '#6f9fe0' },
]

// Taste hues, one per dimension in the order the profile shows them. Chosen to
// avoid every moral hue above: rose, gold, sky, mint, plum.
const TASTE_HUES = ['#d96ba0', '#c9a227', '#4fa3d1', '#63c9a0', '#a86bd9']

// The pale end of a taste dimension. Mixed toward the page rather than
// lightened, so it recedes on a dark ground instead of glowing.
function paler(hex) {
  const n = parseInt(hex.slice(1), 16)
  const mix = (c) => Math.round(c * 0.55 + 0x2a * 0.45)
  return `rgb(${mix((n >> 16) & 255)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`
}

export function polePair(family, index) {
  if (family === 'taste') {
    const hue = TASTE_HUES[index % TASTE_HUES.length]
    return { low: paler(hue), high: hue }
  }
  return MORAL[index % MORAL.length]
}

// A single pole, for callers that draw one end at a time — the plot's four
// labels, for instance.
export function poleColour(family, index, side) {
  return polePair(family, index)[side === 'low' ? 'low' : 'high']
}
