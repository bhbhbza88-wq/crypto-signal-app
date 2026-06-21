// Адрес backend задаётся через переменную окружения VITE_API_URL при сборке на Railway.
// Для локальной разработки используется http://localhost:8000.
function resolveBaseUrl() {
  if (import.meta.env.VITE_API_URL) {
    return `${import.meta.env.VITE_API_URL}/api`
  }
  return 'http://localhost:8000/api'
}

const BASE_URL = resolveBaseUrl()

async function get(path) {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) throw new Error(`Request failed: ${path}`)
  return res.json()
}

export const api = {
  getSignals: () => get('/signals'),
  getHistory: (limit = 100) => get(`/history?limit=${limit}`),
  getEvents: (limit = 50) => get(`/events?limit=${limit}`),
  getStats: () => get('/stats'),
  getMarket: () => get('/market'),
  getDryrunStatus: () => get('/dryrun/status'),
  getDryrunOpen: () => get('/dryrun/open'),
  getDryrunBreakdown: (days = 30) => get(`/dryrun/breakdown?days=${days}`),
}
