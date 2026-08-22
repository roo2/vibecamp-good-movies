import { apiClient } from './apiClient.js'

export function loadMoralProfile(access) {
  return apiClient.get('/api/profile/moral', {
    headers: { 'X-Session-Token': access.token },
  })
}
