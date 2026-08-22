import { apiClient } from './apiClient.js'

export async function loadOnboardingFilms(access, shareToken) {
  const payload = await apiClient.get(`/api/onboarding/films?share_token=${encodeURIComponent(shareToken)}`, {
    headers: { 'X-Session-Token': access.token },
  })
  return payload.films
}

export function submitMovieReaction(access, filmId, reaction, shareToken) {
  return apiClient.post('/api/onboarding/ratings', {
    film_id: filmId,
    reaction,
    session_share_token: shareToken,
  }, {
    headers: { 'X-Session-Token': access.token },
  })
}
