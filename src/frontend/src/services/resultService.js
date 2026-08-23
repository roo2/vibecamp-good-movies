import { apiClient } from './apiClient.js'

export function submitTestResult(access, answers, sessionShareToken) {
  return apiClient.post('/api/test/results', { answers, session_share_token: sessionShareToken }, {
    headers: { 'X-Session-Token': access.token },
  })
}

export function loadCurrentTestResult(access, sessionShareToken) {
  return apiClient.get(`/api/test/results/current?share_token=${encodeURIComponent(sessionShareToken)}`, {
    headers: { 'X-Session-Token': access.token },
  })
}
