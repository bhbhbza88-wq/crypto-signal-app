// Адрес backend задаётся через переменную окружения VITE_API_URL при сборке на Railway.
// Для локальной разработки используется http://localhost:8000.
function resolveBaseUrl() {
  if (import.meta.env.VITE_API_URL) {
    return `${import.meta.env.VITE_API_URL}/api`
  }
  return 'http://localhost:8000/api'
}

const BASE_URL = resolveBaseUrl()

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
  authConfig: () => get('/auth/config'),
  register: (email, password) => post('/auth/register', { email, password }),
  login: (email, password) => post('/auth/login', { email, password }),
  googleLogin: (idToken) => post('/auth/google', { id_token: idToken }),
  verifyEmail: (token) => post('/auth/verify-email', { token }),
  resendVerification: (email) => post('/auth/resend-verification', { email }),
  forgotPassword: (email) => post('/auth/forgot-password', { email }),
  resetPassword: (token, password) => post('/auth/reset-password', { token, password }),
  logout: () => post('/auth/logout'),
  me: () => get('/auth/me'),
  getSignals: () => get('/signals'),
  getHistory: (limit = 100) => get(`/history?limit=${limit}`),
  getStats: () => get('/stats'),
  aiChat: (messages) => post('/ai/chat', { messages }),
  adminGetTraders: () => get('/admin/traders'),
  adminCreateTrader: (data) => post('/admin/traders', data),
  adminAddSignal: (data) => post('/admin/add-signal', data),
  adminGrantPremium: (email, days = 30, tier = 'premium') =>
    post('/admin/grant-premium', { email, days, tier }),
  adminPremiumRequests: () => get('/admin/premium-requests'),
  adminChannelDaily: (days = 14) => get(`/admin/channel-daily?days=${days}`),
  analyzeChannel: (channelUrl, days = 30, entryTimeoutHours = 6, maxHoldHours = 168, riskPerTradeUsd = 100) =>
    post('/analyze-channel', {
      channel_url: channelUrl, days, entry_timeout_hours: entryTimeoutHours,
      max_hold_hours: maxHoldHours, risk_per_trade_usd: riskPerTradeUsd,
    }),
  getAnalysisStatus: (jobId) => get(`/analysis-status/${jobId}`),
  getChannelHistory: (channel) => get(`/channel-history/${encodeURIComponent(channel)}`),
  getChannelsRanking: () => get('/channels-ranking'),
}
