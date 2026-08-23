import { apiClient } from './apiClient.js'

export function loadMoralProfile(access) {
  return apiClient.get('/api/profile/moral', {
    headers: { 'X-Session-Token': access.token },
  })
}

// Everyone else in the shared session, read against the same axes. A session of
// one returns an empty list, so the compass can ask unconditionally.
export function loadSessionMoralProfiles(access, shareToken) {
  return apiClient.get(`/api/profile/moral/session/${encodeURIComponent(shareToken)}`, {
    headers: { 'X-Session-Token': access.token },
  })
}
