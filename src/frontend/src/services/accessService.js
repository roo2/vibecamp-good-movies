import { apiClient } from './apiClient.js'

const storageKey = 'moral-atlas-access'

export async function startAccess(name) {
  const access = await apiClient.post('/api/access', { name })
  localStorage.setItem(storageKey, JSON.stringify(access))
  return access
}

export function loadAccess() {
  try {
    return JSON.parse(localStorage.getItem(storageKey))
  } catch {
    return null
  }
}

export function clearAccess() {
  localStorage.removeItem(storageKey)
}
