import { apiClient } from './apiClient.js'

const storageKey = 'moral-atlas-access'

export async function startAccess(name) {
  const access = await apiClient.post('/api/access', { name })
  sessionStorage.setItem(storageKey, JSON.stringify(access))
  return access
}

export function loadAccess() {
  try {
    return JSON.parse(sessionStorage.getItem(storageKey))
  } catch {
    return null
  }
}

export function clearAccess() {
  sessionStorage.removeItem(storageKey)
}
