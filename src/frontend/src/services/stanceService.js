import { apiClient } from './apiClient.js'

// The moral position somebody CHOSE, which is the only kind this product can
// honestly use. A position read off what they like is mostly their taste with
// moral labels on it — placed twice from disjoint halves of 160,952 raters'
// liked films, the three axes agree at 0.54 / 0.24 / 0.04 raw, and 0.08 / 0.12 /
// -0.06 once taste is taken out of the film positions.
export function loadStance(access) {
  return apiClient.get('/api/profile/stance', {
    headers: { 'X-Session-Token': access.token },
  })
}

// `stanceId` of null is the don't-care answer, and is stored rather than
// discarded: the product has to tell somebody who declined from somebody who
// was never asked, or it asks the first person again forever.
// `shareToken` re-ranks the deck they are looking at. Without it the choice
// saves and the same cards keep coming, because a session materialises its order
// once and keeps it.
export function saveStance(access, stanceId, weight, shareToken = null) {
  return apiClient.put('/api/profile/stance',
    { stance_id: stanceId, weight, share_token: shareToken },
    { headers: { 'X-Session-Token': access.token } })
}
