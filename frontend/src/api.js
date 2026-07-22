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

// Протухший/невалидный токен: чистим и сообщаем приложению, чтобы разлогинить.
function handleUnauthorized() {
  if (!getToken()) return
  setToken(null)
  window.dispatchEvent(new CustomEvent('auth:unauthorized'))
}

async function get(path) {
  const res = await fetch(`${BASE_URL}${path}`, { headers: { ...authHeaders() } })
  if (res.status === 401) handleUnauthorized()
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `Request failed: ${path}`)
  }
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) handleUnauthorized()
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
  getHistory: (limit = 500, days = 30) => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    if (days != null) params.set('days', String(days))
    return get(`/history?${params}`)
  },
  getStats: () => get('/stats'),
  aiChat: (messages) => post('/ai/chat', { messages }),
  aiChatStream: async (messages, { onToken, onDone, onError } = {}) => {
    const res = await fetch(`${BASE_URL}/ai/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ messages }),
    })
    if (res.status === 401) handleUnauthorized()
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      const msg = data.detail || `Request failed: /ai/chat/stream`
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
    const reader = res.body?.getReader()
    if (!reader) throw new Error('Stream unavailable')
    const decoder = new TextDecoder()
    let buf = ''
    let used = null
    let limit = null
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const parts = buf.split('\n')
      buf = parts.pop() || ''
      for (const line of parts) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue
        const raw = trimmed.slice(5).trim()
        if (!raw || raw === '[DONE]') continue
        let ev
        try { ev = JSON.parse(raw) } catch { continue }
        if (ev.error) {
          onError?.(ev.error)
          throw new Error(ev.error)
        }
        if (ev.t) onToken?.(ev.t)
        if (ev.done) {
          used = ev.used
          limit = ev.limit
          onDone?.({ used, limit })
        }
      }
    }
    return { used, limit }
  },
  chartAnalyze: (body) => post('/ai/chart-analyze', body),
  getChartReviews: (limit = 40) => get(`/chart-reviews?limit=${limit}`),
  voteChartHelp: (helped) => post('/chart-reviews/vote', { helped: !!helped }),
  adminGetTraders: () => get('/admin/traders'),
  adminCreateTrader: (data) => post('/admin/traders', data),
  adminAddSignal: (data) => post('/admin/add-signal', data),
  adminGrantPremium: (email, days = 30, tier = 'premium') =>
    post('/admin/grant-premium', { email, days, tier }),
  adminListUsers: ({ q = '', limit = 50, offset = 0, tier = '' } = {}) => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    if (q) params.set('q', q)
    if (tier) params.set('tier', tier)
    return get(`/admin/users?${params}`)
  },
  adminIngestHealth: () => get('/ingest/health'),
  // Без symbol/signal/entry/pnl backend сам берёт случайную монету и % —
  // каждая практика выглядит по-разному, а не всегда BTC +3.2%.
  adminChatEngageTest: (data = {}) =>
    post('/admin/chat-engage-test', { target: 'Kupyansk_2', ...data }),
  adminPremiumRequests: () => get('/admin/premium-requests'),
  telegramLinkToken: () => post('/telegram/link-token', {}),
  paymentsConfig: () => get('/payments/config'),
  createHeleketPayment: (period = 'month') => post('/payments/heleket/create', { period }),
  adminBackfillChannelHistory: (opts = {}) => {
    const params = new URLSearchParams()
    if (opts.limit) params.set('limit', opts.limit)
    if (opts.reset) params.set('reset', 'true')
    const qs = params.toString()
    return post(`/admin/backfill-channel-history${qs ? `?${qs}` : ''}`, {})
  },
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
