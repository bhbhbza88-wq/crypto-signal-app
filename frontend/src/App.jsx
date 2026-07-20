import { useEffect, useState, useCallback, useRef, useMemo, Component, lazy, Suspense } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, getToken, setToken } from './api'
import AuthModal from './AuthModal'
import SignalCard from './SignalCard'
import AccountMenu from './AccountMenu'
import { useI18n } from './i18n'
import { useLivePrices, CountUp, resultLabel, TG_BOT, APP_SECTIONS, polishHistory, polishStats } from './shared'
import './App.css'

const Pricing = lazy(() => import('./Pricing'))
const HistoryTable = lazy(() => import('./HistoryTable'))
const AIChat = lazy(() => import('./AIChat'))
const ChartAnalyze = lazy(() => import('./ChartAnalyze'))
const Admin = lazy(() => import('./Admin'))
const ChannelAnalyzer = lazy(() => import('./ChannelAnalyzer'))

const POLL_SIGNALS_MS = 15000
const POLL_STATS_MS = 75000
const CORE_POLL_TABS = new Set(['overview', 'history'])
const VALID_TABS = new Set(APP_SECTIONS)

// Ошибка в одной вкладке не должна ронять всё приложение в белый экран
class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  componentDidUpdate(prevProps) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) this.setState({ error: null })
  }
  render() {
    const { t } = this.props
    if (this.state.error) {
      return (
        <div className="section animate-in" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
          <h2 style={{ marginBottom: 8 }}>{t ? t('err.boundary') : 'Something went wrong'}</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 20 }}>
            {t ? t('err.boundarySub') : 'Try refreshing the page.'}
          </p>
          <button className="btn-primary" onClick={() => window.location.reload()}>{t ? t('err.reload') : 'Reload'}</button>
        </div>
      )
    }
    return this.props.children
  }
}

const NAV_SECTIONS = [
  { titleKey: 'nav.main', items: [
    { key: 'overview',      labelKey: 'nav.dashboard', icon: '◈' },
    { key: 'chart_analyze', labelKey: 'nav.chart',     icon: '▣', badge: 'NEW' },
    { key: 'history',       labelKey: 'nav.history',   icon: '≡' },
    { key: 'ai_assistant',  labelKey: 'nav.ai',        icon: '✦', badge: 'BETA' },
  ]},
  { titleKey: 'nav.account', items: [
    { key: 'pricing',      labelKey: 'nav.pricing',   icon: '💎' },
  ]},
]

function onSpot(e) {
  const r = e.currentTarget.getBoundingClientRect()
  e.currentTarget.style.setProperty('--mx', `${((e.clientX - r.left) / r.width) * 100}%`)
  e.currentTarget.style.setProperty('--my', `${((e.clientY - r.top) / r.height) * 100}%`)
}

function KPI({ keyName, label, value, suffix, sub, accent }) {
  return (
    <div className={`kpi-card spot ${accent ? 'accent' : ''}`} onMouseMove={onSpot}>
      <div className="kpi-key mono">{keyName}</div>
      <div className="kpi-val"><CountUp value={value} suffix={suffix} /></div>
      <div className="kpi-meta">
        <span className="kpi-label">{label}</span>
        <span className="kpi-sub">{sub}</span>
      </div>
    </div>
  )
}

function requestPush() { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission() }
function sendPush(title, body) { if ('Notification' in window && Notification.permission === 'granted') new Notification(title, { body }) }

function RecentSignals({ history, isPremium, onUpgrade, onSeeAll, t }) {
  const rows = polishHistory(history).slice(0, 8)
  if (!rows.length) return null
  return (
    <div className="rs-card">
      <div className="rs-chrome">
        <span className="rs-prompt mono">tail -n 8 ./history.log</span>
        {isPremium && (
          <button className="rs-more" onClick={onSeeAll}>{t('recent.all')}</button>
        )}
      </div>
      <div className="rs-list-wrap">
        <div className={`rs-list ${!isPremium ? 'rs-blur' : ''}`}>
          <div className="rs-cols mono">
            <span>symbol</span><span>side</span><span>result</span><span>pnl</span>
          </div>
          {rows.map((row) => (
            <div className="rs-row" key={row.id}>
              <span className="rs-sym mono">{row.symbol.replace('/USDT', '')}</span>
              <span className={`rs-dir ${row.signal === 'LONG' ? 'long' : 'short'}`}>{row.signal}</span>
              <span className="rs-res mono">{resultLabel(t, row.result)}</span>
              <span className={`rs-pnl mono ${row.pnl > 0 ? 'pos' : row.pnl < 0 ? 'neg' : ''}`}>
                {row.pnl > 0 ? '+' : ''}{row.pnl}%
              </span>
            </div>
          ))}
        </div>
        {!isPremium && (
          <div className="rs-lock">
            <span className="rs-lock-icon mono">#</span>
            <span className="rs-lock-text">{t('recent.lock')}</span>
            <button className="rs-lock-btn" onClick={onUpgrade}>{t('recent.unlock')}</button>
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
  const { t } = useI18n()

  const [signals, setSignals] = useState([])
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)
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

  useEffect(() => {
    if (getToken()) {
      api.me().then(r => setUser(r.user)).catch(() => setToken(null))
    }
  }, [])

  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null)
      setAuthMode('login')
      setShowAuth(true)
    }
    window.addEventListener('auth:unauthorized', onUnauthorized)
    return () => window.removeEventListener('auth:unauthorized', onUnauthorized)
  }, [])

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

  const fetchSignals = useCallback(async () => {
    try {
      const s = await api.getSignals()
      if (s.length > 0 && prevRef.current.length === 0) {
        sendPush(`🚨 NOWICKI: ${s[0].signal} ${s[0].symbol}`, `Score ${s[0].score}/20`)
      }
      prevRef.current = s
      setSignals(s)
      setError(null)
    } catch {
      setError('offline')
    }
  }, [])

  const fetchStatsHistory = useCallback(async () => {
    try {
      const [h, st] = await Promise.all([api.getHistory(500, 30), api.getStats()])
      setHistory(h)
      setStats(st)
      setError(null)
    } catch {
      setError('offline')
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const boot = async () => {
      await Promise.all([fetchSignals(), fetchStatsHistory()])
      if (!cancelled) setLoading(false)
    }
    boot()

    const shouldPoll = () =>
      document.visibilityState === 'visible' && CORE_POLL_TABS.has(tab)

    const sigId = setInterval(() => { if (shouldPoll()) fetchSignals() }, POLL_SIGNALS_MS)
    const stId = setInterval(() => { if (shouldPoll()) fetchStatsHistory() }, POLL_STATS_MS)

    const onVis = () => {
      if (shouldPoll()) {
        fetchSignals()
        fetchStatsHistory()
      }
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      cancelled = true
      clearInterval(sigId)
      clearInterval(stId)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [fetchSignals, fetchStatsHistory, tab])

  const isPremium = !!user && (user.tier === 'premium' || user.tier === 'vip')
  const [tgBusy, setTgBusy] = useState(false)

  async function openTelegramBot(e) {
    // Залогинен → тот же deep-link, что «Подключить Telegram» (привязка + каналы если Premium).
    // Гость → обычная ссылка на бота.
    if (!user) return
    e.preventDefault()
    if (tgBusy) return
    setTgBusy(true)
    try {
      const r = await api.telegramLinkToken()
      window.open(r.bot_url, '_blank', 'noopener,noreferrer')
    } catch {
      window.open(TG_BOT, '_blank', 'noopener,noreferrer')
    } finally {
      setTgBusy(false)
    }
  }

  const navSections = useMemo(() => {
    const base = NAV_SECTIONS.map((sec) => ({
      title: t(sec.titleKey),
      items: sec.items.map((item) => ({
        ...item,
        label: t(item.labelKey),
      })),
    }))
    if (!user?.is_admin) return base
    return [...base, {
      title: t('nav.admin'),
      items: [
        { key: 'admin', label: t('nav.adminPanel'), icon: '🛠' },
        { key: 'channel_analyzer', label: t('nav.channelAnalyzer'), icon: '🔬' },
      ],
    }]
  }, [t, user?.is_admin])

  return (
    <div className={`layout ${sidebarOpen ? 'sidebar-open' : ''} ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>

      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="sidebar-logo" onClick={() => navigate('/')}>
            {!sidebarCollapsed && (
              <><div className="logo-icon"><span className="logo-n">N</span></div>
              <div className="logo-text-wrap">
                <span className="logo-name gradient-text">NOWICKI</span>
                <span className="logo-sub">~/signal-relay</span>
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
              {sec.items.map((navItem) => (
                <button
                  key={navItem.key}
                  className={`nav-item ${tab === navItem.key ? 'active' : ''}`}
                  onClick={() => setTab(navItem.key)}
                  title={sidebarCollapsed ? navItem.label : ''}
                >
                  <span className="nav-icon">{navItem.icon}</span>
                  {!sidebarCollapsed && <span className="nav-label">{navItem.label}</span>}
                  {!sidebarCollapsed && (
                    <div className="nav-right">
                      {navItem.badge && <span className={`nav-badge ${
                        navItem.badge==='HOT' ? 'hot' :
                        navItem.badge==='AI' ? 'ai' :
                        navItem.badge==='LIVE' ? 'live' :
                        navItem.badge==='NEW' ? 'new' : 'beta'
                      }`}>{navItem.badge}</span>}
                      {tab === navItem.key && <span className="nav-pip" />}
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
                <span className="scan-text">{t('scan.online')}</span>
                <span className="scan-sub">{t('scan.sub')}</span>
              </div>
            </div>
          )}
        </div>
      </aside>

      {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}

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
            <a
              className="btn-tg-bot"
              href={TG_BOT}
              target="_blank"
              rel="noopener noreferrer"
              onClick={openTelegramBot}
              aria-busy={tgBusy || undefined}
              aria-label={`${t('top.telegram')} ${t('top.bot')}`}
            >
              {t('top.telegram')} <span className="btn-tg-label">{t('top.bot')}</span>
            </a>
            <button className="btn-trial" onClick={() => setTab('ai_assistant')}>{t('top.ai')}</button>
            <AccountMenu
              user={user}
              dark={dark}
              onToggleTheme={() => setDark((d) => !d)}
              onLogout={logout}
              onLogin={() => { setAuthMode('login'); setShowAuth(true) }}
              onOpenPricing={() => setTab('pricing')}
            />
          </div>
        </header>

        <main className="content">
          {error && <div className="error-banner animate-in">{t('err.offline')}</div>}

          {user?.on_trial && (
            <div className="trial-banner animate-in">
              <span>✦ <strong>{t('trial.active')}</strong> — {t('trial.left', {
                n: user.trial_days_left,
                unit: user.trial_days_left === 1 ? t('trial.day') : t('trial.days'),
              })}</span>
              <button onClick={() => setTab('pricing')}>{t('trial.cta')}</button>
            </div>
          )}

          <ErrorBoundary resetKey={tab} t={t}>
          <Suspense fallback={<div className="section animate-in" style={{ padding: 40, color: 'var(--text-tertiary)' }}>{t('load.section')}</div>}>
          {tab === 'ai_assistant' && (
            <section className="section section-ai-desk animate-in">
              <AIChat />
            </section>
          )}
          {tab === 'chart_analyze' && (
            <section className="section animate-in">
              <div className="page-header">
                <h1 className="page-title">{t('chart.title')} <span className="beta-tag">BETA</span></h1>
                <p className="page-subtitle">{t('chart.subtitle')}</p>
              </div>
              <ChartAnalyze
                user={user}
                onNeedAuth={() => { setAuthMode('login'); setShowAuth(true) }}
              />
            </section>
          )}
          {tab === 'history' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">{t('hist.title')}</h1><p className="page-subtitle">{t('hist.subtitle')}</p></div><HistoryTable history={history} stats={stats} isPremium={isPremium} onUpgrade={() => user ? setTab('pricing') : (setAuthMode('register'), setShowAuth(true))} /></section>}
          {tab === 'pricing' && <section className="section animate-in"><Pricing user={user} /></section>}
          {tab === 'admin' && user?.is_admin && <Admin />}
          {tab === 'channel_analyzer' && user?.is_admin && <section className="section animate-in"><ChannelAnalyzer /></section>}
          </Suspense>
          {tab === 'overview' && (
            <div className="animate-in dash dash-console">
              <div className="dash-window">
                <div className="dash-titlebar">
                  <span className="dash-dot r" /><span className="dash-dot a" /><span className="dash-dot g" />
                  <span className="dash-path mono">{t('dash.path')}</span>
                  <span className="dash-live-pill"><i />{t('dash.live')}</span>
                </div>
                <div className="dash-body">
                  <div className="dash-hero">
                    <div className="dash-hero-text">
                      <pre className="dash-boot mono">{t('dash.boot')}</pre>
                      <h1 className="page-title">{t('dash.title')}</h1>
                      <p className="page-subtitle">{t('dash.sub')}</p>
                    </div>
                    {prices && (
                      <div className="dash-ticker">
                        <div className="dt-head mono">$ quote.watch</div>
                        <div className="dt-row">
                          <span className="mono">BTC</span>
                          <b className="mono">${prices.btc.price}</b>
                          <i className={`mono ${prices.btc.positive ? 'pos' : 'neg'}`}>{prices.btc.positive ? '+' : ''}{prices.btc.change}%</i>
                        </div>
                        <div className="dt-row">
                          <span className="mono">ETH</span>
                          <b className="mono">${prices.eth.price}</b>
                          <i className={`mono ${prices.eth.positive ? 'pos' : 'neg'}`}>{prices.eth.positive ? '+' : ''}{prices.eth.change}%</i>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="kpi-grid">
                    <KPI keyName="active_signals" label={t('kpi.active')} value={signals.length} sub={signals.length ? t('kpi.activeSub') : t('kpi.wait')} accent />
                    <KPI keyName="closed_30d" label={t('kpi.closed')} value={displayStats.total} sub={t('kpi.closedSub')} />
                    <KPI keyName="winrate" label={t('kpi.winrate')} value={displayStats.winrate} suffix="%" sub={t('kpi.winrateSub')} />
                    <KPI keyName="avg_pnl" label={t('kpi.avgPnl')} value={displayStats.avgPnl} suffix="%" sub={t('kpi.avgPnlSub')} />
                  </div>

                  <div className={`dash-split${history.length > 0 ? ' has-rail' : ''}`}>
                    <section className="section dash-section dash-main-col">
                      <div className="dash-sec-head">
                        <h2 className="dash-sec-title mono">{t('sec.active')}</h2>
                        <span className="sec-count mono">{signals.length}</span>
                      </div>
                      {loading ? <SignalSkeleton /> : signals.length === 0 ? <EmptySignal t={t} /> : (
                        <div className="signals-grid">
                          {signals.map(s => <SignalCard key={s.id ?? s.symbol} signal={s} />)}
                        </div>
                      )}
                    </section>

                    {history.length > 0 && (
                      <section className="section dash-section dash-rail">
                        <div className="dash-sec-head">
                          <h2 className="dash-sec-title mono">{t('sec.recent')}</h2>
                        </div>
                        <RecentSignals
                          history={history}
                          isPremium={isPremium}
                          t={t}
                          onSeeAll={() => setTab('history')}
                          onUpgrade={() => user ? setTab('pricing') : (setAuthMode('register'), setShowAuth(true))}
                        />
                      </section>
                    )}
                  </div>
                </div>
              </div>
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

function EmptySignal({ t }) {
  return (
    <div className="empty-signal animate-in">
      <pre className="empty-boot mono">{t('empty.boot')}</pre>
      <div className="empty-title">{t('empty.title')}</div>
      <div className="empty-desc">{t('empty.desc')}</div>
      <div className="empty-pulse">
        <span className="empty-pulse-dot" />
        <span className="mono">{t('empty.pulse')}</span>
      </div>
    </div>
  )
}
