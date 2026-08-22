import { mockCompassProfile } from '../data/mockCompassProfile.js'

// Backend seam: replace with fetch('/api/profile/compass') once scores are available.
export async function loadCompassProfile({ answers } = {}) {
  // `answers` is accepted now so the future API receives the completed test
  // payload without a screen-level integration rewrite.
  void answers
  return mockCompassProfile
}
