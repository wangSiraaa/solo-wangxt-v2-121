const BASE = import.meta.env.VITE_API_BASE || '/api'

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`${response.status}: ${text}`)
  }
  return response
}

export const api = {
  listTrials: () => request('/trials').then((r) => r.json()),
  getTrial: (id) => request(`/trials/${id}`).then((r) => r.json()),
  listPlans: (id) => request(`/trials/${id}/plans`).then((r) => r.json()),
  evaluate: (id, payload) => request(`/trials/${id}/evaluate`, {
    method: 'POST',
    body: JSON.stringify(payload)
  }).then((r) => r.json()),
  exportUrl: (id, format) => `${BASE}/plans/${id}/export?format=${format}`
}
