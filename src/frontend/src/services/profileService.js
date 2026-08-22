import { apiClient } from './apiClient.js'

export async function loadCompassProfile({ answers } = {}) {
  void answers
  return apiClient.get('/api/profile/compass')
}
