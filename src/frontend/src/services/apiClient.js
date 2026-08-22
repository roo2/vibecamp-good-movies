async function request(path, options = {}) {
  const method = options.method || 'GET'
  const requestBody = options.body ? JSON.parse(options.body) : undefined
  if (requestBody) console.info(`[Moral Atlas API] ${method} ${path} request\n${JSON.stringify(requestBody, null, 2)}`)

  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    console.error(`[Moral Atlas API] ${method} ${path} failed\n${JSON.stringify(body, null, 2)}`)
    const detail = Array.isArray(body?.detail) ? body.detail[0]?.msg : body?.detail
    throw new Error(detail || 'The service could not complete that request.')
  }
  console.info(`[Moral Atlas API] ${method} ${path} response\n${JSON.stringify(body, null, 2)}`)
  return body
}

export const apiClient = {
  get: (path, options) => request(path, options),
  post: (path, body, options = {}) => request(path, { ...options, method: 'POST', body: JSON.stringify(body) }),
}
