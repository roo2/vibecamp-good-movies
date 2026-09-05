import { apiClient } from './apiClient.js'

const storageKey = 'moral-atlas-group-session'

function headers(access) {
  return { headers: { 'X-Session-Token': access.token } }
}

export function saveGroupSession(groupSession) {
  localStorage.setItem(storageKey, JSON.stringify({ shareToken: groupSession.share_token }))
}

// Forget the session without forgetting the person. Backing out of a
// half-answered quiz should not sign anybody out or lose the moral position
// they set — neither is what they are abandoning.
export function clearGroupSession() {
  try {
    localStorage.removeItem(storageKey)
  } catch {
    // A browser refusing storage is not a reason to fail leaving a screen.
  }
}

export function loadGroupSession() {
  try {
    return JSON.parse(localStorage.getItem(storageKey))
  } catch {
    return null
  }
}

export async function createGroupSession(access) {
  const groupSession = await apiClient.post('/api/sessions', {}, headers(access))
  saveGroupSession(groupSession)
  return groupSession
}

export async function joinGroupSession(access, shareToken) {
  const groupSession = await apiClient.post(`/api/sessions/${shareToken}/join`, {}, headers(access))
  saveGroupSession(groupSession)
  return groupSession
}

export function loadGroupSessionStatus(access, shareToken) {
  return apiClient.get(`/api/sessions/${shareToken}`, headers(access))
}

export function startGroupSession(access, shareToken) {
  return apiClient.post(`/api/sessions/${shareToken}/start`, {}, headers(access))
}

export function beginResultsWait(access, shareToken) {
  return apiClient.post(`/api/sessions/${shareToken}/wait`, {}, headers(access))
}

export function markSessionMemberUnready(access, shareToken) {
  return apiClient.post(`/api/sessions/${shareToken}/unready`, {}, headers(access))
}

export function continueWithoutMembers(access, shareToken) {
  return apiClient.post(`/api/sessions/${shareToken}/continue`, {}, headers(access))
}
