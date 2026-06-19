import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api'
import StatsHero from './StatsHero'
import SignalCard from './SignalCard'
import HistoryTable from './HistoryTable'
import MarketView from './MarketView'
import AIChat from './AIChat'

const POLL_INTERVAL = 15000
const MARKET_POLL_INTERVAL = 60000

const NAV_SECTIONS = [
  {
    items: [
      { key: 'overview',   label: 'Dashboard',       icon: '◈', hotkey: '1' },
      { key: 'portfolio',  label: 'Мой портфель',    icon: '◉', hotkey: '2', soon: true },
      { key: 'strategies', label: 'Стратегии',       icon: '★', hotkey: '3', badge: 'HOT' },
    ]
  },
  {
    title: 'Инструменты',
    items: [
      { key: 'market',     label: 'Скринер',         icon: '⬡', hotkey: '4' },
      { key: 'signal',     label: 'Сигнал-бот',      icon: '⚡', hotkey: '5', soon: true },
      { key: 'scanner',    label: 'AI Сканер',        icon: '✦', hotkey: '6', badge: 'AI' },
      { key: 'history',    label: 'История',          icon: '≡', hotkey: '7' },
    ]
  },
  {
    title: 'Аккаунт',
    items: [
      { key: 'ai',         label: 'AI Ассистент',    icon: '✦', hotkey: '8', badge: 'BETA' },
      { key: 'invite',     label: 'Пригласить друга', icon: '👥', hotkey: '9', soon: true },
      { key: 'settings',   label: 'Настройки',       icon: '⚙', hotkey: '0', soon: true },
    ]
  }
]

const STEPS = [
  { icon: '✓', title: 'Сканер запущен', desc: 'Анализирует 32 пары на Bybit', done: true },
  { icon: '◈', title: 'Ищем сигнал', desc: 'EMA · RSI · ADX · ATR', active: true },
  { icon: '⚡', title: 'Уровни выставлены', desc: 'TP1 · TP2 · TP3 · SL' },
  { icon: '✦', title: 'AI объясняет', desc: 'Причины входа и риски' },
]

const TOP_STRATEGIES = [
  { symbol: 'ETC/USDT', dir: 'LONG', days: 182, roi: 23.4, apy: 46.8, minDeposit: 50, drawdown: -12.3 },
  { symbol: 'SOL/USDT', dir: 'LONG', days: 90,  roi: 18.7, apy: 75.8, minDeposit: 100, drawdown: -15.1 },
  { symbol: 'BNB/USDT', dir: 'SHORT', days: 60, roi: 11.2, apy: 68.3, minDeposit: 50, drawdown: -8.4 },
]

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

function requestPush() { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission() }
function sendPush(title, body) { if ('Notification' in window && Notification.permission === 'granted') new Notification(title, { body }) }

// Mini ROI chart SVG
function MiniChart({ positive }) {
  const points = positive
    ? "0,40 20,35 40,30 60,20 80,15 100,5 120,8 140,3"
    : "0,5 20,8 40,15 60,20 80,30 100,35 120,32 140,38"
  const fill = positive
    ? "rgba(0,229,168,0.15)"
    : "rgba(255,79,96,0.15)"
  const stroke = positive ? "var(--long)" : "var(--short)"
  return (
    <svg width="140" height="50" viewBox="0 0 140 50" style={{ display: 'block' }}>
      <defs>
        <linearGradient id={`g${positive}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={positive ? "#00e5a8" : "#ff4f60"} stopOpacity="0.3"/>
          <stop offset="100%" stopColor={positive ? "#00e5a8" : "#ff4f60"} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <polygon points={`0,40 ${points} 140,50 0,50`} fill={`url(#g${positive})`} />
      <polyline points={points} fill="none" stroke={stroke} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/>
    </svg>
  )
}

export default function App() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('overview')
  const [signals, setSignals] = useState([])
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)
  const [market, setMarket] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const prevRef = useRef([])
  const prices = useLivePrices()

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
      const map = { '1':'overview','2':'portfolio','3':'strategies','4':'market','5':'signal','6':'scanner','7':'history','8':'ai' }
      if (map[e.key]) setTab(map[e.key])
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
      prevRef.current = s
      setSignals(s); setHistory(h); setStats(st); setError(null)
    } catch { setError('Нет связи с сервером.') }
    finally { setLoading(false) }
  }, [])

  const fetchMarket = useCallback(async () => { try { setMarket(await api.getMarket()) } catch {} }, [])

  useEffect(() => { fetchCore(); const id = setInterval(fetchCore, POLL_INTERVAL); return () => clearInterval(id) }, [fetchCore])
  useEffect(() => {
    if (tab !== 'market') return
    fetchMarket(); const id = setInterval(fetchMarket, MARKET_POLL_INTERVAL); return () => clearInterval(id)
  }, [tab, fetchMarket])

  const allTabs = NAV_SECTIONS.flatMap(s => s.items)
  const currentTab = allTabs.find(t => t.key === tab)

  return (
    <div className={`layout ${sidebarOpen ? 'sidebar-open' : ''}`}>

      {/* ── SIDEBAR ── */}
      <aside className="sidebar">
        <div className="sidebar-logo" onClick={() => navigate('/')}>
          <div className="logo-icon"><span className="logo-n">N</span></div>
          <div className="logo-text-wrap">
            <span className="logo-name gradient-text">NWICKI</span>
            <span className="logo-sub">Crypto Scanner</span>
          </div>
        </div>

        {prices && (
          <div className="sidebar-prices">
            <div className="sp-item">
              <span className="sp-sym">₿</span>
              <span className="sp-val">${prices.btc.price}</span>
              <span className={`sp-chg ${prices.btc.positive ? 'pos' : 'neg'}`}>{prices.btc.positive ? '▲' : '▼'}{Math.abs(prices.btc.change)}%</span>
            </div>
            <div className="sp-div" />
            <div className="sp-item">
              <span className="sp-sym">Ξ</span>
              <span className="sp-val">${prices.eth.price}</span>
              <span className={`sp-chg ${prices.eth.positive ? 'pos' : 'neg'}`}>{prices.eth.positive ? '▲' : '▼'}{Math.abs(prices.eth.change)}%</span>
            </div>
          </div>
        )}

        <nav className="sidebar-nav">
          {NAV_SECTIONS.map((section, si) => (
            <div key={si} className="nav-section">
              {section.title && <div className="nav-section-title">{section.title}</div>}
              {section.items.map((t) => (
                <button
                  key={t.key}
                  className={`nav-item ${tab === t.key ? 'active' : ''} ${t.soon ? 'soon' : ''}`}
                  onClick={() => { if (!t.soon) { setTab(t.key); setSidebarOpen(false) } }}
                  title={t.soon ? 'Скоро' : ''}
                >
                  <span className="nav-icon">{t.icon}</span>
                  <span className="nav-label">{t.label}</span>
                  <div className="nav-right">
                    {t.badge && <span className={`nav-badge ${t.badge === 'HOT' ? 'hot' : t.badge === 'AI' ? 'ai' : 'beta'}`}>{t.badge}</span>}
                    {t.soon && <span className="nav-soon">Скоро</span>}
                    {tab === t.key && !t.soon && <span className="nav-pip" />}
                  </div>
                </button>
              ))}
            </div>
          ))}
        </nav>

        {/* Community banner like 3Commas */}
        <div className="sidebar-banner">
          <div className="banner-icon">✈</div>
          <div>
            <div className="banner-title">Сообщество</div>
            <div className="banner-desc">Тысячи трейдеров уже используют NWICKI</div>
          </div>
          <button className="banner-btn">Войти</button>
        </div>

        <div className="sidebar-bottom">
          <div className="scan-status">
            <span className="scan-dot" />
            <div>
              <span className="scan-text">Сканирую рынок</span>
              <span className="scan-sub">каждые 2 мин</span>
            </div>
          </div>
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
            <span className="topbar-logo gradient-text">NWICKI</span>
          </div>
          {prices && (
            <div className="topbar-prices">
              <div className="tp-item">
                <span className="tp-sym">BTC/USDT</span>
                <span className="tp-val">${prices.btc.price}</span>
                <span className={`tp-chg ${prices.btc.positive ? 'pos' : 'neg'}`}>{prices.btc.positive ? '▲' : '▼'}{Math.abs(prices.btc.change)}%</span>
              </div>
              <div className="tp-div" />
              <div className="tp-item">
                <span className="tp-sym">ETH/USDT</span>
                <span className="tp-val">${prices.eth.price}</span>
                <span className={`tp-chg ${prices.eth.positive ? 'pos' : 'neg'}`}>{prices.eth.positive ? '▲' : '▼'}{Math.abs(prices.eth.change)}%</span>
              </div>
            </div>
          )}
          <div className="topbar-right">
            <button className="btn-create" onClick={() => setTab('market')}>+ Скринер</button>
            <button className="btn-trial" onClick={() => setTab('ai')}>✦ AI Ассистент</button>
            <button className="theme-toggle-sm" onClick={() => setDark(d => !d)}>{dark ? '☀' : '☾'}</button>
          </div>
        </header>

        <main className="content">
          {error && <div className="error-banner animate-in">{error}</div>}

          {/* ── OVERVIEW ── */}
          {tab === 'overview' && (
            <div className="animate-in">
              <div className="page-header">
                <div className="page-header-left">
                  <h1 className="page-title">Dashboard</h1>
                </div>
              </div>
              <div className="page-tabs-row">
                <span className="page-tab active">Главная</span>
                <span className="page-tab" onClick={() => setTab('ai')}>Руководство</span>
              </div>

              <div className="steps-grid">
                {STEPS.map((s, i) => (
                  <div key={i} className={`step-card ${s.done ? 'done' : ''} ${s.active ? 'active-step' : ''}`}>
                    <div className={`step-icon-wrap ${s.done ? 'done' : s.active ? 'act' : ''}`}>{s.icon}</div>
                    <div className="step-title">{s.title}</div>
                    <div className="step-desc">{s.desc}</div>
                    {s.done && <div className="step-check">✓</div>}
                    {s.active && <button className="step-btn" onClick={() => setTab('market')}>Скринер →</button>}
                  </div>
                ))}
              </div>

              <StatsHero stats={stats} loading={loading} />

              {/* Top strategies like 3Commas */}
              <div className="top-strategies">
                <div className="ts-header">
                  <div>
                    <h2 className="ts-title">Лучшие сигналы</h2>
                    <p className="ts-sub">Исторические результаты сканера по парам</p>
                  </div>
                  <button className="ts-more" onClick={() => setTab('history')}>Все результаты →</button>
                </div>
                <div className="ts-grid">
                  {TOP_STRATEGIES.map((s, i) => (
                    <div key={i} className="ts-card">
                      <div className="ts-card-header">
                        <div className="ts-coin">
                          <div className="ts-coin-icon">{s.symbol.replace('/USDT','').charAt(0)}</div>
                          <div>
                            <div className="ts-symbol">{s.symbol}</div>
                            <div className="ts-tags">
                              <span className={`ts-tag ${s.dir === 'LONG' ? 'long' : 'short'}`}>{s.dir}</span>
                              <span className="ts-tag neutral">SPOT</span>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="ts-chart"><MiniChart positive={s.roi > 0} /></div>
                      <div className="ts-roi-row">
                        <span className="ts-roi-label">{s.days}Д BACKTEST, ROI</span>
                        <span className={`ts-roi-val ${s.roi > 0 ? 'pos' : 'neg'}`}>{s.roi > 0 ? '+' : ''}{s.roi}%</span>
                      </div>
                      <div className="ts-stats">
                        <div className="ts-stat"><span className="ts-stat-label">APY</span><span className="ts-stat-val">{s.apy}%</span></div>
                        <div className="ts-stat"><span className="ts-stat-label">Мин. депозит</span><span className="ts-stat-val">${s.minDeposit}</span></div>
                        <div className="ts-stat"><span className="ts-stat-label">Макс. просадка</span><span className="ts-stat-val neg">{s.drawdown}%</span></div>
                      </div>
                      <button className="ts-btn" onClick={() => setTab('market')}>Открыть скринер</button>
                    </div>
                  ))}
                </div>
              </div>

              <section className="section" style={{ marginTop: 28 }}>
                <h2 className="section-title">Активный сигнал</h2>
                {loading ? <SignalSkeleton /> : signals.length === 0 ? <EmptySignal /> : (
                  <div className="signals-grid">{signals.map(s => <SignalCard key={s.symbol} signal={s} />)}</div>
                )}
              </section>
            </div>
          )}

          {/* ── MARKET / SCREENER ── */}
          {(tab === 'market' || tab === 'scanner') && (
            <section className="section animate-in">
              <div className="page-header"><h1 className="page-title">Скринер рынка</h1></div>
              <MarketView market={market} />
            </section>
          )}

          {/* ── HISTORY ── */}
          {tab === 'history' && (
            <section className="section animate-in">
              <div className="page-header"><h1 className="page-title">История сделок</h1></div>
              <HistoryTable history={history} />
            </section>
          )}

          {/* ── AI ── */}
          {tab === 'ai' && (
            <section className="section animate-in">
              <div className="page-header"><h1 className="page-title">AI Ассистент <span className="beta-tag">BETA</span></h1></div>
              <AIChat signals={signals} stats={stats} market={market} />
            </section>
          )}

          {/* ── STRATEGIES ── */}
          {tab === 'strategies' && (
            <section className="section animate-in">
              <div className="page-header"><h1 className="page-title">Стратегии <span className="hot-tag">HOT</span></h1></div>
              <div className="coming-soon-card">
                <div className="cs-icon">★</div>
                <div className="cs-title">Галерея стратегий</div>
                <div className="cs-desc">Здесь будут автоматические стратегии сканера с историческими результатами. Выбери стратегию и запусти одним кликом.</div>
                <div className="cs-badge">Скоро</div>
              </div>
            </section>
          )}

          {/* ── SOON pages ── */}
          {(tab === 'portfolio' || tab === 'signal' || tab === 'invite' || tab === 'settings') && (
            <section className="section animate-in">
              <div className="page-header"><h1 className="page-title">{currentTab?.label}</h1></div>
              <div className="coming-soon-card">
                <div className="cs-icon">{currentTab?.icon}</div>
                <div className="cs-title">{currentTab?.label}</div>
                <div className="cs-desc">Этот раздел находится в разработке. Следи за обновлениями!</div>
                <div className="cs-badge">Скоро</div>
              </div>
            </section>
          )}
        </main>
      </div>

      <style>{`
        .layout { display: flex; min-height: 100vh; background: var(--bg); }

        /* ── SIDEBAR ── */
        .sidebar {
          width: 240px; flex-shrink: 0;
          background: var(--sidebar-bg); border-right: 1px solid var(--sidebar-border);
          box-shadow: var(--shadow-sidebar);
          display: flex; flex-direction: column;
          position: sticky; top: 0; height: 100vh; z-index: 100;
          overflow-y: auto;
        }
        .sidebar-logo {
          display: flex; align-items: center; gap: 12px;
          padding: 18px 18px 14px; border-bottom: 1px solid var(--border);
          cursor: pointer; flex-shrink: 0;
        }
        .logo-icon { width: 34px; height: 34px; background: linear-gradient(135deg, var(--accent), var(--purple)); border-radius: 9px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-shadow: 0 3px 10px rgba(77,140,245,0.35); }
        .logo-n { color: #fff; font-size: 18px; font-weight: 900; }
        .logo-text-wrap { display: flex; flex-direction: column; gap: 1px; }
        .logo-name { font-size: 15px; font-weight: 900; letter-spacing: 0.04em; line-height: 1; }
        .logo-sub { font-size: 9px; color: var(--text-tertiary); letter-spacing: 0.08em; text-transform: uppercase; }

        .sidebar-prices { padding: 8px 14px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; background: var(--surface-hover); flex-shrink: 0; }
        .sp-item { display: flex; align-items: center; gap: 4px; flex: 1; }
        .sp-sym { font-size: 10px; color: var(--text-tertiary); font-weight: 600; }
        .sp-val { font-family: var(--font-mono); font-size: 10px; font-weight: 700; color: var(--text); }
        .sp-chg { font-family: var(--font-mono); font-size: 9px; font-weight: 600; }
        .sp-chg.pos { color: var(--long); } .sp-chg.neg { color: var(--short); }
        .sp-div { width: 1px; height: 14px; background: var(--border); }

        .sidebar-nav { flex: 1; padding: 10px 10px; display: flex; flex-direction: column; gap: 2px; }
        .nav-section { margin-bottom: 8px; }
        .nav-section-title { font-size: 10px; font-weight: 700; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.08em; padding: 6px 12px 4px; }
        .nav-item {
          display: flex; align-items: center; gap: 10px; padding: 9px 12px;
          border: none; background: transparent; color: var(--text-tertiary);
          font-size: 13px; font-weight: 500; border-radius: var(--radius-md);
          transition: all 0.15s; position: relative; text-align: left; width: 100%;
        }
        .nav-item:hover:not(.soon) { background: var(--surface-hover); color: var(--text-secondary); }
        .nav-item.active { background: var(--sidebar-active); color: var(--sidebar-active-text); font-weight: 600; }
        .nav-item.soon { opacity: 0.5; cursor: not-allowed; }
        .nav-icon { font-size: 14px; width: 18px; text-align: center; flex-shrink: 0; }
        .nav-label { flex: 1; }
        .nav-right { display: flex; align-items: center; gap: 5px; }
        .nav-pip { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
        .nav-badge { font-size: 9px; font-weight: 700; padding: 2px 5px; border-radius: 4px; color: #fff; }
        .nav-badge.hot { background: var(--short); }
        .nav-badge.ai { background: linear-gradient(135deg, var(--accent), var(--purple)); }
        .nav-badge.beta { background: var(--amber); }
        .nav-soon { font-size: 9px; color: var(--text-tertiary); background: var(--surface-hover); border: 1px solid var(--border); padding: 1px 5px; border-radius: 4px; }

        .sidebar-banner { margin: 8px 10px; background: var(--surface-hover); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 12px; display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
        .banner-icon { font-size: 20px; flex-shrink: 0; }
        .banner-title { font-size: 12px; font-weight: 700; color: var(--text); }
        .banner-desc { font-size: 10px; color: var(--text-tertiary); line-height: 1.4; margin-top: 2px; }
        .banner-btn { border: none; background: var(--accent); color: #fff; font-size: 11px; font-weight: 600; padding: 6px 10px; border-radius: 7px; white-space: nowrap; flex-shrink: 0; }

        .sidebar-bottom { padding: 10px 14px; border-top: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
        .scan-status { display: flex; align-items: center; gap: 8px; }
        .scan-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; flex-shrink: 0; }
        .scan-text { display: block; font-size: 10px; color: var(--text-secondary); font-weight: 500; }
        .scan-sub { display: block; font-size: 9px; color: var(--text-tertiary); }
        .sidebar-actions { display: flex; gap: 4px; }
        .theme-toggle { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); width: 28px; height: 28px; border-radius: 7px; font-size: 12px; display: flex; align-items: center; justify-content: center; }

        /* ── TOPBAR ── */
        .topbar { display: flex; align-items: center; justify-content: space-between; padding: 0 24px; height: 52px; background: var(--sidebar-bg); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 90; gap: 16px; }
        .topbar-left { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
        .burger { border: none; background: transparent; display: none; flex-direction: column; gap: 4px; padding: 4px; }
        .burger span { display: block; width: 20px; height: 2px; background: var(--text); border-radius: 2px; }
        .topbar-logo { font-size: 15px; font-weight: 900; letter-spacing: 0.06em; display: none; }
        .topbar-prices { display: flex; align-items: center; gap: 16px; flex: 1; justify-content: center; }
        .tp-item { display: flex; align-items: center; gap: 6px; }
        .tp-sym { font-size: 11px; color: var(--text-tertiary); font-weight: 600; }
        .tp-val { font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: var(--text); }
        .tp-chg { font-family: var(--font-mono); font-size: 11px; font-weight: 600; }
        .tp-chg.pos { color: var(--long); } .tp-chg.neg { color: var(--short); }
        .tp-div { width: 1px; height: 16px; background: var(--border); }
        .topbar-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .btn-create { border: 1px solid var(--border); background: var(--surface); color: var(--text); font-size: 13px; font-weight: 600; padding: 7px 14px; border-radius: 8px; transition: all 0.2s; white-space: nowrap; }
        .btn-create:hover { background: var(--surface-hover); }
        .btn-trial { background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; border: none; font-size: 13px; font-weight: 600; padding: 7px 14px; border-radius: 8px; box-shadow: 0 3px 12px rgba(77,140,245,0.35); transition: all 0.2s; white-space: nowrap; }
        .btn-trial:hover { opacity: 0.88; }
        .theme-toggle-sm { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); width: 32px; height: 32px; border-radius: 8px; font-size: 14px; }

        /* ── CONTENT ── */
        .sidebar-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 99; backdrop-filter: blur(4px); }
        .main-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; }
        .content { flex: 1; max-width: 960px; width: 100%; margin: 0 auto; padding: 24px 28px 80px; display: flex; flex-direction: column; gap: 0; }

        /* ── PAGE HEADER ── */
        .page-header { margin-bottom: 4px; }
        .page-title { font-size: 24px; font-weight: 800; color: var(--text); letter-spacing: -0.02em; display: flex; align-items: center; gap: 10px; }
        .beta-tag { font-size: 11px; font-weight: 700; background: var(--amber); color: #fff; padding: 2px 8px; border-radius: 5px; vertical-align: middle; }
        .hot-tag { font-size: 11px; font-weight: 700; background: var(--short); color: #fff; padding: 2px 8px; border-radius: 5px; vertical-align: middle; }
        .page-tabs-row { display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
        .page-tab { padding: 8px 0; margin-right: 24px; font-size: 14px; font-weight: 500; color: var(--text-tertiary); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; margin-bottom: -1px; }
        .page-tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
        .page-tab:hover:not(.active) { color: var(--text-secondary); }

        /* ── STEPS ── */
        .steps-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 24px; }
        .step-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px; box-shadow: var(--shadow-card); position: relative; transition: all 0.2s; }
        .step-card:hover { transform: translateY(-2px); }
        .step-card.done { border-color: rgba(0,229,168,0.3); }
        .step-card.active-step { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-soft), var(--shadow-card); }
        .step-icon-wrap { width: 34px; height: 34px; border-radius: 9px; background: var(--surface-hover); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; font-size: 15px; margin-bottom: 10px; color: var(--text-tertiary); }
        .step-icon-wrap.done { background: var(--long-soft); border-color: transparent; color: var(--long); }
        .step-icon-wrap.act { background: var(--accent-soft); border-color: transparent; color: var(--accent); animation: pa 2s infinite; }
        @keyframes pa { 0%,100%{box-shadow:0 0 0 0 rgba(77,140,245,0.3)} 50%{box-shadow:0 0 0 6px rgba(77,140,245,0)} }
        .step-title { font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .step-desc { font-size: 11px; color: var(--text-tertiary); line-height: 1.5; }
        .step-check { position: absolute; top: 12px; right: 12px; width: 18px; height: 18px; border-radius: 50%; background: var(--long); display: flex; align-items: center; justify-content: center; font-size: 10px; color: #fff; font-weight: 700; }
        .step-btn { margin-top: 10px; border: none; background: var(--accent); color: #fff; font-size: 11px; font-weight: 600; padding: 5px 10px; border-radius: 6px; }

        /* ── TOP STRATEGIES ── */
        .top-strategies { margin: 24px 0; }
        .ts-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
        .ts-title { font-size: 18px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .ts-sub { font-size: 12px; color: var(--text-tertiary); }
        .ts-more { border: 1px solid var(--border); background: transparent; color: var(--text-secondary); font-size: 13px; padding: 7px 14px; border-radius: 8px; transition: all 0.2s; white-space: nowrap; }
        .ts-more:hover { background: var(--surface-hover); color: var(--text); }
        .ts-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; }
        .ts-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; box-shadow: var(--shadow-card); transition: all 0.2s; }
        .ts-card:hover { border-color: var(--border-strong); transform: translateY(-2px); box-shadow: var(--shadow-lg); }
        .ts-card-header { padding: 16px 16px 0; }
        .ts-coin { display: flex; align-items: center; gap: 10px; }
        .ts-coin-icon { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--purple)); display: flex; align-items: center; justify-content: center; color: #fff; font-size: 16px; font-weight: 800; flex-shrink: 0; }
        .ts-symbol { font-family: var(--font-mono); font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .ts-tags { display: flex; gap: 4px; }
        .ts-tag { font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); }
        .ts-tag.long { background: var(--long-soft); color: var(--long); }
        .ts-tag.short { background: var(--short-soft); color: var(--short); }
        .ts-tag.neutral { background: var(--surface-hover); color: var(--text-secondary); }
        .ts-chart { padding: 8px 0; }
        .ts-roi-row { padding: 0 16px 8px; }
        .ts-roi-label { font-size: 10px; color: var(--text-tertiary); display: block; margin-bottom: 2px; }
        .ts-roi-val { font-family: var(--font-mono); font-size: 26px; font-weight: 800; display: block; }
        .ts-roi-val.pos { color: var(--long); } .ts-roi-val.neg { color: var(--short); }
        .ts-stats { display: flex; flex-direction: column; gap: 0; border-top: 1px solid var(--border); }
        .ts-stat { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; border-bottom: 1px solid var(--border); }
        .ts-stat:last-child { border-bottom: none; }
        .ts-stat-label { font-size: 11px; color: var(--text-secondary); }
        .ts-stat-val { font-family: var(--font-mono); font-size: 12px; font-weight: 600; color: var(--text); }
        .ts-stat-val.neg { color: var(--short); }
        .ts-btn { width: 100%; padding: 12px; background: var(--accent); color: #fff; border: none; font-size: 13px; font-weight: 600; transition: opacity 0.2s; }
        .ts-btn:hover { opacity: 0.85; }

        /* ── COMING SOON ── */
        .coming-soon-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 64px 32px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 14px; }
        .cs-icon { font-size: 48px; opacity: 0.3; }
        .cs-title { font-size: 22px; font-weight: 700; color: var(--text); }
        .cs-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; max-width: 400px; }
        .cs-badge { background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent-soft); padding: 6px 16px; border-radius: 20px; font-size: 13px; font-weight: 600; }

        /* ── MISC ── */
        .section { display: flex; flex-direction: column; gap: 14px; }
        .section-title { font-size: 10px; font-weight: 700; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.1em; display: flex; align-items: center; gap: 8px; }
        .section-title::after { content: ''; flex: 1; height: 1px; background: var(--border); }
        .signals-grid { display: grid; gap: 16px; }
        .error-banner { padding: 13px 18px; background: var(--short-soft); color: var(--short); border: 1px solid var(--short-soft); border-radius: var(--radius-md); font-size: 13px; margin-bottom: 20px; }

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
        .animate-in { animation: fadeIn 0.4s ease forwards; }

        @media (max-width: 1024px) { .ts-grid { grid-template-columns: repeat(2,1fr); } .steps-grid { grid-template-columns: repeat(2,1fr); } }
        @media (max-width: 768px) {
          .sidebar { position: fixed; left: -250px; top: 0; height: 100vh; transition: left 0.3s ease; z-index: 100; }
          .layout.sidebar-open .sidebar { left: 0; }
          .burger { display: flex; } .topbar-logo { display: block; }
          .topbar-prices { display: none; } .btn-create { display: none; }
          .content { padding: 16px 14px 80px; }
          .steps-grid { grid-template-columns: 1fr 1fr; }
          .ts-grid { grid-template-columns: 1fr; }
        }
        @media (max-width: 480px) { .steps-grid { grid-template-columns: 1fr 1fr; } .content { padding: 12px 10px 80px; } }
      `}</style>
    </div>
  )
}

function SignalSkeleton() {
  return (
    <div className="signal-skeleton animate-in">
      <div className="sk-bar skeleton" />
      <div className="sk-content">
        <div className="sk-row"><div className="sk-circle skeleton" /><div style={{flex:1,display:'flex',flexDirection:'column',gap:8}}><div className="sk-line skeleton" style={{width:'40%'}} /><div className="sk-line skeleton" style={{width:'25%',height:10}} /></div><div className="sk-line skeleton" style={{flex:'0 0 80px'}} /></div>
        <div className="sk-line skeleton" style={{height:8}} />
        <div className="sk-chart skeleton" />
        <div className="sk-row">{[1,2,3,4,5].map(i=><div key={i} className="sk-line skeleton" style={{height:40}} />)}</div>
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
