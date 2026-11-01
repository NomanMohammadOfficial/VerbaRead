const BASE = '/api'

async function request(path, options = {}) {
  const init = { ...options }
  if (init.body !== undefined && typeof init.body !== 'string') {
    init.body = JSON.stringify(init.body)
    init.headers = { 'Content-Type': 'application/json', ...(init.headers || {}) }
  }
  const response = await fetch(`${BASE}${path}`, init)
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const data = await response.json()
      const detail = data?.detail
      if (typeof detail === 'string') {
        message = detail
      } else if (Array.isArray(detail)) {
        message = detail.map((item) => item?.msg || item?.detail || 'Invalid input').join('; ')
      }
    } catch {
      message = message || 'Request failed'
    }
    throw new Error(message)
  }
  if (response.status === 204) return null
  return response.json()
}

function query(params) {
  const search = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '' || value === false) return
    search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const api = {
  health: () => request('/health'),
  lessons: () => request('/lessons'),
  createLesson: (body) => request('/lessons', { method: 'POST', body }),
  getLesson: (id) => request(`/lessons/${id}`),
  patchLesson: (id, body) => request(`/lessons/${id}`, { method: 'PATCH', body }),
  deleteLesson: (id) => request(`/lessons/${id}`, { method: 'DELETE' }),
  reader: (id) => request(`/lessons/${id}/reader`),
  lookup: (body) => request('/lookup', { method: 'POST', body }),
  dictionary: (word, cache = true) => request(`/dictionary${query({ word, cache })}`),
  explain: (body) => request('/explain', { method: 'POST', body }),
  phrase: (body) => request('/phrase', { method: 'POST', body }),
  words: (params = {}) => request(`/words${query(params)}`),
  getWord: (id) => request(`/words/${id}`),
  patchWord: (id, body) => request(`/words/${id}`, { method: 'PATCH', body }),
  deleteWord: (id) => request(`/words/${id}`, { method: 'DELETE' }),
  practiceDue: (limit = 20) => request(`/practice/due${query({ limit })}`),
  grade: (id, grade) => request(`/practice/${id}`, { method: 'POST', body: { grade } }),
  stats: () => request('/stats'),
  youtube: (url) => request(`/youtube${query({ url })}`),
  translate: (text, target = 'en') => request(`/translate${query({ text, target })}`),
  ankiUrl: `${BASE}/export/anki`,
}
