import { useEffect, useState, useCallback } from 'react'
import { api } from './api'
import StatsHero from './StatsHero'
import SignalCard from './SignalCard'
import HistoryTable from './HistoryTable'
import MarketView from './MarketView'

const POLL_INTERVAL = 15000
const MARKET_POLL_INTERVAL = 60000

const TABS = [
  { key: 'overview', label: 'Обзор' },
  { key: 'market', label: 'Рынок' },
  { key: 'history', label: 'История' },
]

export default function App() {
  const [tab, setTab] = useState('overview')
  const [signals, setSignals] = useState([])
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)
  const [market, setMarket] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

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
    } catch (e) {
      setError('Не удаётся подключиться к backend. Запущен ли сервер на localhost:8000?')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchMarket = useCallback(async () => {
    try {
      const marketData = await api.getMarket()
      setMarket(marketData)
    } catch (e) {
      // ошибка рынка не блокирует остальной интерфейс
    }
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
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark" />
          <span className="brand-name">Signal Desk</span>
        </div>
        <div className="scan-status">
          <span className="scan-dot" />
          <span>Сканирую рынок</span>
        </div>
      </header>

      <nav className="tab-nav">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`tab-btn ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="app-main">
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
                  Сейчас открытых позиций нет. Сканер ищет точку входа каждые 5 минут.
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

      <style>{`
        .app {
          min-height: 100vh;
          max-width: 880px;
          margin: 0 auto;
          padding: 0 20px 64px;
        }
        .app-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 28px 0 18px;
          flex-wrap: wrap;
          gap: 12px;
        }
        .brand { display: flex; align-items: center; gap: 9px; }
        .brand-mark {
          width: 9px; height: 9px;
          background: var(--long);
          border-radius: 2px;
          transform: rotate(45deg);
        }
        .brand-name {
          font-size: 17px;
          font-weight: 700;
          color: var(--text);
          letter-spacing: -0.01em;
        }
        .scan-status {
          display: flex;
          align-items: center;
          gap: 7px;
          font-size: 12px;
          color: var(--text-tertiary);
        }
        .scan-dot {
          width: 6px; height: 6px;
          border-radius: 50%;
          background: var(--long);
          box-shadow: 0 0 0 0 var(--long-soft);
          animation: pulse 2s infinite;
        }
        @keyframes pulse {
          0% { box-shadow: 0 0 0 0 rgba(31,157,107,0.25); }
          70% { box-shadow: 0 0 0 5px rgba(31,157,107,0); }
          100% { box-shadow: 0 0 0 0 rgba(31,157,107,0); }
        }

        .tab-nav {
          display: flex;
          gap: 4px;
          padding-bottom: 20px;
          border-bottom: 1px solid var(--border);
          margin-bottom: 24px;
        }
        .tab-btn {
          border: none;
          background: transparent;
          color: var(--text-tertiary);
          font-size: 14px;
          font-weight: 500;
          padding: 8px 4px;
          position: relative;
        }
        .tab-btn + .tab-btn { margin-left: 18px; }
        .tab-btn.active { color: var(--text); font-weight: 600; }
        .tab-btn.active::after {
          content: '';
          position: absolute;
          left: 0; right: 0; bottom: -21px;
          height: 2px;
          background: var(--text);
        }
        .tab-btn:hover:not(.active) { color: var(--text-secondary); }

        .app-main {
          display: flex;
          flex-direction: column;
          gap: 28px;
        }
        .section { display: flex; flex-direction: column; gap: 12px; }
        .section-title {
          font-size: 13px;
          font-weight: 600;
          color: var(--text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .signals-grid {
          display: grid;
          gap: 14px;
        }
        .placeholder {
          padding: 30px;
          text-align: center;
          color: var(--text-tertiary);
          font-size: 13px;
          background: var(--surface);
          border: 1px dashed var(--border-strong);
          border-radius: var(--radius-lg);
        }
        .error-banner {
          padding: 13px 18px;
          background: var(--short-soft);
          color: var(--short);
          border: 1px solid #f3cccc;
          border-radius: var(--radius-md);
          font-size: 13px;
        }
      `}</style>
    </div>
  )
}
