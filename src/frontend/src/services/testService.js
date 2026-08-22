import { apiClient } from './apiClient.js'

export async function loadTestQuestions() {
  const payload = await apiClient.get('/api/test/questions')
  return payload.questions
}
