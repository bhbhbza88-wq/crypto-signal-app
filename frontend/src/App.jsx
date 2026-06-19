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

const TABS = [
  { key: 'overview', label: 'Обзор',   icon: '◈', hotkey: '1' },
  { key: 'market',   label: 'Рынок',   icon: '⬡', hotkey: '2' },
  { key: 'history',  label: 'История', icon: '≡', hotkey: '3' },
  { key: 'ai',       label: 'AI Чат',  icon: '✦', hotkey: '4', badge: 'AI' },
]

const STEPS = [
  { icon: '✓', title: 'Сканер запущен', desc: 'Анализирует 32 пары на Bybit', done: true },
  { icon: '◈', title: 'Ищем сигнал', desc: 'EMA · RSI · ADX · ATR', active: true },
  { icon: '⚡', title: 'Уровни выставлены', desc: 'TP1 · TP2 · TP3 · SL' },
  { icon: '✦', title: 'AI объясняет', desc: 'Причины входа и риски' },
]

function useLivePrices() {
  const [prices, setPrices] = useState(null)
  useEffect(() => {
    async function fetch_prices() {
      try {
        const [btcRes, ethRes] = await Promise.all([
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT'),
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=ETHUSDT'),
        ])
        const btc = (await btcRes.json())?.result?.list?.[0]
        const eth = (await ethRes.json())?.result?.list?.[0]
        if (btc && eth) setPrices({
          btc: { price: parseFloat(btc.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }), change: (parseFloat(btc.price24hPcnt)*100).toFixed(2), positive: parseFloat(btc.price24hPcnt) >= 0 },
          eth: { price: parseFloat(eth.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }), change: (parseFloat(eth.price24hPcnt)*100).toFixed(2), positive: parseFloat(eth.price24hPcnt) >= 0 },
        })
      } catch {}
    }
    fetch_prices()
    const id = setInterval(fetch_prices, 30000)
    return () => clearInterval(id)
  }, [])
  return prices
}

function requestPushPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }
}
function sendPushNotification(title, body) {
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification(title, { body, icon: '/favicon.ico' })
  }
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
  const prevSignalsRef = useRef([])
  const prices = useLivePrices()

  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('theme')
    if (saved) return saved === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      if (e.key === '1') setTab('overview')
      if (e.key === '2') setTab('market')
      if (e.key === '3') setTab('history')
      if (e.key === '4') setTab('ai')
      if (e.key === 'd') setDark(d => !d)
      if (e.key === 'Escape') setSidebarOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  useEffect(() => { requestPushPermission() }, [])

  const fetchCore = useCallback(async () => {
    try {
      const [signalsData, historyData, statsData] = await Promise.all([
        api.getSignals(), api.getHistory(50), api.getStats(),
      ])
      const prev = prevSignalsRef.current
      if (signalsData.length > 0 && prev.length === 0) {
        const s = signalsData[0]
        sendPushNotification(`🚨 NWICKI: ${s.signal} ${s.symbol}`, `Score ${s.score}/20 · Вход: ${s.entry?.toFixed(4)}`)
      }
      prevSignalsRef.current = signalsData
      setSignals(signalsData); setHistory(historyData); setStats(statsData); setError(null)
    } catch { setError('Нет связи с сервером.') }
    finally { setLoading(false) }
  }, [])

  const fetchMarket = useCallback(async () => {
    try { setMarket(await api.getMarket()) } catch {}
  }, [])

  useEffect(() => {
    fetchCore()
    const id = setInterval(fetchCore, POLL_INTERVAL)
    return () => clearInterval(id)
  }, [fetchCore])

  useEffect(() => {
    if (tab !== 'market') return
    fetchMarket()
    const id = setInterval(fetchMarket, MARKET_POLL_INTERVAL)
    return () => clearInterval(id)
  }, [tab, fetchMarket])

  return (
    <div className={`layout ${sidebarOpen ? 'sidebar-open' : ''}`}>

      {/* ── SIDEBAR ── */}
      <aside className="sidebar">
        {/* Logo */}
        <div className="sidebar-logo" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
          <div className="logo-icon"><span className="logo-n">N</span></div>
          <div className="logo-text-wrap">
            <span className="logo-name gradient-text">NWICKI</span>
            <span className="logo-sub">Crypto Scanner</span>
          </div>
        </div>

        {/* Live prices in sidebar */}
        {prices && (
          <div className="sidebar-prices">
            <div className="sidebar-price-item">
              <span className="sp-sym">₿</span>
              <span className="sp-val">${prices.btc.price}</span>
              <span className={`sp-chg ${prices.btc.positive ? 'pos' : 'neg'}`}>
                {prices.btc.positive ? '▲' : '▼'}{Math.abs(prices.btc.change)}%
              </span>
            </div>
            <div className="sidebar-price-divider" />
            <div className="sidebar-price-item">
              <span className="sp-sym">Ξ</span>
              <span className="sp-val">${prices.eth.price}</span>
              <span className={`sp-chg ${prices.eth.positive ? 'pos' : 'neg'}`}>
                {prices.eth.positive ? '▲' : '▼'}{Math.abs(prices.eth.change)}%
              </span>
            </div>
          </div>
        )}

        {/* Nav */}
        <nav className="sidebar-nav">
          {TABS.map((t, i) => (
            <button
              key={t.key}
              className={`nav-item ${tab === t.key ? 'active' : ''}`}
              style={{ animationDelay: `${i * 0.05}s` }}
              onClick={() => { setTab(t.key); setSidebarOpen(false) }}
            >
              <span className="nav-icon">{t.icon}</span>
              <span className="nav-label">{t.label}</span>
              <div className="nav-right">
                {t.badge && <span className="nav-badge">{t.badge}</span>}
                <span className="nav-hotkey">{t.hotkey}</span>
                {tab === t.key && <span className="nav-pip" />}
              </div>
            </button>
          ))}
        </nav>

        {/* Footer */}
        <div className="sidebar-bottom">
          <div className="scan-status">
            <span className="scan-dot" />
            <div>
              <span className="scan-text">Сканирую рынок</span>
              <span className="scan-sub">каждые 2 мин</span>
            </div>
          </div>
          <div className="sidebar-actions">
            <button className="theme-toggle" onClick={() => setDark(d => !d)} title="Тема (D)">
              {dark ? '☀' : '☾'}
            </button>
            {'Notification' in window && Notification.permission !== 'granted' && (
              <button className="notif-btn" onClick={requestPushPermission} title="Уведомления">🔔</button>
            )}
          </div>
        </div>

        <div className="hotkeys-hint">
          <span className="hotkey-badge"><kbd className="hotkey-key">1-4</kbd> разделы</span>
          <span className="hotkey-badge"><kbd className="hotkey-key">D</kbd> тема</span>
        </div>
      </aside>

      {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}

      {/* ── MAIN ── */}
      <div className="main-wrap">
        {/* Top bar with live prices */}
        <header className="topbar">
          <div className="topbar-left">
            <button className="burger" onClick={() => setSidebarOpen(o => !o)}>
              <span /><span /><span />
            </button>
            <span className="topbar-title gradient-text">NWICKI</span>
          </div>
          {prices && (
            <div className="topbar-prices">
              <div className="tp-item">
                <span className="tp-sym">BTC/USDT</span>
                <span className="tp-val">${prices.btc.price}</span>
                <span className={`tp-chg ${prices.btc.positive ? 'pos' : 'neg'}`}>
                  {prices.btc.positive ? '▲' : '▼'}{Math.abs(prices.btc.change)}%
                </span>
              </div>
              <div className="tp-divider" />
              <div className="tp-item">
                <span className="tp-sym">ETH/USDT</span>
                <span className="tp-val">${prices.eth.price}</span>
                <span className={`tp-chg ${prices.eth.positive ? 'pos' : 'neg'}`}>
                  {prices.eth.positive ? '▲' : '▼'}{Math.abs(prices.eth.change)}%
                </span>
              </div>
            </div>
          )}
          <button className="theme-toggle-mobile" onClick={() => setDark(d => !d)}>
            {dark ? '☀' : '☾'}
          </button>
        </header>

        <main className="content">
          {error && <div className="error-banner animate-in">{error}</div>}

          {tab === 'overview' && (
            <div className="animate-in">
              {/* Page title like 3Commas */}
              <div className="page-header">
                <h1 className="page-title">Dashboard</h1>
                <div className="page-tabs">
                  <span className="page-tab active">Обзор</span>
                  <span className="page-tab">Руководство</span>
                </div>
              </div>

              {/* Steps block like 3Commas */}
              <div className="steps-grid">
                {STEPS.map((s, i) => (
                  <div key={i} className={`step-card ${s.done ? 'done' : ''} ${s.active ? 'active-step' : ''}`}>
                    <div className={`step-icon ${s.done ? 'done' : s.active ? 'active-step-icon' : ''}`}>
                      {s.icon}
                    </div>
                    <div className="step-title">{s.title}</div>
                    <div className="step-desc">{s.desc}</div>
                    {s.done && <div className="step-check">✓</div>}
                  </div>
                ))}
              </div>

              <StatsHero stats={stats} loading={loading} />

              <section className="section" style={{ marginTop: 28 }}>
                <h2 className="section-title">Активный сигнал</h2>
                {loading ? <SignalSkeleton /> : signals.length === 0 ? <EmptySignal /> : (
                  <div className="signals-grid">
                    {signals.map((s) => <SignalCard key={s.symbol} signal={s} />)}
                  </div>
                )}
              </section>
            </div>
          )}

          {tab === 'market' && (
            <section className="section animate-in">
              <div className="page-header">
                <h1 className="page-title">Рынок</h1>
              </div>
              <MarketView market={market} />
            </section>
          )}

          {tab === 'history' && (
            <section className="section animate-in">
              <div className="page-header">
                <h1 className="page-title">История сделок</h1>
              </div>
              <HistoryTable history={history} />
            </section>
          )}

          {tab === 'ai' && (
            <section className="section animate-in">
              <div className="page-header">
                <h1 className="page-title">AI Ассистент</h1>
              </div>
              <AIChat signals={signals} stats={stats} market={market} />
            </section>
          )}
        </main>
      </div>

      <style>{`
        .layout { display: flex; min-height: 100vh; background: var(--bg); }

        /* ── SIDEBAR ── */
        .sidebar {
          width: 230px; flex-shrink: 0;
          background: var(--sidebar-bg);
          border-right: 1px solid var(--sidebar-border);
          box-shadow: var(--shadow-sidebar);
          display: flex; flex-direction: column;
          position: sticky; top: 0; height: 100vh;
          z-index: 100; transition: background 0.3s ease;
        }
        .sidebar-logo {
          display: flex; align-items: center; gap: 12px;
          padding: 20px 20px 16px;
          border-bottom: 1px solid var(--border);
        }
        .logo-icon {
          width: 36px; height: 36px;
          background: linear-gradient(135deg, var(--accent), var(--purple));
          border-radius: 10px; display: flex; align-items: center; justify-content: center;
          flex-shrink: 0; box-shadow: 0 4px 12px rgba(77,140,245,0.35);
        }
        .logo-n { color: #fff; font-size: 19px; font-weight: 900; letter-spacing: -0.03em; }
        .logo-text-wrap { display: flex; flex-direction: column; gap: 1px; }
        .logo-name { font-size: 16px; font-weight: 900; letter-spacing: 0.04em; line-height: 1; }
        .logo-sub { font-size: 9px; color: var(--text-tertiary); letter-spacing: 0.08em; text-transform: uppercase; }

        /* Live prices in sidebar */
        .sidebar-prices {
          padding: 10px 14px;
          border-bottom: 1px solid var(--border);
          display: flex; align-items: center; gap: 8px;
          background: var(--surface-hover);
        }
        .sidebar-price-item { display: flex; align-items: center; gap: 5px; flex: 1; }
        .sp-sym { font-size: 11px; color: var(--text-tertiary); font-weight: 600; }
        .sp-val { font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: var(--text); }
        .sp-chg { font-family: var(--font-mono); font-size: 10px; font-weight: 600; }
        .sp-chg.pos { color: var(--long); }
        .sp-chg.neg { color: var(--short); }
        .sidebar-price-divider { width: 1px; height: 14px; background: var(--border); flex-shrink: 0; }

        .sidebar-nav { flex: 1; display: flex; flex-direction: column; gap: 2px; padding: 12px 10px; overflow-y: auto; }
        .nav-item {
          display: flex; align-items: center; gap: 10px; padding: 10px 12px;
          border: none; background: transparent; color: var(--text-tertiary);
          font-size: 13.5px; font-weight: 500; border-radius: var(--radius-md);
          transition: all 0.2s; position: relative; text-align: left; width: 100%;
          animation: fadeIn 0.3s ease forwards; opacity: 0;
        }
        .nav-item:hover { background: var(--surface-hover); color: var(--text-secondary); transform: translateX(2px); }
        .nav-item.active { background: var(--sidebar-active); color: var(--sidebar-active-text); font-weight: 600; }
        .nav-icon { font-size: 15px; width: 20px; text-align: center; flex-shrink: 0; }
        .nav-label { flex: 1; }
        .nav-right { display: flex; align-items: center; gap: 6px; margin-left: auto; }
        .nav-pip { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 6px var(--accent); }
        .nav-badge { font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; }
        .nav-hotkey { font-size: 10px; color: var(--text-tertiary); font-family: var(--font-mono); background: var(--surface-hover); border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px; opacity: 0; transition: opacity 0.2s; }
        .nav-item:hover .nav-hotkey { opacity: 1; }

        .sidebar-bottom { padding: 12px 16px; border-top: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
        .scan-status { display: flex; align-items: center; gap: 8px; }
        .scan-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; flex-shrink: 0; }
        .scan-text { display: block; font-size: 11px; color: var(--text-secondary); font-weight: 500; }
        .scan-sub { display: block; font-size: 10px; color: var(--text-tertiary); }
        .sidebar-actions { display: flex; gap: 6px; }
        .theme-toggle, .notif-btn {
          border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary);
          width: 30px; height: 30px; border-radius: 8px; font-size: 13px;
          display: flex; align-items: center; justify-content: center; transition: all 0.2s; flex-shrink: 0;
        }
        .theme-toggle:hover, .notif-btn:hover { background: var(--surface-hover); color: var(--text); }
        .hotkeys-hint { padding: 8px 16px 14px; display: flex; gap: 10px; flex-wrap: wrap; }

        /* ── TOPBAR ── */
        .topbar {
          display: flex; align-items: center; justify-content: space-between;
          padding: 0 24px; height: 52px;
          background: var(--sidebar-bg); border-bottom: 1px solid var(--border);
          position: sticky; top: 0; z-index: 90;
          backdrop-filter: blur(12px);
        }
        .topbar-left { display: flex; align-items: center; gap: 12px; }
        .burger { border: none; background: transparent; display: none; flex-direction: column; gap: 5px; padding: 4px; }
        .burger span { display: block; width: 20px; height: 2px; background: var(--text); border-radius: 2px; }
        .topbar-title { font-size: 16px; font-weight: 900; letter-spacing: 0.06em; display: none; }

        .topbar-prices { display: flex; align-items: center; gap: 20px; }
        .tp-item { display: flex; align-items: center; gap: 8px; }
        .tp-sym { font-size: 11px; color: var(--text-tertiary); font-weight: 600; }
        .tp-val { font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: var(--text); }
        .tp-chg { font-family: var(--font-mono); font-size: 12px; font-weight: 600; }
        .tp-chg.pos { color: var(--long); }
        .tp-chg.neg { color: var(--short); }
        .tp-divider { width: 1px; height: 18px; background: var(--border); }

        .theme-toggle-mobile { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); width: 32px; height: 32px; border-radius: 8px; font-size: 15px; }

        /* ── PAGE HEADER ── */
        .page-header { margin-bottom: 20px; }
        .page-title { font-size: 26px; font-weight: 800; color: var(--text); letter-spacing: -0.02em; margin-bottom: 8px; }
        .page-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); }
        .page-tab { padding: 8px 0; margin-right: 24px; font-size: 14px; font-weight: 500; color: var(--text-tertiary); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; margin-bottom: -1px; }
        .page-tab.active { color: var(--text); border-bottom-color: var(--accent); font-weight: 600; }
        .page-tab:hover:not(.active) { color: var(--text-secondary); }

        /* ── STEPS GRID ── */
        .steps-grid {
          display: grid; grid-template-columns: repeat(4,1fr); gap: 12px;
          margin-bottom: 24px;
        }
        .step-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); padding: 20px 18px;
          box-shadow: var(--shadow-card); position: relative;
          transition: all 0.2s;
        }
        .step-card:hover { border-color: var(--border-strong); transform: translateY(-2px); }
        .step-card.done { border-color: var(--long-soft); background: var(--surface); }
        .step-card.active-step { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-soft), var(--shadow-card); }
        .step-icon {
          width: 36px; height: 36px; border-radius: 10px;
          background: var(--surface-hover); border: 1px solid var(--border);
          display: flex; align-items: center; justify-content: center;
          font-size: 16px; margin-bottom: 12px; color: var(--text-tertiary);
        }
        .step-icon.done { background: var(--long-soft); border-color: var(--long-soft); color: var(--long); }
        .step-icon.active-step-icon { background: var(--accent-soft); border-color: var(--accent-soft); color: var(--accent); animation: pulse-accent 2s infinite; }
        @keyframes pulse-accent {
          0%,100% { box-shadow: 0 0 0 0 rgba(77,140,245,0.3); }
          50% { box-shadow: 0 0 0 6px rgba(77,140,245,0); }
        }
        .step-title { font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .step-desc { font-size: 11px; color: var(--text-tertiary); line-height: 1.5; }
        .step-check { position: absolute; top: 14px; right: 14px; width: 20px; height: 20px; border-radius: 50%; background: var(--long); display: flex; align-items: center; justify-content: center; font-size: 11px; color: #fff; font-weight: 700; }

        /* ── MAIN CONTENT ── */
        .sidebar-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 99; backdrop-filter: blur(4px); }
        .main-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; }
        .content { flex: 1; max-width: 940px; width: 100%; margin: 0 auto; padding: 28px 28px 80px; display: flex; flex-direction: column; gap: 0; }
        .section { display: flex; flex-direction: column; gap: 14px; }
        .section-title { font-size: 10px; font-weight: 700; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.1em; display: flex; align-items: center; gap: 8px; }
        .section-title::after { content: ''; flex: 1; height: 1px; background: var(--border); }
        .signals-grid { display: grid; gap: 16px; }
        .error-banner { padding: 13px 18px; background: var(--short-soft); color: var(--short); border: 1px solid var(--short-soft); border-radius: var(--radius-md); font-size: 13px; margin-bottom: 20px; }

        /* ── SKELETON & EMPTY ── */
        .signal-skeleton { border-radius: var(--radius-lg); overflow: hidden; background: var(--surface); border: 1px solid var(--border); }
        .sk-bar { height: 4px; }
        .sk-content { padding: 22px; display: flex; flex-direction: column; gap: 14px; }
        .sk-row { display: flex; gap: 12px; align-items: center; }
        .sk-circle { width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0; }
        .sk-line { height: 14px; border-radius: 6px; flex: 1; }
        .sk-chart { height: 180px; border-radius: 8px; }
        .empty-signal { padding: 48px 32px; text-align: center; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); display: flex; flex-direction: column; align-items: center; gap: 14px; }
        .empty-icon { font-size: 40px; opacity: 0.4; }
        .empty-title { font-size: 16px; font-weight: 600; color: var(--text-secondary); }
        .empty-desc { font-size: 13px; color: var(--text-tertiary); line-height: 1.6; max-width: 320px; }
        .empty-pulse { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--long); background: var(--long-soft); padding: 8px 16px; border-radius: 20px; }

        @keyframes pulse {
          0%   { box-shadow: 0 0 0 0 rgba(0,229,168,0.4); }
          70%  { box-shadow: 0 0 0 8px rgba(0,229,168,0); }
          100% { box-shadow: 0 0 0 0 rgba(0,229,168,0); }
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

        @media (max-width: 768px) {
          .sidebar { position: fixed; left: -250px; top: 0; height: 100vh; transition: left 0.3s ease; z-index: 100; }
          .layout.sidebar-open .sidebar { left: 0; }
          .burger { display: flex; }
          .topbar-title { display: block; }
          .topbar-prices { display: none; }
          .content { padding: 20px 16px 80px; }
          .steps-grid { grid-template-columns: repeat(2,1fr); }
        }
        @media (max-width: 480px) {
          .steps-grid { grid-template-columns: 1fr 1fr; }
          .content { padding: 16px 12px 80px; }
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
        <div className="sk-row">
          <div className="sk-circle skeleton" />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div className="sk-line skeleton" style={{ width: '40%' }} />
            <div className="sk-line skeleton" style={{ width: '25%', height: 10 }} />
          </div>
          <div className="sk-line skeleton" style={{ flex: '0 0 80px' }} />
        </div>
        <div className="sk-line skeleton" style={{ height: 8 }} />
        <div className="sk-chart skeleton" />
        <div className="sk-row">
          {[1,2,3,4,5].map(i => <div key={i} className="sk-line skeleton" style={{ height: 40 }} />)}
        </div>
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
      <div className="empty-pulse">
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--long)', animation: 'pulse 2s infinite', display: 'inline-block' }} />
        Сканирование каждые 2 минуты
      </div>
    </div>
  )
}
