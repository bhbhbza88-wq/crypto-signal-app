import { useEffect, useState, useCallback, useRef, useMemo, Component, lazy, Suspense } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, getToken, setToken } from './api'
import AuthModal from './AuthModal'
import SignalCard from './SignalCard'
import { useLivePrices, CountUp, RESULT_LABEL, TG_BOT, APP_SECTIONS, polishHistory, polishStats } from './shared'
import './App.css'

const Pricing = lazy(() => import('./Pricing'))
const HistoryTable = lazy(() => import('./HistoryTable'))
const MarketView = lazy(() => import('./MarketView'))
const AIChat = lazy(() => import('./AIChat'))
const SmartTrade = lazy(() => import('./SmartTrade'))
const Admin = lazy(() => import('./Admin'))
const ChannelAnalyzer = lazy(() => import('./ChannelAnalyzer'))

const POLL_INTERVAL = 15000
const MARKET_POLL_INTERVAL = 60000
const VALID_TABS = new Set(APP_SECTIONS)

// Ошибка в одной вкладке не должна ронять всё приложение в белый экран
class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  componentDidUpdate(prevProps) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) this.setState({ error: null })
  }
  render() {
    if (this.state.error) {
      return (
        <div className="section animate-in" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
          <h2 style={{ marginBottom: 8 }}>Что-то пошло не так</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 20 }}>
            Раздел не смог загрузиться. Попробуй обновить страницу — остальное приложение работает.
          </p>
          <button className="btn-primary" onClick={() => window.location.reload()}>Обновить</button>
        </div>
      )
    }
    return this.props.children
  }
}

const NAV_SECTIONS = [
  { title: 'Главное', items: [
    { key: 'overview',     label: 'Дашборд',       icon: '◈' },
    { key: 'ai_assistant', label: 'AI Ассистент',  icon: '✦', badge: 'BETA' },
    { key: 'market',       label: 'Скринер',        icon: '◫' },
  ]},
  { title: 'Инструменты', items: [
    { key: 'smarttrade_calc', label: 'Smart Trade', icon: '⚡', badge: 'NEW' },
    { key: 'history',      label: 'История',        icon: '📋' },
  ]},
  { title: 'Аккаунт', items: [
    { key: 'pricing',      label: 'Тарифы',         icon: '💎' },
    { key: 'invite',       label: 'Пригласить',     icon: '👥' },
  ]},
]

function ComingSoonPage({ tab }) {
  const labels = { invite: 'Пригласить друга' }
  const descs = { invite: 'Реферальная программа в разработке — приглашай друзей и получай бонусы к тарифу. Скоро.' }
  return (
    <div className="coming-soon-card animate-in">
      <div className="cs-icon">◈</div>
      <div className="cs-title">{labels[tab] || tab}</div>
      <div className="cs-desc">{descs[tab] || 'Этот раздел в разработке. Следи за обновлениями!'}</div>
      <div className="cs-badge">Скоро</div>
    </div>
  )
}

function onSpot(e) {
  const r = e.currentTarget.getBoundingClientRect()
  e.currentTarget.style.setProperty('--mx', `${((e.clientX - r.left) / r.width) * 100}%`)
  e.currentTarget.style.setProperty('--my', `${((e.clientY - r.top) / r.height) * 100}%`)
}

function KPI({ label, value, suffix, sub, accent }) {
  return (
    <div className={`kpi-card spot ${accent ? 'accent' : ''}`} onMouseMove={onSpot}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-val"><CountUp value={value} suffix={suffix} /></div>
      <div className="kpi-sub">{sub}</div>
    </div>
  )
}

function requestPush() { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission() }
function sendPush(t, b) { if ('Notification' in window && Notification.permission === 'granted') new Notification(t, { body: b }) }

function RecentSignals({ history, isPremium, onUpgrade, onSeeAll }) {
  const rows = polishHistory(history).slice(0, 8)
  if (!rows.length) return null
  return (
    <div className="rs-card">
      {isPremium && (
        <div className="rs-head">
          <button className="rs-more" onClick={onSeeAll}>Вся история →</button>
        </div>
      )}
      <div className="rs-list-wrap">
        <div className={`rs-list ${!isPremium ? 'rs-blur' : ''}`}>
          {rows.map((t) => (
            <div className="rs-row" key={t.id}>
              <span className="rs-sym mono">{t.symbol.replace('/USDT', '')}</span>
              <span className={`rs-dir ${t.signal === 'LONG' ? 'long' : 'short'}`}>{t.signal}</span>
              <span className="rs-res">{RESULT_LABEL[t.result] || t.result}</span>
              <span className={`rs-pnl mono ${t.pnl > 0 ? 'pos' : t.pnl < 0 ? 'neg' : ''}`}>
                {t.pnl > 0 ? '+' : ''}{t.pnl}%
              </span>
            </div>
          ))}
        </div>
        {!isPremium && (
          <div className="rs-lock">
            <span className="rs-lock-icon">🔒</span>
            <span className="rs-lock-text">Полная лента сделок и PnL по дням — на Premium</span>
            <button className="rs-lock-btn" onClick={onUpgrade}>Открыть за Premium →</button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const navigate = useNavigate()
  const { section } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = VALID_TABS.has(section) ? section : 'overview'

  const [signals, setSignals] = useState([])
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)
  const [market, setMarket] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [user, setUser] = useState(null)
  const [showAuth, setShowAuth] = useState(false)
  const [authMode, setAuthMode] = useState('login')
  const prevRef = useRef([])
  const prices = useLivePrices()
  const displayHistory = useMemo(() => polishHistory(history), [history])
  const displayStats = useMemo(() => polishStats(stats, displayHistory), [stats, displayHistory])

  const setTab = useCallback((key) => {
    navigate(`/app/${key}`)
    setSidebarOpen(false)
  }, [navigate])

  useEffect(() => {
    if (!VALID_TABS.has(section)) navigate('/app/overview', { replace: true })
  }, [section, navigate])

  // восстановление сессии по сохранённому токену
  useEffect(() => {
    if (getToken()) {
      api.me().then(r => setUser(r.user)).catch(() => setToken(null))
    }
  }, [])

  // CTA с лендинга: /app/... ?auth=register|login
  useEffect(() => {
    const wanted = searchParams.get('auth')
    if (wanted === 'register' || wanted === 'login') {
      if (!getToken()) { setAuthMode(wanted); setShowAuth(true) }
      searchParams.delete('auth')
      setSearchParams(searchParams, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const logout = async () => {
    try { await api.logout() } catch {}
    setToken(null); setUser(null)
  }

  const [dark, setDark] = useState(() => {
    const s = localStorage.getItem('theme')
    if (s) return s === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => {
    const h = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      if (e.key === 'd') setDark(d => !d)
      if (e.key === 'Escape') setSidebarOpen(false)
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  useEffect(() => { requestPush() }, [])

  const fetchCore = useCallback(async () => {
    try {
      const [s, h, st] = await Promise.all([api.getSignals(), api.getHistory(50), api.getStats()])
      if (s.length > 0 && prevRef.current.length === 0) sendPush(`🚨 NOWICKI: ${s[0].signal} ${s[0].symbol}`, `Score ${s[0].score}/20`)
      prevRef.current = s; setSignals(s); setHistory(h); setStats(st); setError(null)
    } catch { setError('Нет связи с сервером.') }
    finally { setLoading(false) }
  }, [])

  const fetchMarket = useCallback(async () => { try { setMarket(await api.getMarket()) } catch {} }, [])

  useEffect(() => { fetchCore(); const id = setInterval(fetchCore, POLL_INTERVAL); return () => clearInterval(id) }, [fetchCore])
  useEffect(() => {
    if (tab !== 'market') return
    fetchMarket(); const id = setInterval(fetchMarket, MARKET_POLL_INTERVAL); return () => clearInterval(id)
  }, [tab, fetchMarket])

  const isPremium = !!user && (user.tier === 'premium' || user.tier === 'vip')

  const navSections = user?.is_admin
    ? [...NAV_SECTIONS, { title: 'Админ', items: [
        { key: 'admin', label: 'Админка', icon: '🛠' },
        { key: 'channel_analyzer', label: 'Channel Analyzer', icon: '🔬' },
      ] }]
    : NAV_SECTIONS

  return (
    <div className={`layout ${sidebarOpen ? 'sidebar-open' : ''} ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>

      {/* ── SIDEBAR ── */}
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="sidebar-logo" onClick={() => navigate('/')}>
            {!sidebarCollapsed && (
              <><div className="logo-icon"><span className="logo-n">N</span></div>
              <div className="logo-text-wrap">
                <span className="logo-name gradient-text">NOWICKI</span>
                <span className="logo-sub">Signal Relay</span>
              </div></>
            )}
            {sidebarCollapsed && <div className="logo-icon"><span className="logo-n">N</span></div>}
          </div>
          <button className="sidebar-collapse-btn" onClick={() => setSidebarCollapsed(c => !c)}>
            {sidebarCollapsed ? '›' : '‹'}
          </button>
        </div>

        {prices && !sidebarCollapsed && (
          <div className="sidebar-prices">
            <div className="sp-item">
              <span className="sp-sym">BTC/USD</span>
              <span className="sp-val">${prices.btc.price}</span>
              <span className={`sp-chg ${prices.btc.positive ? 'pos' : 'neg'}`}>{prices.btc.positive ? '▲' : '▼'}{Math.abs(prices.btc.change)}%</span>
            </div>
            <div className="sp-div" />
            <div className="sp-item">
              <span className="sp-sym">ETH/USD</span>
              <span className="sp-val">${prices.eth.price}</span>
              <span className={`sp-chg ${prices.eth.positive ? 'pos' : 'neg'}`}>{prices.eth.positive ? '▲' : '▼'}{Math.abs(prices.eth.change)}%</span>
            </div>
          </div>
        )}

        <nav className="sidebar-nav">
          {navSections.map((sec) => (
            <div key={sec.title} className="nav-group">
              {!sidebarCollapsed && <div className="nav-group-title">{sec.title}</div>}
              {sec.items.map((t) => (
                <button
                  key={t.key}
                  className={`nav-item ${tab === t.key ? 'active' : ''}`}
                  onClick={() => setTab(t.key)}
                  title={sidebarCollapsed ? t.label : ''}
                >
                  <span className="nav-icon">{t.icon}</span>
                  {!sidebarCollapsed && <span className="nav-label">{t.label}</span>}
                  {!sidebarCollapsed && (
                    <div className="nav-right">
                      {t.badge && <span className={`nav-badge ${
                        t.badge==='HOT' ? 'hot' :
                        t.badge==='AI' ? 'ai' :
                        t.badge==='LIVE' ? 'live' :
                        t.badge==='NEW' ? 'new' : 'beta'
                      }`}>{t.badge}</span>}
                      {tab === t.key && <span className="nav-pip" />}
                    </div>
                  )}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          {!sidebarCollapsed && (
            <div className="scan-status">
              <span className="scan-dot" />
              <div>
                <span className="scan-text">Сканер онлайн</span>
                <span className="scan-sub">поиск точек входа 24/7</span>
              </div>
            </div>
          )}
          <div className="sidebar-actions">
            <button className="theme-toggle" onClick={() => setDark(d => !d)}>{dark ? '☀' : '☾'}</button>
          </div>
        </div>
      </aside>

      {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}

      {/* ── MAIN ── */}
      <div className="main-wrap">
        <header className="topbar">
          <div className="topbar-left">
            <button className="burger" onClick={() => setSidebarOpen(o => !o)}><span /><span /><span /></button>
            {prices && (
              <div className="topbar-prices">
                <div className="tp-item">
                  <span className="tp-sym">BTC/USD</span>
                  <span className="tp-val">${prices.btc.price}</span>
                  <span className={`tp-chg ${prices.btc.positive ? 'pos' : 'neg'}`}>{prices.btc.positive ? '▲' : '▼'}{Math.abs(prices.btc.change)}%</span>
                </div>
                <div className="tp-div" />
                <div className="tp-item">
                  <span className="tp-sym">ETH/USD</span>
                  <span className="tp-val">${prices.eth.price}</span>
                  <span className={`tp-chg ${prices.eth.positive ? 'pos' : 'neg'}`}>{prices.eth.positive ? '▲' : '▼'}{Math.abs(prices.eth.change)}%</span>
                </div>
              </div>
            )}
          </div>
          <div className="topbar-right">
            <a className="btn-tg-bot" href={TG_BOT} target="_blank" rel="noopener noreferrer" aria-label="Telegram бот">
              TG <span className="btn-tg-label">Бот</span>
            </a>
            <button className="btn-trial" onClick={() => setTab('ai_assistant')}>AI Ассистент</button>
            {user ? (
              <div className="auth-box">
                <button className={`plan-badge tier-${user.tier}`} onClick={() => setTab('pricing')} title="Сменить тариф">
                  {user.tier.toUpperCase()}
                </button>
                <span className="auth-email" title={user.email}>{user.email.split('@')[0]}</span>
                <button className="auth-logout" onClick={logout} title="Выйти">⎋</button>
              </div>
            ) : (
              <button className="auth-login-btn" onClick={() => { setAuthMode('login'); setShowAuth(true) }}>Войти</button>
            )}
            <button className="theme-toggle-sm" onClick={() => setDark(d => !d)}>{dark ? '☀' : '☾'}</button>
          </div>
        </header>

        <main className="content">
          {error && <div className="error-banner animate-in">{error}</div>}

          {user?.on_trial && (
            <div className="trial-banner animate-in">
              <span>✦ <strong>Premium-триал активен</strong> — осталось {user.trial_days_left} {user.trial_days_left === 1 ? 'день' : 'дн.'}. Все стратегии открыты.</span>
              <button onClick={() => setTab('pricing')}>Оформить Premium</button>
            </div>
          )}

          <ErrorBoundary resetKey={tab}>
          <Suspense fallback={<div className="section animate-in" style={{ padding: 40, color: 'var(--text-tertiary)' }}>Загрузка раздела…</div>}>
          {tab === 'ai_assistant' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">AI Ассистент <span className="beta-tag">BETA</span></h1></div><AIChat /></section>}
          {tab === 'market' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">Скринер рынка</h1></div><MarketView market={market} /></section>}
          {tab === 'history' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">История сделок</h1></div><HistoryTable history={history} isPremium={isPremium} onUpgrade={() => user ? setTab('pricing') : (setAuthMode('register'), setShowAuth(true))} /></section>}
          {tab === 'pricing' && <section className="section animate-in"><Pricing user={user} onUpgraded={(t) => { setUser(u => u ? { ...u, tier: t } : u); setTab('history') }} onNeedAuth={() => { setAuthMode('register'); setShowAuth(true) }} /></section>}
          {tab === 'smarttrade_calc' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">Smart Trade <span className="hot-tag">NEW</span></h1></div><SmartTrade /></section>}
          {tab === 'invite' && <ComingSoonPage tab="invite" />}
          {tab === 'admin' && user?.is_admin && <Admin />}
          {tab === 'channel_analyzer' && user?.is_admin && <section className="section animate-in"><ChannelAnalyzer /></section>}
          </Suspense>
          {tab === 'overview' && (
            <div className="animate-in dash">
              <div className="dash-hero">
                <div className="dash-hero-text">
                  <span className="live-chip">Scanner live</span>
                  <h1 className="page-title">Дашборд</h1>
                  <p className="page-subtitle">AI ищет точки входа. Открытые сетапы и свежий трек-рекорд — ниже.</p>
                </div>
                {prices && (
                  <div className="dash-ticker app-panel">
                    <div className="dt-row">
                      <span>BTC</span>
                      <b>${prices.btc.price}</b>
                      <i className={prices.btc.positive ? 'pos' : 'neg'}>{prices.btc.positive ? '+' : ''}{prices.btc.change}%</i>
                    </div>
                    <div className="dt-row">
                      <span>ETH</span>
                      <b>${prices.eth.price}</b>
                      <i className={prices.eth.positive ? 'pos' : 'neg'}>{prices.eth.positive ? '+' : ''}{prices.eth.change}%</i>
                    </div>
                  </div>
                )}
              </div>

              <div className="kpi-grid">
                <KPI label="Активные" value={signals.length} sub={signals.length ? 'в работе' : 'ожидание'} accent />
                <KPI label="Закрыто" value={displayStats.total} sub="всего сделок" />
                <KPI label="Винрейт" value={displayStats.winrate} suffix="%" sub="за всё время" />
                <KPI label="Ср. PnL" value={displayStats.avgPnl} suffix="%" sub="на сделку" />
              </div>

              <section className="section dash-section">
                <div className="app-panel-head" style={{ paddingLeft: 0, paddingRight: 0, border: 'none' }}>
                  <h2 className="section-title" style={{ margin: 0, flex: 1 }}>Активные сигналы</h2>
                  <span className="sec-count">{signals.length}</span>
                </div>
                {loading ? <SignalSkeleton /> : signals.length === 0 ? <EmptySignal /> : (
                  <div className="signals-grid">
                    {signals.map(s => <SignalCard key={s.symbol} signal={s} />)}
                  </div>
                )}
              </section>

              {history.length > 0 && (
                <section className="section dash-section">
                  <div className="app-panel-head" style={{ paddingLeft: 0, paddingRight: 0, border: 'none' }}>
                    <h2 className="section-title" style={{ margin: 0, flex: 1 }}>Последние сигналы</h2>
                  </div>
                  <RecentSignals
                    history={history}
                    isPremium={isPremium}
                    onSeeAll={() => setTab('history')}
                    onUpgrade={() => user ? setTab('pricing') : (setAuthMode('register'), setShowAuth(true))}
                  />
                </section>
              )}
            </div>
          )}
          </ErrorBoundary>
        </main>
      </div>

      {showAuth && <AuthModal initialMode={authMode} onClose={() => setShowAuth(false)} onAuth={setUser} />}


    </div>
  )
}

function SignalSkeleton() {
  return (
    <div className="signal-skeleton animate-in">
      <div className="sk-bar skeleton" />
      <div className="sk-content">
        <div className="sk-row"><div className="sk-circle skeleton" /><div style={{flex:1,display:'flex',flexDirection:'column',gap:8}}><div className="sk-line skeleton" style={{width:'40%'}} /><div className="sk-line skeleton" style={{width:'25%',height:10}} /></div></div>
        <div className="sk-line skeleton" style={{height:8}} />
        <div className="sk-chart skeleton" />
      </div>
    </div>
  )
}

function EmptySignal() {
  return (
    <div className="empty-signal animate-in">
      <div className="empty-icon">🔍</div>
      <div className="empty-title">Сигналов нет</div>
      <div className="empty-desc">AI-сканер ищет точки входа на рынке. Как только появится новый сигнал — он отобразится здесь.</div>
      <div className="empty-pulse"><span style={{width:7,height:7,borderRadius:'50%',background:'var(--long)',animation:'pulse 2s infinite',display:'inline-block'}} />Сканируем рынок каждые несколько минут</div>
    </div>
  )
}
