import { mockQuestions } from '../data/mockQuestions.js'

// Backend seam: replace this with fetch('/api/test/questions') when the API exists.
// Components only depend on this function, not on the mock-data file.
export async function loadTestQuestions() {
  return mockQuestions
}
