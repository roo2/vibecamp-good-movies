import { apiClient } from './apiClient.js'

export async function loadOnboardingFilm() {
  const payload = await apiClient.get('/api/onboarding/films')
  return payload.films[0]
}

export function submitMovieReaction(access, filmId, reaction) {
  return apiClient.post('/api/onboarding/ratings', {
    film_id: filmId,
    reaction,
  }, {
    headers: { 'X-Session-Token': access.token },
  })
}
