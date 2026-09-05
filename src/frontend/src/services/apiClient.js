// Only GET and HEAD may be sent twice. A repeated POST is a second rating or a
// second session, and "it failed, so I sent it again" is how duplicates happen.
const REPEATABLE = new Set(['GET', 'HEAD'])

// Gateway statuses: the edge could not reach the API or gave up waiting. These
// are not the API refusing anything, so the same request a moment later usually
// works — which is exactly what a person discovers by refreshing the page.
const TRANSIENT = new Set([502, 503, 504])

async function request(path, options = {}, attempt = 0) {
  const method = options.method || 'GET'
  const requestBody = options.body ? JSON.parse(options.body) : undefined
  if (requestBody) console.info(`[Something Good To Watch API] ${method} ${path} request\n${JSON.stringify(requestBody, null, 2)}`)

  let response
  try {
    response = await fetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    })
  } catch (networkError) {
    // fetch only rejects when the request did not complete at all — no status,
    // nothing on the server, nothing in its log. Worth saying plainly rather
    // than reporting it as though the service had answered.
    console.error(`[Something Good To Watch API] ${method} ${path} never reached the server`, networkError)
    if (REPEATABLE.has(method) && attempt === 0) return request(path, options, attempt + 1)
    throw new Error('That did not reach the server. Check your connection and try again.')
  }

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    console.error(`[Something Good To Watch API] ${method} ${path} failed ${response.status}\n${JSON.stringify(body, null, 2)}`)
    if (TRANSIENT.has(response.status) && REPEATABLE.has(method) && attempt === 0) {
      return request(path, options, attempt + 1)
    }
    const detail = Array.isArray(body?.detail) ? body.detail[0]?.msg : body?.detail
    if (detail) throw new Error(detail)
    // No detail means the body was not the API's — a gateway error page, most
    // often. The status is the only thing that distinguishes "the service said
    // no" from "the service was never asked", so it goes in the message: this
    // failure was reported for a week with nothing to tell those apart.
    throw new Error(TRANSIENT.has(response.status)
      ? `The connection to the service dropped (${response.status}). Please try again.`
      : `The service could not complete that request (${response.status}).`)
  }
  console.info(`[Something Good To Watch API] ${method} ${path} response\n${JSON.stringify(body, null, 2)}`)
  return body
}

export const apiClient = {
  get: (path, options) => request(path, options),
  post: (path, body, options = {}) => request(path, { ...options, method: 'POST', body: JSON.stringify(body) }),
  put: (path, body, options = {}) => request(path, { ...options, method: 'PUT', body: JSON.stringify(body) }),
}
