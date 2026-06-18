import { useEffect, useState, useCallback } from 'react'
import { api } from './api'
import StatsHero from './StatsHero'
import SignalCard from './SignalCard'
import HistoryTable from './HistoryTable'
import MarketView from './MarketView'

const POLL_INTERVAL = 15000
const MARKET_POLL_INTERVAL = 60000

const TABS = [
  { key: 'overview', label: 'Обзор',   icon: '◈' },
  { key: 'market',   label: 'Рынок',   icon: '⬡' },
  { key: 'history',  label: 'История', icon: '≡' },
]

export default function App() {
  const [tab, setTab]             = useState('overview')
  const [signals, setSignals]     = useState([])
  const [history, setHistory]     = useState([])
  const [stats, setStats]         = useState(null)
  const [market, setMarket]       = useState(null)
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('theme')
    if (saved) return saved === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  const fetchCore = useCallback(async () => {
    try {
      const [signalsData, historyData, statsData] = await Promise.all([
        api.getSignals(),
        api.getHistory(50),
        api.getStats(),
      ])
      setSignals(signalsData)
      setHistory(historyData)
      setStats(statsData)
      setError(null)
    } catch {
      setError('Нет связи с сервером.')
    } finally {
      setLoading(false)
    }
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

      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon">
            <span className="logo-n">N</span>
          </div>
          <div className="logo-text-wrap">
            <span className="logo-name">NWICKI</span>
            <span className="logo-sub">Crypto Scanner</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`nav-item ${tab === t.key ? 'active' : ''}`}
              onClick={() => { setTab(t.key); setSidebarOpen(false) }}
            >
              <span className="nav-icon">{t.icon}</span>
              <span className="nav-label">{t.label}</span>
              {tab === t.key && <span className="nav-pip" />}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="scan-badge">
            <span className="scan-dot" />
            <span className="scan-text">Сканирую рынок</span>
          </div>
          <button
            className="theme-toggle"
            onClick={() => setDark(d => !d)}
            title={dark ? 'Светлая тема' : 'Тёмная тема'}
          >
            {dark ? '☀' : '☾'}
          </button>
        </div>
      </aside>

      {sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      <div className="main-wrap">
        <header className="topbar">
          <button className="burger" onClick={() => setSidebarOpen(o => !o)}>
            <span /><span /><span />
          </button>
          <span className="topbar-title">NWICKI</span>
          <button className="theme-toggle-mobile" onClick={() => setDark(d => !d)}>
            {dark ? '☀' : '☾'}
          </button>
        </header>

        <main className="content">
          {error && <div className="error-banner">{error}</div>}

          {tab === 'overview' && (
            <>
              <StatsHero stats={stats} />
              <section className="section">
                <h2 className="section-title">Активный сигнал</h2>
                {loading ? (
                  <div className="placeholder">Загрузка...</div>
                ) : signals.length === 0 ? (
                  <div className="placeholder">
                    Открытых позиций нет. Сканер ищет точку входа каждые 2 минуты.
                  </div>
                ) : (
                  <div className="signals-grid">
                    {signals.map((s) => (
                      <SignalCard key={s.symbol} signal={s} />
                    ))}
                  </div>
                )}
              </section>
            </>
          )}

          {tab === 'market' && (
            <section className="section">
              <h2 className="section-title">Состояние рынка</h2>
              <MarketView market={market} />
            </section>
          )}

          {tab === 'history' && (
            <section className="section">
              <h2 className="section-title">История сделок</h2>
              <HistoryTable history={history} />
            </section>
          )}
        </main>
      </div>

      <style>{`
        .layout { display: flex; min-height: 100vh; background: var(--bg); }

        .sidebar {
          width: 220px;
          flex-shrink: 0;
          background: var(--sidebar-bg);
          border-right: 1px solid var(--sidebar-border);
          box-shadow: var(--shadow-sidebar);
          display: flex;
          flex-direction: column;
          position: sticky;
          top: 0;
          height: 100vh;
          z-index: 100;
          transition: background 0.2s ease;
        }

        .sidebar-logo {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 24px 20px 20px;
          border-bottom: 1px solid var(--border);
        }
        .logo-icon {
          width: 38px; height: 38px;
          background: linear-gradient(135deg, var(--accent) 0%, #7c3aed 100%);
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          box-shadow: 0 4px 12px rgba(75,140,245,0.35);
        }
        .logo-n {
          color: #fff;
          font-size: 20px;
          font-weight: 800;
          letter-spacing: -0.03em;
        }
        .logo-text-wrap { display: flex; flex-direction: column; gap: 1px; }
        .logo-name {
          font-size: 17px;
          font-weight: 800;
          color: var(--text);
          letter-spacing: 0.04em;
          line-height: 1;
        }
        .logo-sub {
          font-size: 10px;
          color: var(--text-tertiary);
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }

        .sidebar-nav {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 4px;
          padding: 16px 12px;
        }
        .nav-item {
          display: flex;
          align-items: center;
          gap: 11px;
          padding: 11px 12px;
          border: none;
          background: transparent;
          color: var(--text-tertiary);
          font-size: 14px;
          font-weight: 500;
          border-radius: var(--radius-md);
          transition: background 0.15s, color 0.15s;
          position: relative;
          text-align: left;
          width: 100%;
        }
        .nav-item:hover { background: var(--surface-hover); color: var(--text-secondary); }
        .nav-item.active { background: var(--sidebar-active); color: var(--sidebar-active-text); font-weight: 600; }
        .nav-icon { font-size: 16px; width: 20px; text-align: center; flex-shrink: 0; }
        .nav-pip {
          position: absolute; right: 12px;
          width: 6px; height: 6px;
          border-radius: 50%;
          background: var(--accent);
        }

        .sidebar-footer {
          padding: 16px 16px 24px;
          border-top: 1px solid var(--border);
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
        }
        .scan-badge { display: flex; align-items: center; gap: 7px; }
        .scan-dot {
          width: 7px; height: 7px;
          border-radius: 50%;
          background: var(--long);
          animation: pulse 2s infinite;
        }
        @keyframes pulse {
          0%   { box-shadow: 0 0 0 0 rgba(0,201,150,0.4); }
          70%  { box-shadow: 0 0 0 6px rgba(0,201,150,0); }
          100% { box-shadow: 0 0 0 0 rgba(0,201,150,0); }
        }
        .scan-text { font-size: 11px; color: var(--text-tertiary); }
        .theme-toggle {
          border: 1px solid var(--border);
          background: var(--surface);
          color: var(--text-secondary);
          width: 32px; height: 32px;
          border-radius: 8px;
          font-size: 15px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.15s;
          flex-shrink: 0;
        }
        .theme-toggle:hover { background: var(--surface-hover); color: var(--text); }

        .topbar {
          display: none;
          align-items: center;
          justify-content: space-between;
          padding: 14px 18px;
          background: var(--sidebar-bg);
          border-bottom: 1px solid var(--border);
          position: sticky;
          top: 0;
          z-index: 90;
        }
        .burger {
          border: none; background: transparent;
          display: flex; flex-direction: column; gap: 5px; padding: 4px;
        }
        .burger span { display: block; width: 22px; height: 2px; background: var(--text); border-radius: 2px; }
        .topbar-title { font-size: 17px; font-weight: 800; color: var(--text); letter-spacing: 0.04em; }
        .theme-toggle-mobile {
          border: 1px solid var(--border); background: var(--surface);
          color: var(--text-secondary); width: 34px; height: 34px;
          border-radius: 8px; font-size: 16px;
        }

        .sidebar-overlay {
          position: fixed; inset: 0;
          background: rgba(0,0,0,0.5); z-index: 99;
        }

        .main-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; }
        .content {
          flex: 1; max-width: 900px; width: 100%;
          margin: 0 auto; padding: 32px 28px 64px;
          display: flex; flex-direction: column; gap: 28px;
        }
        .section { display: flex; flex-direction: column; gap: 14px; }
        .section-title {
          font-size: 11px; font-weight: 700;
          color: var(--text-tertiary);
          text-transform: uppercase; letter-spacing: 0.08em;
        }
        .signals-grid { display: grid; gap: 14px; }
        .placeholder {
          padding: 36px; text-align: center;
          color: var(--text-tertiary); font-size: 13px;
          background: var(--surface);
          border: 1px dashed var(--border-strong);
          border-radius: var(--radius-lg); line-height: 1.6;
        }
        .error-banner {
          padding: 13px 18px;
          background: var(--short-soft); color: var(--short);
          border: 1px solid var(--short-soft);
          border-radius: var(--radius-md); font-size: 13px;
        }

        @media (max-width: 768px) {
          .sidebar {
            position: fixed; left: -240px; top: 0;
            height: 100vh; transition: left 0.25s ease; z-index: 100;
          }
          .layout.sidebar-open .sidebar { left: 0; }
          .topbar { display: flex; }
          .content { padding: 20px 16px 64px; }
        }
      `}</style>
    </div>
  )
}
