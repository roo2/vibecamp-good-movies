import { apiClient } from './apiClient.js'

export async function loadOnboardingFilms() {
  const payload = await apiClient.get('/api/onboarding/films')
  return payload.films
}

export function submitMovieReaction(access, filmId, reaction) {
  return apiClient.post('/api/onboarding/ratings', {
    film_id: filmId,
    reaction,
  }, {
    headers: { 'X-Session-Token': access.token },
  })
}
