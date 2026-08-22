import { apiClient } from './apiClient.js'

export function submitTestResult(access, answers) {
  return apiClient.post('/api/test/results', { answers }, {
    headers: { 'X-Session-Token': access.token },
  })
}
