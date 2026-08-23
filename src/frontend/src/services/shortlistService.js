import { apiClient } from './apiClient.js'

export async function loadShortlist(access, shareToken) {
  const query = shareToken ? `?share_token=${encodeURIComponent(shareToken)}` : ''
  return (await apiClient.get(`/api/shortlist/films${query}`, {
    headers: { 'X-Session-Token': access.token },
  })).films
}

export function loadNextShortlistFilm(access, shareToken) {
  return apiClient.get(`/api/shortlist/next?share_token=${encodeURIComponent(shareToken)}`, { headers: { 'X-Session-Token': access.token } })
}

export function loadShortlistSelection(access, shareToken) {
  return apiClient.get(`/api/shortlist/selection?share_token=${encodeURIComponent(shareToken)}`, { headers: { 'X-Session-Token': access.token } })
}

export function saveShortlistReaction(access, shareToken, filmId, reaction) {
  return apiClient.post('/api/shortlist/reactions', { share_token: shareToken, film_id: filmId, reaction }, { headers: { 'X-Session-Token': access.token } })
}

export function reopenShortlist(access, shareToken) {
  return apiClient.post('/api/shortlist/reopen', { share_token: shareToken }, { headers: { 'X-Session-Token': access.token } })
}
