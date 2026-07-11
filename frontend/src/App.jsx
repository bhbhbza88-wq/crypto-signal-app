import { useEffect, useState, useCallback, useRef, Component } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getToken, setToken } from './api'
import AuthModal from './AuthModal'
import Pricing from './Pricing'
import StatsHero from './StatsHero'
import SignalCard from './SignalCard'
import HistoryTable from './HistoryTable'
import MarketView from './MarketView'
import AIChat from './AIChat'
import Backtest from './Backtest'
import SmartTrade from './SmartTrade'
import DryRunDashboard from './DryRunDashboard'
import XSecDashboard from './XSecDashboard'
import TrendDashboard from './TrendDashboard'
import StrategiesCompare from './StrategiesCompare'
import Admin from './Admin'

const POLL_INTERVAL = 15000
const MARKET_POLL_INTERVAL = 60000

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
  { title: 'Стратегии', items: [
    { key: 'compare',      label: 'Сравнение',      icon: '⚓', badge: 'LIVE' },
    { key: 'dryrun',       label: 'Дальран',        icon: '🛰', badge: 'LIVE' },
    { key: 'xsec',         label: 'Long-Short',     icon: '⚖', badge: 'NEW' },
    { key: 'trend_ff',     label: 'Trend-Following', icon: '📈', badge: 'NEW' },
  ]},
  { title: 'Инструменты', items: [
    { key: 'backtest',     label: 'Бэктест',        icon: '📊' },
    { key: 'smarttrade_calc', label: 'Smart Trade', icon: '⚡', badge: 'NEW' },
    { key: 'history',      label: 'История',        icon: '📋' },
  ]},
  { title: 'Аккаунт', items: [
    { key: 'pricing',      label: 'Тарифы',         icon: '💎' },
    { key: 'invite',       label: 'Пригласить',     icon: '👥' },
  ]},
]

// маршрут открытия дашборда конкретной стратегии с главной
const STRATEGY_TAB = { momentum: 'dryrun', xsec: 'xsec', trend: 'trend_ff' }

// вкладки, закрытые за Premium
const GATED = new Set(['compare', 'dryrun', 'xsec', 'trend_ff'])
const GATED_TITLES = { compare: 'Сравнение стратегий', dryrun: 'Дальран', xsec: 'Long-Short', trend_ff: 'Trend-Following' }

function useLivePrices() {
  const [prices, setPrices] = useState(null)
  useEffect(() => {
    async function fp() {
      try {
        const [b, e] = await Promise.all([
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT'),
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=ETHUSDT'),
        ])
        const btc = (await b.json())?.result?.list?.[0]
        const eth = (await e.json())?.result?.list?.[0]
        if (btc && eth) setPrices({
          btc: { price: parseFloat(btc.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }), change: (parseFloat(btc.price24hPcnt)*100).toFixed(2), positive: parseFloat(btc.price24hPcnt) >= 0 },
          eth: { price: parseFloat(eth.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }), change: (parseFloat(eth.price24hPcnt)*100).toFixed(2), positive: parseFloat(eth.price24hPcnt) >= 0 },
        })
      } catch {}
    }
    fp(); const id = setInterval(fp, 30000); return () => clearInterval(id)
  }, [])
  return prices
}

function MiniChart({ positive }) {
  const pts = positive ? "0,50 30,40 60,28 90,18 120,10 150,5 180,3" : "0,3 30,8 60,18 90,28 120,38 150,45 180,50"
  const color = positive ? '#00e5a8' : '#ff4f60'
  return (
    <svg width="100%" height="50" viewBox="0 0 180 55" preserveAspectRatio="none">
      <defs><linearGradient id={`g${positive}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity="0.25"/><stop offset="100%" stopColor={color} stopOpacity="0"/></linearGradient></defs>
      <polygon points={`0,50 ${pts} 180,55 0,55`} fill={`url(#g${positive})`}/>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/>
    </svg>
  )
}

// курсор-spotlight на карточке
function onSpot(e) {
  const r = e.currentTarget.getBoundingClientRect()
  e.currentTarget.style.setProperty('--mx', `${((e.clientX - r.left) / r.width) * 100}%`)
  e.currentTarget.style.setProperty('--my', `${((e.clientY - r.top) / r.height) * 100}%`)
}

// число с count-up анимацией
function CountUp({ value, suffix = '' }) {
  const isNum = typeof value === 'number' && isFinite(value)
  const [disp, setDisp] = useState(isNum ? 0 : value)
  const prev = useRef(0)
  useEffect(() => {
    if (!isNum) { setDisp(value); return }
    const from = prev.current, to = value, t0 = performance.now(), dur = 900
    let raf
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / dur)
      const eased = 1 - Math.pow(1 - p, 3)
      setDisp(Math.round((from + (to - from) * eased) * 10) / 10)
      if (p < 1) raf = requestAnimationFrame(tick)
      else prev.current = to
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, isNum])
  const out = isNum ? (Number.isInteger(disp) ? disp : disp.toFixed(1)) : disp
  return <>{out}{suffix}</>
}

function requestPush() { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission() }
function sendPush(t, b) { if ('Notification' in window && Notification.permission === 'granted') new Notification(t, { body: b }) }

// ── PAGES ──────────────────────────────────────────────────────

function ComingSoonPage({ tab }) {
  const icons = { invite: '👥' }
  const labels = { invite: 'Пригласить друга' }
  const descs = { invite: 'Реферальная программа в разработке — приглашай друзей и получай бонусы к тарифу. Скоро.' }
  return (
    <div className="coming-soon-card animate-in">
      <div className="cs-icon">{icons[tab] || '◈'}</div>
      <div className="cs-title">{labels[tab] || tab}</div>
      <div className="cs-desc">{descs[tab] || 'Этот раздел в разработке. Следи за обновлениями!'}</div>
      <div className="cs-badge">Скоро</div>
    </div>
  )
}

function UpgradeLock({ tab, user, onUpgrade, onLogin }) {
  return (
    <div className="lock-card animate-in">
      <div className="lock-icon">🔒</div>
      <span className="lock-badge">Premium</span>
      <div className="lock-title">{GATED_TITLES[tab] || 'Premium-раздел'}</div>
      <div className="lock-desc">
        {user
          ? 'Этот раздел доступен на тарифе Premium. Открой все live-стратегии и дашборды в реальном времени.'
          : 'Live-стратегии доступны на Premium. Зарегистрируйся — первые 3 дня Premium бесплатно, карта не нужна.'}
      </div>
      {user
        ? <button className="lock-btn" onClick={onUpgrade}>Перейти на Premium →</button>
        : <button className="lock-btn" onClick={onLogin}>Начать 3 дня бесплатно →</button>}
      <div className="lock-feats">
        {['Сравнение всех стратегий', 'Дальран в реальном времени', 'Long-Short и Trend-Following', 'AI-ассистент 50 вопросов/день'].map((f, i) => (
          <span key={i} className="lock-feat">✓ {f}</span>
        ))}
      </div>
    </div>
  )
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

export default function App() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('overview')
  const [signals, setSignals] = useState([])
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)
  const [market, setMarket] = useState(null)
  const [strategies, setStrategies] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [user, setUser] = useState(null)
  const [showAuth, setShowAuth] = useState(false)
  const [authMode, setAuthMode] = useState('login')
  const prevRef = useRef([])
  const prices = useLivePrices()

  // восстановление сессии по сохранённому токену
  useEffect(() => {
    if (getToken()) {
      api.me().then(r => setUser(r.user)).catch(() => setToken(null))
    }
  }, [])

  // CTA с лендинга: /app?auth=register|login — открываем модалку, если не залогинен
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get('auth')
    if (wanted === 'register' || wanted === 'login') {
      if (!getToken()) { setAuthMode(wanted); setShowAuth(true) }
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

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
      if (s.length > 0 && prevRef.current.length === 0) sendPush(`🚨 NWICKI: ${s[0].signal} ${s[0].symbol}`, `Score ${s[0].score}/20`)
      prevRef.current = s; setSignals(s); setHistory(h); setStats(st); setError(null)
    } catch { setError('Нет связи с сервером.') }
    finally { setLoading(false) }
  }, [])

  const fetchStrategies = useCallback(async () => {
    try { const r = await api.getStrategiesSummary(); setStrategies(r.strategies || []) } catch {}
  }, [])

  const fetchMarket = useCallback(async () => { try { setMarket(await api.getMarket()) } catch {} }, [])

  useEffect(() => { fetchCore(); const id = setInterval(fetchCore, POLL_INTERVAL); return () => clearInterval(id) }, [fetchCore])
  useEffect(() => { fetchStrategies(); const id = setInterval(fetchStrategies, MARKET_POLL_INTERVAL); return () => clearInterval(id) }, [fetchStrategies])
  useEffect(() => {
    if (tab !== 'market') return
    fetchMarket(); const id = setInterval(fetchMarket, MARKET_POLL_INTERVAL); return () => clearInterval(id)
  }, [tab, fetchMarket])

  const isPremium = !!user && (user.tier === 'premium' || user.tier === 'vip')
  const gate = (node) => isPremium
    ? node
    : <UpgradeLock tab={tab} user={user} onUpgrade={() => setTab('pricing')} onLogin={() => { setAuthMode('register'); setShowAuth(true) }} />

  const navSections = user?.is_admin
    ? [...NAV_SECTIONS, { title: 'Админ', items: [{ key: 'admin', label: 'Админка', icon: '🛠' }] }]
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
                <span className="logo-name gradient-text">NWICKI</span>
                <span className="logo-sub">Crypto Scanner</span>
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
                  onClick={() => { setTab(t.key); setSidebarOpen(false) }}
                  title={sidebarCollapsed ? t.label : ''}
                >
                  <span className="nav-icon">{t.icon}</span>
                  {!sidebarCollapsed && <span className="nav-label">{t.label}</span>}
                  {!sidebarCollapsed && (
                    <div className="nav-right">
                      {GATED.has(t.key) && !isPremium && <span className="nav-lock" title="Premium">🔒</span>}
                      {t.badge && <span className={`nav-badge ${t.badge==='HOT'?'hot':t.badge==='AI'?'ai':'beta'}`}>{t.badge}</span>}
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
                <span className="scan-text">Сканирую рынок</span>
                <span className="scan-sub">каждые 2 мин</span>
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
            <button className="btn-trial" onClick={() => setTab('ai_assistant')}>✦ AI Ассистент</button>
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
          {tab === 'ai_assistant' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">AI Ассистент <span className="beta-tag">BETA</span></h1></div><AIChat signals={signals} stats={stats} market={market} /></section>}
          {tab === 'market' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">Скринер рынка</h1></div><MarketView market={market} /></section>}
          {tab === 'history' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">История сделок</h1></div><HistoryTable history={history} isPremium={isPremium} onUpgrade={() => user ? setTab('pricing') : (setAuthMode('register'), setShowAuth(true))} /></section>}
          {tab === 'backtest' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">Бэктест <span className="beta-tag">BETA</span></h1></div><Backtest isPremium={isPremium} onUpgrade={() => user ? setTab('pricing') : (setAuthMode('register'), setShowAuth(true))} /></section>}
          {tab === 'pricing' && <section className="section animate-in"><Pricing user={user} onUpgraded={(t) => setUser(u => u ? { ...u, tier: t } : u)} onNeedAuth={() => setShowAuth(true)} /></section>}
          {tab === 'compare' && gate(<section className="section animate-in"><StrategiesCompare /></section>)}
          {tab === 'dryrun' && gate(<section className="section animate-in"><DryRunDashboard /></section>)}
          {tab === 'xsec' && gate(<section className="section animate-in"><XSecDashboard /></section>)}
          {tab === 'trend_ff' && gate(<section className="section animate-in"><TrendDashboard /></section>)}
          {tab === 'smarttrade_calc' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">Smart Trade <span className="hot-tag">NEW</span></h1></div><SmartTrade /></section>}
          {tab === 'invite' && <ComingSoonPage tab="invite" />}
          {tab === 'admin' && user?.is_admin && <Admin />}

          {tab === 'overview' && (
            <div className="animate-in">
              <div className="page-header">
                <h1 className="page-title">Дашборд</h1>
                <p className="page-subtitle">Живой обзор: сигналы сканера и бумажные стратегии в реальном времени.</p>
              </div>

              {/* KPI — реальные цифры */}
              <div className="kpi-grid">
                <KPI label="Активный сигнал" value={signals.length} sub={signals.length ? 'прямо сейчас' : 'сканер ищет'} accent />
                <KPI label="Стратегии в работе" value={strategies ? strategies.length : 0} sub="бумажные, live" />
                <KPI label="Сделок в истории" value={stats?.all_time?.total ?? history.length} sub="всего закрыто" />
                <KPI label="Винрейт" value={stats?.all_time?.winrate ?? 0} suffix="%" sub="за всё время" />
              </div>

              {/* Активный сигнал — ведём продуктом */}
              <section className="section" style={{ marginTop: 28 }}>
                <h2 className="section-title">Активный сигнал</h2>
                {loading ? <SignalSkeleton /> : signals.length === 0 ? <EmptySignal /> : (
                  <div className="signals-grid">{signals.map(s => <SignalCard key={s.symbol} signal={s} />)}</div>
                )}
              </section>

              {/* Живые стратегии — реальные данные */}
              <div className="ts-block">
                <div className="ts-header">
                  <div>
                    <h2 className="ts-title">Живые стратегии</h2>
                    <p className="ts-sub">Реальные данные, бумажное исполнение — обновляется в реальном времени</p>
                  </div>
                  <button className="ts-more" onClick={() => setTab('compare')}>Сравнить все →</button>
                </div>
                <div className="ts-grid">
                  {(strategies || []).map((s, i) => {
                    const pos = (s.realized_pnl_pct ?? 0) >= 0
                    return (
                      <div key={i} className="ts-card spot" onMouseMove={onSpot} onClick={() => setTab(STRATEGY_TAB[s.key] || 'compare')}>
                        <div className="ts-card-top">
                          <div className="ts-name">{s.name}</div>
                          <span className="ts-kind">{s.kind}</span>
                        </div>
                        <div className="ts-chart"><MiniChart positive={pos} /></div>
                        <div className="ts-roi-row">
                          <span className="ts-roi-label">PnL · paper</span>
                          <span className={`ts-roi-val ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{s.realized_pnl_pct}%</span>
                        </div>
                        <div className="ts-stats">
                          <div className="ts-stat"><span className="ts-stat-label">Сделок</span><span className="ts-stat-val">{s.closed_trades}</span></div>
                          <div className="ts-stat"><span className="ts-stat-label">Винрейт</span><span className="ts-stat-val">{s.winrate != null ? `${s.winrate}%` : '—'}</span></div>
                          <div className="ts-stat"><span className="ts-stat-label">Открыто</span><span className="ts-stat-val">{s.open_positions}</span></div>
                        </div>
                        <button className="ts-btn">Открыть дашборд</button>
                      </div>
                    )
                  })}
                  {!strategies && [0,1,2].map(i => <div key={i} className="ts-card" style={{ minHeight: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>Загрузка...</div>)}
                </div>
              </div>

              {/* Рынок — виджеты ниже */}
              <section className="section" style={{ marginTop: 28 }}>
                <h2 className="section-title">Рынок</h2>
                <StatsHero stats={stats} loading={loading} />
              </section>
            </div>
          )}
          </ErrorBoundary>
        </main>
      </div>

      {showAuth && <AuthModal initialMode={authMode} onClose={() => setShowAuth(false)} onAuth={setUser} />}

      <style>{`
        .auth-box { display: flex; align-items: center; gap: 8px; }
        .auth-email { font-size: 12px; color: var(--text-secondary); max-width: 90px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .auth-logout { background: none; border: 1px solid var(--border); border-radius: 6px; color: var(--text-tertiary); cursor: pointer; padding: 3px 7px; font-size: 13px; }
        .auth-login-btn { background: var(--accent); color: #fff; border: none; border-radius: 7px; padding: 7px 16px; font-size: 13px; font-weight: 700; cursor: pointer; }
        .plan-badge.tier-free { color: var(--text-secondary); }
        .plan-badge.tier-premium { color: var(--accent); border-color: var(--accent); }
        .plan-badge.tier-vip { color: var(--purple); border-color: var(--purple); }
        .layout { display: flex; min-height: 100vh; background: var(--bg); }
        .layout.sidebar-collapsed .sidebar { width: 56px; }
        .layout.sidebar-collapsed .content { max-width: 100%; }

        /* SPOTLIGHT */
        .spot { position: relative; overflow: hidden; }
        .spot::after { content: ''; position: absolute; inset: 0; border-radius: inherit; background: radial-gradient(360px circle at var(--mx,50%) var(--my,50%), var(--accent-soft), transparent 55%); opacity: 0; transition: opacity 0.35s; pointer-events: none; z-index: 0; }
        .spot:hover::after { opacity: 1; }
        .spot > * { position: relative; z-index: 1; }

        /* SIDEBAR */
        .sidebar { width: 230px; flex-shrink: 0; background: var(--sidebar-bg); border-right: 1px solid var(--sidebar-border); display: flex; flex-direction: column; position: sticky; top: 0; height: 100vh; z-index: 100; overflow-y: auto; overflow-x: hidden; transition: width 0.2s ease; }
        .sidebar-top { display: flex; align-items: center; justify-content: space-between; padding: 14px 10px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
        .sidebar-logo { display: flex; align-items: center; gap: 10px; cursor: pointer; flex: 1; min-width: 0; }
        .logo-icon { width: 32px; height: 32px; background: linear-gradient(135deg, var(--accent), var(--purple)); border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .logo-n { color: #fff; font-size: 17px; font-weight: 900; }
        .logo-text-wrap { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
        .logo-name { font-size: 14px; font-weight: 900; letter-spacing: 0.04em; line-height: 1; }
        .logo-sub { font-size: 9px; color: var(--text-tertiary); letter-spacing: 0.08em; text-transform: uppercase; }
        .sidebar-collapse-btn { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); width: 24px; height: 24px; border-radius: 6px; font-size: 14px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; cursor: pointer; }

        .sidebar-prices { padding: 8px 12px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 6px; background: var(--surface-hover); flex-shrink: 0; flex-wrap: wrap; }
        .sp-item { display: flex; align-items: center; gap: 4px; }
        .sp-sym { font-size: 9px; color: var(--text-tertiary); font-weight: 600; }
        .sp-val { font-family: var(--font-mono); font-size: 10px; font-weight: 700; color: var(--text); }
        .sp-chg { font-family: var(--font-mono); font-size: 9px; font-weight: 600; }
        .sp-chg.pos { color: var(--long); } .sp-chg.neg { color: var(--short); }
        .sp-div { width: 1px; height: 12px; background: var(--border); }

        .sidebar-nav { flex: 1; padding: 8px 8px; display: flex; flex-direction: column; gap: 2px; }
        .nav-group { display: flex; flex-direction: column; gap: 1px; margin-bottom: 8px; }
        .nav-group-title { font-size: 9px; font-weight: 700; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.1em; padding: 8px 10px 4px; }
        .nav-item { display: flex; align-items: center; gap: 9px; padding: 8px 10px; border: none; background: transparent; color: var(--text-tertiary); font-size: 13px; font-weight: 500; border-radius: 8px; transition: all 0.15s; text-align: left; width: 100%; white-space: nowrap; cursor: pointer; }
        .nav-item:hover { background: var(--surface-hover); color: var(--text-secondary); }
        .nav-item.active { background: var(--sidebar-active); color: var(--sidebar-active-text); font-weight: 600; }
        .nav-icon { font-size: 14px; width: 18px; text-align: center; flex-shrink: 0; }
        .nav-label { flex: 1; overflow: hidden; text-overflow: ellipsis; }
        .nav-right { display: flex; align-items: center; gap: 5px; margin-left: auto; }
        .nav-pip { width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
        .nav-badge { font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 4px; color: #fff; }
        .nav-badge.hot { background: var(--short); }
        .nav-badge.ai { background: linear-gradient(135deg, var(--accent), var(--purple)); }
        .nav-badge.beta { background: var(--amber); }

        .sidebar-bottom { padding: 10px 12px; border-top: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
        .scan-status { display: flex; align-items: center; gap: 7px; }
        .scan-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; flex-shrink: 0; }
        .scan-text { display: block; font-size: 10px; color: var(--text-secondary); font-weight: 500; }
        .scan-sub { display: block; font-size: 9px; color: var(--text-tertiary); }
        .sidebar-actions { display: flex; gap: 4px; }
        .theme-toggle { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); width: 28px; height: 28px; border-radius: 7px; font-size: 13px; display: flex; align-items: center; justify-content: center; cursor: pointer; }

        /* TOPBAR */
        .topbar { display: flex; align-items: center; justify-content: space-between; padding: 0 20px; height: 50px; background: var(--sidebar-bg); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 90; gap: 12px; }
        .topbar-left { display: flex; align-items: center; gap: 12px; }
        .burger { border: none; background: transparent; display: flex; flex-direction: column; gap: 4px; padding: 4px; cursor: pointer; }
        .burger span { display: block; width: 18px; height: 2px; background: var(--text); border-radius: 2px; }
        .topbar-prices { display: flex; align-items: center; gap: 14px; }
        .tp-item { display: flex; align-items: center; gap: 5px; }
        .tp-sym { font-size: 10px; color: var(--text-tertiary); font-weight: 600; }
        .tp-val { font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--text); }
        .tp-chg { font-family: var(--font-mono); font-size: 11px; font-weight: 600; }
        .tp-chg.pos { color: var(--long); } .tp-chg.neg { color: var(--short); }
        .tp-div { width: 1px; height: 14px; background: var(--border); }
        .topbar-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .btn-trial { background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; border: none; font-size: 12px; font-weight: 600; padding: 6px 14px; border-radius: 7px; box-shadow: 0 3px 10px rgba(77,140,245,0.3); white-space: nowrap; cursor: pointer; }
        .plan-badge { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; font-weight: 500; padding: 5px 10px; border-radius: 7px; white-space: nowrap; cursor: pointer; }
        .theme-toggle-sm { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); width: 30px; height: 30px; border-radius: 7px; font-size: 14px; cursor: pointer; }

        /* CONTENT */
        .sidebar-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 99; }
        .main-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; }
        .content { flex: 1; max-width: 1040px; width: 100%; margin: 0 auto; padding: 24px 24px 80px; display: flex; flex-direction: column; gap: 0; }
        .section { display: flex; flex-direction: column; gap: 14px; }
        .section-title { font-size: 10px; font-weight: 700; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.1em; display: flex; align-items: center; gap: 8px; }
        .section-title::after { content: ''; flex: 1; height: 1px; background: var(--border); }
        .page-header { margin-bottom: 16px; }
        .page-title { font-size: 24px; font-weight: 800; color: var(--text); letter-spacing: -0.02em; display: flex; align-items: center; gap: 10px; }
        .page-subtitle { font-size: 13px; color: var(--text-secondary); margin-top: 5px; }
        .beta-tag { font-size: 10px; font-weight: 700; background: var(--amber); color: #fff; padding: 2px 7px; border-radius: 4px; }
        .hot-tag { font-size: 10px; font-weight: 700; background: var(--short); color: #fff; padding: 2px 7px; border-radius: 4px; }
        .error-banner { padding: 12px 16px; background: var(--short-soft); color: var(--short); border: 1px solid var(--short-soft); border-radius: var(--radius-md); font-size: 13px; margin-bottom: 20px; }
        .signals-grid { display: grid; gap: 16px; }
        .pos { color: var(--long) !important; } .neg { color: var(--short) !important; }

        /* KPI */
        .kpi-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; }
        .kpi-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px 20px; box-shadow: var(--shadow-card); transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s; }
        .kpi-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); border-color: var(--accent); }
        .kpi-card.accent { background: linear-gradient(135deg, var(--surface), var(--accent-soft)); }
        .kpi-label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
        .kpi-val { font-family: var(--font-mono); font-size: 30px; font-weight: 800; color: var(--text); line-height: 1.1; margin: 8px 0 4px; }
        .kpi-sub { font-size: 11px; color: var(--text-secondary); }

        /* LIVE STRATEGIES */
        .ts-block { margin: 28px 0 0; }
        .ts-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }
        .ts-title { font-size: 17px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .ts-sub { font-size: 12px; color: var(--text-tertiary); }
        .ts-more { border: 1px solid var(--border); background: transparent; color: var(--text-secondary); font-size: 12px; padding: 6px 12px; border-radius: 7px; white-space: nowrap; cursor: pointer; }
        .ts-more:hover { border-color: var(--accent); color: var(--accent); }
        .ts-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; }
        .ts-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px; box-shadow: var(--shadow-card); transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s; cursor: pointer; }
        .ts-card:hover { border-color: var(--accent); transform: translateY(-3px); box-shadow: var(--shadow-lg); }
        .ts-card-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; }
        .ts-name { font-size: 14px; font-weight: 700; color: var(--text); }
        .ts-kind { font-size: 10px; color: var(--text-tertiary); background: var(--surface-hover); padding: 2px 8px; border-radius: 5px; white-space: nowrap; }
        .ts-chart { padding: 4px 0 6px; margin: 0 -4px; }
        .ts-roi-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
        .ts-roi-label { font-size: 10px; color: var(--text-tertiary); }
        .ts-roi-val { font-family: var(--font-mono); font-size: 22px; font-weight: 800; }
        .ts-stats { border-top: 1px solid var(--border); padding-top: 8px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 5px; }
        .ts-stat { display: flex; justify-content: space-between; }
        .ts-stat-label { font-size: 11px; color: var(--text-secondary); }
        .ts-stat-val { font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: var(--text); }
        .ts-btn { width: 100%; padding: 10px; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; border: none; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; transition: opacity 0.2s; }
        .ts-btn:hover { opacity: 0.88; }

        .nav-lock { font-size: 10px; opacity: 0.6; }

        /* TRIAL BANNER */
        .trial-banner { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; background: linear-gradient(135deg, var(--accent-soft), var(--purple-soft)); border: 1px solid var(--accent); border-radius: var(--radius-md); padding: 10px 16px; font-size: 13px; color: var(--text); margin-bottom: 20px; }
        .trial-banner button { background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; border: none; border-radius: 7px; padding: 6px 14px; font-size: 12px; font-weight: 700; cursor: pointer; white-space: nowrap; }

        /* UPGRADE LOCK */
        .lock-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 56px 32px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px; box-shadow: var(--shadow-card); position: relative; overflow: hidden; }
        .lock-card::before { content: ''; position: absolute; top: -120px; left: 50%; transform: translateX(-50%); width: 500px; height: 360px; background: radial-gradient(circle, var(--accent-soft) 0%, transparent 65%); pointer-events: none; }
        .lock-icon { font-size: 44px; position: relative; }
        .lock-badge { position: relative; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em; color: #fff; background: linear-gradient(135deg, var(--accent), var(--purple)); padding: 4px 12px; border-radius: 20px; }
        .lock-title { font-size: 22px; font-weight: 800; color: var(--text); position: relative; }
        .lock-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; max-width: 440px; position: relative; }
        .lock-btn { position: relative; margin-top: 6px; padding: 12px 28px; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 700; cursor: pointer; box-shadow: 0 8px 24px rgba(77,140,245,0.35); }
        .lock-btn:hover { opacity: 0.9; }
        .lock-feats { display: flex; flex-wrap: wrap; gap: 8px 18px; justify-content: center; margin-top: 12px; position: relative; }
        .lock-feat { font-size: 12px; color: var(--text-secondary); }

        /* COMING SOON */
        .coming-soon-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 64px 32px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 14px; }
        .cs-icon { font-size: 48px; opacity: 0.3; }
        .cs-title { font-size: 22px; font-weight: 700; color: var(--text); }
        .cs-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; max-width: 400px; }
        .cs-badge { background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent-soft); padding: 6px 16px; border-radius: 20px; font-size: 13px; font-weight: 600; }

        /* SKELETON & EMPTY */
        .signal-skeleton { border-radius: var(--radius-lg); overflow: hidden; background: var(--surface); border: 1px solid var(--border); }
        .sk-bar { height: 4px; } .sk-content { padding: 22px; display: flex; flex-direction: column; gap: 14px; }
        .sk-row { display: flex; gap: 12px; align-items: center; } .sk-circle { width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0; }
        .sk-line { height: 14px; border-radius: 6px; flex: 1; } .sk-chart { height: 180px; border-radius: 8px; }
        .empty-signal { padding: 48px 32px; text-align: center; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); display: flex; flex-direction: column; align-items: center; gap: 14px; }
        .empty-icon { font-size: 40px; opacity: 0.4; } .empty-title { font-size: 16px; font-weight: 600; color: var(--text-secondary); }
        .empty-desc { font-size: 13px; color: var(--text-tertiary); line-height: 1.6; max-width: 320px; }
        .empty-pulse { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--long); background: var(--long-soft); padding: 8px 16px; border-radius: 20px; }

        @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(0,229,168,0.4)} 70%{box-shadow:0 0 0 8px rgba(0,229,168,0)} 100%{box-shadow:0 0 0 0 rgba(0,229,168,0)} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        .animate-in { animation: fadeIn 0.35s ease forwards; }

        @media (max-width: 1100px) { .ts-grid { grid-template-columns: repeat(2,1fr); } .kpi-grid { grid-template-columns: repeat(2,1fr); } }
        @media (max-width: 768px) {
          .sidebar { position: fixed; left: -240px; top: 0; height: 100vh; transition: left 0.3s ease; z-index: 100; }
          .layout.sidebar-open .sidebar { left: 0; }
          .burger { display: flex; }
          .content { padding: 16px 14px 80px; }
          .topbar-prices { display: none; }
          .ts-grid { grid-template-columns: 1fr; }
          .kpi-grid { grid-template-columns: 1fr 1fr; }
          /* topbar-right не должен выталкивать страницу в горизонтальный скролл */
          .topbar { padding: 0 12px; }
          .topbar-right { gap: 6px; }
          .topbar-right .btn-trial { display: none; }
          .auth-email { max-width: 64px; }
        }
        @media (max-width: 480px) {
          /* Триал-баннер: аккуратный стек вместо кривого переноса кнопки */
          .trial-banner { flex-direction: column; align-items: stretch; text-align: center; gap: 10px; }
          .trial-banner button { width: 100%; padding: 9px 14px; }
          .page-title { font-size: 21px; }
          .kpi-grid > * { padding: 14px 16px; }
          .section-title { font-size: 15px; }
        }
      `}</style>
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
      <div className="empty-desc">Сканер анализирует 32 пары на Bybit. Когда найдёт точку входа — сигнал появится здесь автоматически.</div>
      <div className="empty-pulse"><span style={{width:7,height:7,borderRadius:'50%',background:'var(--long)',animation:'pulse 2s infinite',display:'inline-block'}} />Сканирование каждые 2 минуты</div>
    </div>
  )
}
