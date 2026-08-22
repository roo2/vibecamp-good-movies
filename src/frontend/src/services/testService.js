import { apiClient } from './apiClient.js'

export async function loadTestQuestions(access, shareToken) {
  const payload = await apiClient.get(`/api/test/questions?share_token=${encodeURIComponent(shareToken)}`, {
    headers: { 'X-Session-Token': access.token },
  })
  return payload.questions
}
