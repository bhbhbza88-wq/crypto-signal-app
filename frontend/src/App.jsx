import { useEffect, useState, useCallback, useRef } from 'react'
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

// Custom Cursor
function CustomCursor() {
  const dotRef  = useRef(null)
  const ringRef = useRef(null)

  useEffect(() => {
    const dot  = dotRef.current
    const ring = ringRef.current
    if (!dot || !ring) return

    let mouseX = 0, mouseY = 0
    let ringX = 0, ringY = 0

    const move = (e) => {
      mouseX = e.clientX
      mouseY = e.clientY
      dot.style.left = mouseX + 'px'
      dot.style.top  = mouseY + 'px'
    }

    const hover = () => { dot.classList.add('hovering'); ring.classList.add('hovering') }
    const leave = () => { dot.classList.remove('hovering'); ring.classList.remove('hovering') }

    let raf
    const animate = () => {
      ringX += (mouseX - ringX) * 0.12
      ringY += (mouseY - ringY) * 0.12
      ring.style.left = ringX + 'px'
      ring.style.top  = ringY + 'px'
      raf = requestAnimationFrame(animate)
    }

    document.addEventListener('mousemove', move)
    document.querySelectorAll('button, a, input, [role="button"]').forEach(el => {
      el.addEventListener('mouseenter', hover)
      el.addEventListener('mouseleave', leave)
    })
    animate()

    return () => {
      document.removeEventListener('mousemove', move)
      cancelAnimationFrame(raf)
    }
  }, [])

  return (
    <>
      <div className="cursor-dot"  ref={dotRef} />
      <div className="cursor-ring" ref={ringRef} />
    </>
  )
}

// Push notifications
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
  const [tab, setTab]             = useState('overview')
  const [signals, setSignals]     = useState([])
  const [history, setHistory]     = useState([])
  const [stats, setStats]         = useState(null)
  const [market, setMarket]       = useState(null)
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const prevSignalsRef = useRef([])

  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('theme')
    if (saved) return saved === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  // Hotkeys
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

  // Push permission on load
  useEffect(() => { requestPushPermission() }, [])

  const fetchCore = useCallback(async () => {
    try {
      const [signalsData, historyData, statsData] = await Promise.all([
        api.getSignals(),
        api.getHistory(50),
        api.getStats(),
      ])
      // Push notification when new signal appears
      const prev = prevSignalsRef.current
      if (signalsData.length > prev.length && prev.length === 0 && signalsData.length > 0) {
        const s = signalsData[0]
        sendPushNotification(
          `🚨 NWICKI: Новый сигнал ${s.signal}`,
          `${s.symbol} · Score ${s.score}/20 · Вход: ${s.entry?.toFixed(4)}`
        )
      }
      prevSignalsRef.current = signalsData
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
    <>
      <CustomCursor />
      <div className={`layout ${sidebarOpen ? 'sidebar-open' : ''}`}>

        <aside className="sidebar animate-in-left">
          <div className="sidebar-logo">
            <div className="logo-icon">
              <span className="logo-n">N</span>
            </div>
            <div className="logo-text-wrap">
              <span className="logo-name gradient-text">NWICKI</span>
              <span className="logo-sub">Crypto Scanner</span>
            </div>
          </div>

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

          <div className="sidebar-bottom">
            <div className="scan-status">
              <span className="scan-dot" />
              <div>
                <span className="scan-text">Сканирую рынок</span>
                <span className="scan-sub">каждые 2 мин</span>
              </div>
            </div>
            <div className="sidebar-actions">
              <button
                className="theme-toggle"
                onClick={() => setDark(d => !d)}
                title="Сменить тему (D)"
              >
                {dark ? '☀' : '☾'}
              </button>
              {'Notification' in window && Notification.permission !== 'granted' && (
                <button
                  className="notif-btn"
                  onClick={requestPushPermission}
                  title="Включить уведомления"
                >
                  🔔
                </button>
              )}
            </div>
          </div>

          {/* Hotkeys hint */}
          <div className="hotkeys-hint">
            <span className="hotkey-badge">
              <kbd className="hotkey-key">1-4</kbd> разделы
            </span>
            <span className="hotkey-badge">
              <kbd className="hotkey-key">D</kbd> тема
            </span>
          </div>
        </aside>

        {sidebarOpen && (
          <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
        )}

        <div className="main-wrap">
          <header className="topbar glass">
            <button className="burger" onClick={() => setSidebarOpen(o => !o)}>
              <span /><span /><span />
            </button>
            <span className="topbar-title gradient-text">NWICKI</span>
            <button className="theme-toggle-mobile" onClick={() => setDark(d => !d)}>
              {dark ? '☀' : '☾'}
            </button>
          </header>

          <main className="content">
            {error && <div className="error-banner animate-in">{error}</div>}

            {tab === 'overview' && (
              <div className="animate-in">
                <StatsHero stats={stats} loading={loading} />
                <section className="section" style={{ marginTop: 28 }}>
                  <h2 className="section-title">Активный сигнал</h2>
                  {loading ? (
                    <SignalSkeleton />
                  ) : signals.length === 0 ? (
                    <EmptySignal />
                  ) : (
                    <div className="signals-grid">
                      {signals.map((s) => (
                        <SignalCard key={s.symbol} signal={s} />
                      ))}
                    </div>
                  )}
                </section>
              </div>
            )}

            {tab === 'market' && (
              <section className="section animate-in">
                <h2 className="section-title">Состояние рынка</h2>
                <MarketView market={market} />
              </section>
            )}

            {tab === 'history' && (
              <section className="section animate-in">
                <h2 className="section-title">История сделок</h2>
                <HistoryTable history={history} />
              </section>
            )}

            {tab === 'ai' && (
              <section className="section animate-in">
                <h2 className="section-title">AI Ассистент</h2>
                <AIChat signals={signals} stats={stats} market={market} />
              </section>
            )}
          </main>
        </div>
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
          z-index: 100;
          transition: background 0.3s ease, border-color 0.3s ease;
        }

        .sidebar-logo {
          display: flex; align-items: center; gap: 12px;
          padding: 26px 20px 22px;
          border-bottom: 1px solid var(--border);
          position: relative;
          overflow: hidden;
        }
        .sidebar-logo::after {
          content: '';
          position: absolute; top: 0; left: 0; right: 0; bottom: 0;
          background: linear-gradient(135deg, var(--accent-soft), transparent);
          opacity: 0.3; pointer-events: none;
        }
        .logo-icon {
          width: 40px; height: 40px;
          background: linear-gradient(135deg, var(--accent), var(--purple));
          border-radius: 12px;
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0;
          box-shadow: 0 4px 16px rgba(77,140,245,0.4);
          position: relative; z-index: 1;
        }
        .logo-n { color: #fff; font-size: 21px; font-weight: 900; letter-spacing: -0.04em; }
        .logo-text-wrap { display: flex; flex-direction: column; gap: 2px; position: relative; z-index: 1; }
        .logo-name { font-size: 18px; font-weight: 900; letter-spacing: 0.06em; line-height: 1; }
        .logo-sub { font-size: 9px; color: var(--text-tertiary); letter-spacing: 0.1em; text-transform: uppercase; }

        .sidebar-nav {
          flex: 1; display: flex; flex-direction: column;
          gap: 2px; padding: 14px 10px;
          overflow-y: auto;
        }
        .nav-item {
          display: flex; align-items: center; gap: 10px;
          padding: 10px 12px; border: none;
          background: transparent;
          color: var(--text-tertiary); font-size: 13.5px; font-weight: 500;
          border-radius: var(--radius-md);
          transition: all 0.2s ease;
          position: relative; text-align: left; width: 100%;
          animation: fadeIn 0.3s ease forwards; opacity: 0;
        }
        .nav-item:hover {
          background: var(--surface-hover);
          color: var(--text-secondary);
          transform: translateX(2px);
        }
        .nav-item.active {
          background: var(--sidebar-active);
          color: var(--sidebar-active-text);
          font-weight: 600;
          box-shadow: inset 0 0 0 1px var(--accent-soft);
        }
        .nav-icon { font-size: 15px; width: 20px; text-align: center; flex-shrink: 0; }
        .nav-label { flex: 1; }
        .nav-right { display: flex; align-items: center; gap: 6px; margin-left: auto; }
        .nav-pip { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 6px var(--accent); }
        .nav-badge {
          font-size: 9px; font-weight: 700; padding: 2px 6px;
          border-radius: 4px;
          background: linear-gradient(135deg, var(--accent), var(--purple));
          color: #fff; letter-spacing: 0.05em;
        }
        .nav-hotkey {
          font-size: 10px; color: var(--text-tertiary);
          font-family: var(--font-mono);
          background: var(--surface-hover); border: 1px solid var(--border);
          border-radius: 4px; padding: 1px 5px;
          opacity: 0; transition: opacity 0.2s;
        }
        .nav-item:hover .nav-hotkey { opacity: 1; }

        .sidebar-bottom {
          padding: 14px 16px;
          border-top: 1px solid var(--border);
          display: flex; align-items: center; justify-content: space-between;
        }
        .scan-status { display: flex; align-items: center; gap: 10px; }
        .scan-dot {
          width: 8px; height: 8px; border-radius: 50%;
          background: var(--long); animation: pulse 2s infinite; flex-shrink: 0;
        }
        .scan-text { display: block; font-size: 11px; color: var(--text-secondary); font-weight: 500; }
        .scan-sub { display: block; font-size: 10px; color: var(--text-tertiary); }
        .sidebar-actions { display: flex; gap: 6px; }
        .theme-toggle, .notif-btn {
          border: 1px solid var(--border); background: var(--surface);
          color: var(--text-secondary); width: 32px; height: 32px;
          border-radius: 9px; font-size: 14px;
          display: flex; align-items: center; justify-content: center;
          transition: all 0.2s; flex-shrink: 0;
        }
        .theme-toggle:hover, .notif-btn:hover {
          background: var(--surface-hover); color: var(--text);
          border-color: var(--border-strong);
          transform: scale(1.05);
        }

        .hotkeys-hint {
          padding: 10px 16px 16px;
          display: flex; gap: 12px; flex-wrap: wrap;
        }

        /* ── TOPBAR ── */
        .topbar {
          display: none; align-items: center; justify-content: space-between;
          padding: 14px 18px;
          border-bottom: 1px solid var(--border);
          position: sticky; top: 0; z-index: 90;
        }
        .burger { border: none; background: transparent; display: flex; flex-direction: column; gap: 5px; padding: 4px; }
        .burger span { display: block; width: 22px; height: 2px; background: var(--text); border-radius: 2px; transition: background 0.2s; }
        .topbar-title { font-size: 18px; font-weight: 900; letter-spacing: 0.06em; }
        .theme-toggle-mobile {
          border: 1px solid var(--border); background: var(--surface);
          color: var(--text-secondary); width: 34px; height: 34px; border-radius: 9px; font-size: 16px;
        }

        .sidebar-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 99; backdrop-filter: blur(4px); }

        /* ── MAIN ── */
        .main-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; }
        .content {
          flex: 1; max-width: 920px; width: 100%;
          margin: 0 auto; padding: 32px 28px 80px;
          display: flex; flex-direction: column; gap: 0;
        }
        .section { display: flex; flex-direction: column; gap: 14px; }
        .section-title {
          font-size: 10px; font-weight: 700; color: var(--text-tertiary);
          text-transform: uppercase; letter-spacing: 0.1em;
          display: flex; align-items: center; gap: 8px;
        }
        .section-title::after {
          content: ''; flex: 1; height: 1px; background: var(--border);
        }
        .signals-grid { display: grid; gap: 16px; }
        .error-banner {
          padding: 13px 18px; background: var(--short-soft); color: var(--short);
          border: 1px solid var(--short-soft); border-radius: var(--radius-md);
          font-size: 13px; margin-bottom: 20px;
        }

        /* ── SKELETON ── */
        .signal-skeleton {
          border-radius: var(--radius-lg); overflow: hidden;
          background: var(--surface); border: 1px solid var(--border);
        }
        .sk-bar { height: 4px; }
        .sk-content { padding: 22px; display: flex; flex-direction: column; gap: 14px; }
        .sk-row { display: flex; gap: 12px; align-items: center; }
        .sk-circle { width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0; }
        .sk-line { height: 14px; border-radius: 6px; flex: 1; }
        .sk-line.short { flex: 0 0 80px; }
        .sk-chart { height: 180px; border-radius: 8px; }

        /* ── EMPTY STATE ── */
        .empty-signal {
          padding: 48px 32px; text-align: center;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); display: flex; flex-direction: column;
          align-items: center; gap: 14px;
        }
        .empty-icon { font-size: 40px; opacity: 0.4; }
        .empty-title { font-size: 16px; font-weight: 600; color: var(--text-secondary); }
        .empty-desc { font-size: 13px; color: var(--text-tertiary); line-height: 1.6; max-width: 320px; }
        .empty-pulse {
          display: flex; align-items: center; gap: 8px;
          font-size: 12px; color: var(--long);
          background: var(--long-soft); padding: 8px 16px; border-radius: 20px;
        }

        @media (max-width: 768px) {
          .sidebar { position: fixed; left: -250px; top: 0; height: 100vh; transition: left 0.3s ease; z-index: 100; }
          .layout.sidebar-open .sidebar { left: 0; }
          .topbar { display: flex; }
          .content { padding: 20px 16px 80px; }
          .cursor-dot, .cursor-ring { display: none; }
          body { cursor: auto; }
          button, a { cursor: auto; }
        }
        @media (max-width: 480px) {
          .content { padding: 16px 12px 80px; }
        }
      `}</style>
    </>
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
          <div className="sk-line skeleton short" />
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
      <div className="empty-desc">
        Сканер анализирует 32 пары на Bybit. Когда найдёт точку входа — сигнал появится здесь автоматически.
      </div>
      <div className="empty-pulse">
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--long)', animation: 'pulse 2s infinite', display: 'inline-block' }} />
        Сканирование каждые 2 минуты
      </div>
    </div>
  )
}
