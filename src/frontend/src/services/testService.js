import { apiClient } from './apiClient.js'

const questionRequests = new Map()

export function loadTestQuestions(access, shareToken) {
  const requestKey = `${access.user.id}:${shareToken}`
  if (!questionRequests.has(requestKey)) {
    const request = apiClient.get(`/api/test/questions?share_token=${encodeURIComponent(shareToken)}`, {
      headers: { 'X-Session-Token': access.token },
    }).then((payload) => payload.questions).catch((error) => {
      questionRequests.delete(requestKey)
      throw error
    })
    questionRequests.set(requestKey, request)
  }
  return questionRequests.get(requestKey)
}

export function preloadTestQuestions(access, shareToken) {
  loadTestQuestions(access, shareToken).catch(() => {})
}
