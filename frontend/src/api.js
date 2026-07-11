// Адрес backend задаётся через переменную окружения VITE_API_URL при сборке на Railway.
// Для локальной разработки используется http://localhost:8000.
function resolveBaseUrl() {
  if (import.meta.env.VITE_API_URL) {
    return `${import.meta.env.VITE_API_URL}/api`
  }
  return 'http://localhost:8000/api'
}

const BASE_URL = resolveBaseUrl()

// ── Токен авторизации (localStorage) ──
const TOKEN_KEY = 'nwicki_token'
export function getToken() { return localStorage.getItem(TOKEN_KEY) }
export function setToken(t) { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) }

function authHeaders() {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function get(path) {
  const res = await fetch(`${BASE_URL}${path}`, { headers: { ...authHeaders() } })
  if (!res.ok) throw new Error(`Request failed: ${path}`)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Request failed: ${path}`)
  return data
}

export const api = {
  // auth / billing
  register: (email, password) => post('/auth/register', { email, password }),
  login: (email, password) => post('/auth/login', { email, password }),
  logout: () => post('/auth/logout'),
  me: () => get('/auth/me'),
  upgrade: (tier) => post('/billing/upgrade', { tier }),
  getSignals: () => get('/signals'),
  getHistory: (limit = 100) => get(`/history?limit=${limit}`),
  getEvents: (limit = 50) => get(`/events?limit=${limit}`),
  getStats: () => get('/stats'),
  getMarket: () => get('/market'),
  getDryrunStatus: () => get('/dryrun/status'),
  getDryrunOpen: () => get('/dryrun/open'),
  getDryrunBreakdown: (days = 30) => get(`/dryrun/breakdown?days=${days}`),
  getXsecStatus: () => get('/xsec/status'),
  getXsecHistory: (limit = 100) => get(`/xsec/history?limit=${limit}`),
  getXsecRanking: () => get('/xsec/ranking'),
  getTrendStatus: () => get('/trend/status'),
  getTrendHistory: (limit = 100) => get(`/trend/history?limit=${limit}`),
  getMarketPhase: () => get('/market/phase'),
  getStrategiesSummary: () => get('/strategies/summary'),
  aiChat: (messages) => post('/ai/chat', { messages }),
  startRobustness: (params) => post('/backtest/robustness', params),
  getRobustnessStatus: (jobId) => get(`/backtest/robustness/${jobId}`),
  getTraders: () => get('/traders'),
  adminGetTraders: () => get('/admin/traders'),
  adminCreateTrader: (data) => post('/admin/traders', data),
  adminAddSignal: (data) => post('/admin/add-signal', data),
  analyzeChannel: (channelUrl, days = 30, entryTimeoutHours = 6) =>
    post('/analyze-channel', { channel_url: channelUrl, days, entry_timeout_hours: entryTimeoutHours }),
  getAnalysisStatus: (jobId) => get(`/analysis-status/${jobId}`),
  getChannelHistory: (channel) => get(`/channel-history/${encodeURIComponent(channel)}`),
  getChannelsRanking: () => get('/channels-ranking'),
}
