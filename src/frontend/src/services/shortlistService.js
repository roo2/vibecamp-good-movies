import { apiClient } from './apiClient.js'

export async function loadShortlist(access) {
  return (await apiClient.get('/api/shortlist/films', { headers: { 'X-Session-Token': access.token } })).films
}

export function saveShortlistReaction(access, filmId, reaction) {
  return apiClient.post('/api/shortlist/reactions', { film_id: filmId, reaction }, { headers: { 'X-Session-Token': access.token } })
}
