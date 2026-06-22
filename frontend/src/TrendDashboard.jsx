import { useEffect, useState, useCallback } from 'react'
import { api } from './api'

function SignalRow({ s }) {
  return (
    <div className={`tr-sig-row ${s.in_trend ? 'up' : 'down'}`}>
      <span className={`tr-sig-dot ${s.in_trend ? 'up' : 'down'}`} />
      <span className="tr-sig-sym">{s.symbol.replace('/USDT', '')}</span>
      <span className="tr-sig-status">{s.in_trend ? 'В РЫНКЕ' : 'В КЭШЕ'}</span>
      <span className="tr-sig-price">{s.close}</span>
      <span className={`tr-sig-dist ${s.distance_pct >= 0 ? 'pos' : 'neg'}`}>
        EMA{s.distance_pct >= 0 ? '50>200' : '50<200'}: {s.distance_pct > 0 ? '+' : ''}{s.distance_pct}%
      </span>
    </div>
  )
}

const PHASE_LABEL = { UPTREND: 'АПТРЕНД', DOWNTREND: 'ДАУНТРЕНД', SIDEWAYS: 'БОКОВИК' }
const PHASE_CLASS = { UPTREND: 'up', DOWNTREND: 'down', SIDEWAYS: 'side' }

function MarketPhaseBanner({ phase }) {
  if (!phase || phase.error) return null
  const cls = PHASE_CLASS[phase.phase] || 'side'
  return (
    <div className={`mp-banner ${cls}`}>
      <div className="mp-left">
        <span className="mp-dot" />
        <div>
          <div className="mp-title">Фаза рынка: {PHASE_LABEL[phase.phase] || phase.phase}
            <span className="mp-score">risk-on {phase.risk_on_score}/4</span>
          </div>
          <div className="mp-sub">
            Монет в аптренде: {phase.breadth_pct}% · моментум 60д: {phase.momentum_60d_pct > 0 ? '+' : ''}{phase.momentum_60d_pct}% · BTC {phase.btc_close}
          </div>
        </div>
      </div>
      <div className="mp-note">ℹ️ Консенсус 4 сигналов + подтверждение 5д · информационно, не управляет деньгами</div>
      <style>{`
        .mp-banner { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 18px; border-radius: var(--radius-md); margin-bottom: 18px; border: 1px solid var(--border); background: var(--surface); }
        .mp-banner.up { border-color: var(--long); background: var(--long-soft); }
        .mp-banner.down { border-color: var(--short); background: var(--short-soft); }
        .mp-banner.side { border-color: var(--amber); background: var(--amber-soft); }
        .mp-left { display: flex; align-items: center; gap: 10px; }
        .mp-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
        .mp-banner.up .mp-dot { background: var(--long); }
        .mp-banner.down .mp-dot { background: var(--short); }
        .mp-banner.side .mp-dot { background: var(--amber); }
        .mp-title { font-weight: 800; font-size: 14px; color: var(--text); display: flex; align-items: center; gap: 8px; }
        .mp-score { font-size: 11px; font-weight: 700; font-family: var(--font-mono); padding: 1px 7px; border-radius: 6px; background: var(--surface-2); color: var(--text-secondary); }
        .mp-sub { font-size: 12px; color: var(--text-secondary); margin-top: 2px; font-family: var(--font-mono); }
        .mp-note { font-size: 11px; color: var(--text-tertiary); white-space: nowrap; }
      `}</style>
    </div>
  )
}

export default function TrendDashboard() {
  const [status, setStatus] = useState(null)
  const [history, setHistory] = useState([])
  const [phase, setPhase] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const [s, h, p] = await Promise.all([api.getTrendStatus(), api.getTrendHistory(), api.getMarketPhase()])
      setStatus(s); setHistory(h.trades || []); setPhase(p)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 120000)
    return () => clearInterval(id)
  }, [load])

  if (loading && !status) {
    return <div className="bt-loading animate-in"><div className="bt-spinner" /><div>Загрузка...</div></div>
  }

  const winrate = status?.closed_trades ? (status.wins / status.closed_trades * 100) : 0
  const inMarket = status?.signals?.filter(s => s.in_trend).length || 0

  return (
    <div className="tr-page animate-in">
      <div className="page-header" style={{ marginBottom: 8 }}>
        <h1 className="page-title">Trend-Following <span className="hot-tag">NEW</span></h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          Позиционная стратегия — в рынке при EMA{status?.ema_fast}&gt;EMA{status?.ema_slow}, иначе в кэше · ~раз в 7 недель сделка
        </p>
      </div>

      {error && <div className="bt-error animate-in">❌ {error}</div>}

      <MarketPhaseBanner phase={phase} />

      <div className="xs-metrics">
        <div className="xs-metric main">
          <div className="xs-metric-label">В рынке сейчас</div>
          <div className="xs-metric-val">{inMarket}/{status?.universe_size}</div>
          <div className="xs-metric-sub">монет в позиции</div>
        </div>
        <div className="xs-metric">
          <div className="xs-metric-label">Закрытых сделок</div>
          <div className="xs-metric-val">{status?.closed_trades ?? 0}</div>
          <div className="xs-metric-sub">винрейт {winrate.toFixed(0)}%</div>
        </div>
        <div className="xs-metric">
          <div className="xs-metric-label">Реализ. PnL</div>
          <div className={`xs-metric-val ${(status?.total_realized_pnl_pct ?? 0) >= 0 ? 'pos' : 'neg'}`}>
            {(status?.total_realized_pnl_pct ?? 0) >= 0 ? '+' : ''}{status?.total_realized_pnl_pct ?? 0}%
          </div>
          <div className="xs-metric-sub">по закрытым сделкам</div>
        </div>
        <div className="xs-metric">
          <div className="xs-metric-label">Частота</div>
          <div className="xs-metric-val" style={{ fontSize: 16 }}>~7/год</div>
          <div className="xs-metric-sub">по дизайну — это даёт edge</div>
        </div>
      </div>

      <h3 className="dr-section-title">Открытые позиции</h3>
      {status?.positions?.length > 0 ? (
        <div className="dr-open-list">
          {status.positions.map(p => {
            const pos = p.pnl_pct >= 0
            return (
              <div key={p.symbol} className="dr-open-card">
                <div className="dr-open-head">
                  <span className="dr-side-badge long">LONG</span>
                  <span className="dr-open-symbol">{p.symbol.replace('/USDT', '')}</span>
                  <span className={`dr-open-pnl ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{p.pnl_pct}%</span>
                </div>
                <div className="dr-open-levels">
                  <span>Вход {p.entry}</span>
                  <span>Сейчас {p.price}</span>
                  <span style={{ color: 'var(--text-tertiary)' }}>выход — пересечение EMA вниз</span>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="dr-empty">Нет открытых позиций — все монеты ниже EMA{status?.ema_slow} (не в аптренде)</div>
      )}

      <h3 className="dr-section-title">Сигналы по вселенной ({status?.universe_size})</h3>
      <div className="tr-sig-list">
        {status?.signals?.map(s => <SignalRow key={s.symbol} s={s} />)}
      </div>

      {history.length > 0 && (
        <>
          <h3 className="dr-section-title">История закрытых сделок</h3>
          <div className="tr-history">
            {history.map(t => (
              <div key={t.id} className="tr-hist-row">
                <span>{t.date}</span>
                <span className="tr-hist-sym">{t.symbol.replace('/USDT', '')}</span>
                <span>{t.entry} → {t.exit}</span>
                <span className={t.pnl_pct >= 0 ? 'pos' : 'neg'}>{t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct}%</span>
              </div>
            ))}
          </div>
        </>
      )}

      <style>{`
        .tr-sig-list { display: flex; flex-direction: column; gap: 8px; }
        .tr-sig-row { display: flex; align-items: center; gap: 10px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 14px; box-shadow: var(--shadow-card); }
        .tr-sig-dot { width: 8px; height: 8px; border-radius: 50%; }
        .tr-sig-dot.up { background: var(--long); } .tr-sig-dot.down { background: var(--text-tertiary); }
        .tr-sig-sym { font-weight: 700; font-size: 13px; min-width: 56px; }
        .tr-sig-status { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; }
        .tr-sig-row.up .tr-sig-status { background: var(--long-soft); color: var(--long); }
        .tr-sig-row.down .tr-sig-status { background: var(--surface-2); color: var(--text-tertiary); }
        .tr-sig-price { margin-left: auto; font-family: var(--font-mono); font-size: 12px; color: var(--text-secondary); }
        .tr-sig-dist { font-family: var(--font-mono); font-size: 11px; min-width: 130px; text-align: right; }
        .tr-sig-dist.pos { color: var(--long); } .tr-sig-dist.neg { color: var(--text-tertiary); }

        .tr-history { display: flex; flex-direction: column; gap: 4px; }
        .tr-hist-row { display: flex; align-items: center; gap: 12px; padding: 8px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 12px; font-family: var(--font-mono); }
        .tr-hist-sym { font-weight: 700; min-width: 50px; }
        .tr-hist-row .pos { color: var(--long); margin-left: auto; font-weight: 700; }
        .tr-hist-row .neg { color: var(--short); margin-left: auto; font-weight: 700; }
      `}</style>
    </div>
  )
}
