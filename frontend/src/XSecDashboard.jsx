import { useEffect, useState, useCallback } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts'
import { api } from './api'

function PortfolioSide({ title, positions, side }) {
  const color = side === 'long' ? 'var(--long)' : 'var(--short)'
  return (
    <div className="xs-side">
      <div className="xs-side-title" style={{ color }}>{title}</div>
      {positions.length === 0 ? (
        <div className="xs-empty-small">—</div>
      ) : positions.map(p => {
        const pos = p.pnl_pct >= 0
        return (
          <div key={p.symbol} className="xs-pos">
            <span className="xs-pos-sym">{p.symbol.replace('/USDT', '')}</span>
            <span className="xs-pos-mom" title="momentum за окно">{p.mom > 0 ? '+' : ''}{p.mom}%</span>
            <span className={`xs-pos-pnl ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{p.pnl_pct}%</span>
          </div>
        )
      })}
    </div>
  )
}

export default function XSecDashboard() {
  const [status, setStatus] = useState(null)
  const [history, setHistory] = useState(null)
  const [ranking, setRanking] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const [s, h, r] = await Promise.all([
        api.getXsecStatus(),
        api.getXsecHistory(),
        api.getXsecRanking(),
      ])
      setStatus(s); setHistory(h); setRanking(r.ranking || [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 60000)
    return () => clearInterval(id)
  }, [load])

  if (loading && !status) {
    return <div className="bt-loading animate-in"><div className="bt-spinner" /><div>Загрузка...</div></div>
  }

  const longs = status?.positions?.filter(p => p.side === 'long') || []
  const shorts = status?.positions?.filter(p => p.side === 'short') || []
  const curve = history?.equity_curve || []
  const roi = status ? ((status.equity / status.deposit - 1) * 100) : 0
  const pos = roi >= 0

  return (
    <div className="xs-page animate-in">
      <div className="page-header" style={{ marginBottom: 8 }}>
        <h1 className="page-title">Cross-Sectional Momentum <span className="hot-tag">NEW</span></h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          Рыночно-нейтральная long-short · ребаланс раз в {status?.rebal_days || 7}д · бумажная торговля
        </p>
      </div>

      {error && <div className="bt-error animate-in">❌ {error}</div>}

      {/* Метрики */}
      <div className="xs-metrics">
        <div className="xs-metric main">
          <div className="xs-metric-label">Бумажный депозит</div>
          <div className={`xs-metric-val ${pos ? 'pos' : 'neg'}`}>${status?.equity?.toFixed(0)}</div>
          <div className="xs-metric-sub">{pos ? '+' : ''}{roi.toFixed(1)}% от ${status?.deposit}</div>
        </div>
        <div className="xs-metric">
          <div className="xs-metric-label">Нереализ. PnL</div>
          <div className={`xs-metric-val ${(status?.unrealized_pct ?? 0) >= 0 ? 'pos' : 'neg'}`}>
            {(status?.unrealized_pct ?? 0) >= 0 ? '+' : ''}{status?.unrealized_pct ?? 0}%
          </div>
          <div className="xs-metric-sub">текущий цикл</div>
        </div>
        <div className="xs-metric">
          <div className="xs-metric-label">Плечо (vol-managed)</div>
          <div className="xs-metric-val">x{status?.leverage ?? 1}</div>
          <div className="xs-metric-sub">target {status?.vol_target ?? 2}% · cap x{status?.vol_cap ?? 2}</div>
        </div>
        <div className="xs-metric">
          <div className="xs-metric-label">След. ребаланс</div>
          <div className="xs-metric-val">{status?.next_rebalance_in_days ?? '—'}д</div>
          <div className="xs-metric-sub">lookback {status?.lookback_days}д · N={status?.n_per_side}</div>
        </div>
        <div className="xs-metric">
          <div className="xs-metric-label">Ребалансов</div>
          <div className="xs-metric-val">{history?.rebalances?.length ?? 0}</div>
          <div className="xs-metric-sub">всего циклов</div>
        </div>
      </div>

      {/* Текущий портфель */}
      <h3 className="dr-section-title">Текущий портфель (нейтральный 50/50)</h3>
      {status?.initialized ? (
        <div className="xs-portfolio">
          <PortfolioSide title="▲ ЛОНГ (сильнейшие)" positions={longs} side="long" />
          <PortfolioSide title="▼ ШОРТ (слабейшие)" positions={shorts} side="short" />
        </div>
      ) : (
        <div className="dr-empty">Портфель ещё не сформирован — ждём первого ребаланса</div>
      )}

      {/* Equity curve */}
      {curve.length > 1 && (
        <div className="bt-chart-card" style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', marginBottom: 16 }}>
            Кривая бумажного депозита ({curve.length} ребалансов)
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={curve}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fill: 'var(--text-tertiary)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'var(--text-tertiary)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} tickFormatter={v => `$${v}`} width={56} />
              <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, fontFamily: 'var(--font-mono)', fontSize: 12 }} formatter={v => [`$${v}`, 'Депозит']} />
              <ReferenceLine y={status?.deposit} stroke="var(--text-tertiary)" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="equity" stroke={pos ? 'var(--long)' : 'var(--short)'} strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Рейтинг вселенной */}
      {ranking.length > 0 && (
        <>
          <h3 className="dr-section-title">Рейтинг вселенной по momentum ({status?.lookback_days}д)</h3>
          <div className="xs-ranking">
            {ranking.map((r, i) => {
              const isLong = i < (status?.n_per_side ?? 3)
              const isShort = i >= ranking.length - (status?.n_per_side ?? 3)
              return (
                <div key={r.symbol} className={`xs-rank-item ${isLong ? 'rl' : isShort ? 'rs' : ''}`}>
                  <span className="xs-rank-num">{i + 1}</span>
                  <span className="xs-rank-sym">{r.symbol.replace('/USDT', '')}</span>
                  <span className={`xs-rank-mom ${r.mom_pct >= 0 ? 'pos' : 'neg'}`}>{r.mom_pct > 0 ? '+' : ''}{r.mom_pct}%</span>
                </div>
              )
            })}
          </div>
        </>
      )}

      <style>{`
        .xs-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 16px 0; }
        .xs-metric { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px 16px; box-shadow: var(--shadow-card); }
        .xs-metric.main { border-color: var(--accent); }
        .xs-metric-label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 6px; }
        .xs-metric-val { font-size: 22px; font-weight: 800; font-family: var(--font-mono); color: var(--text); }
        .xs-metric-val.pos { color: var(--long); } .xs-metric-val.neg { color: var(--short); }
        .xs-metric-sub { font-size: 11px; color: var(--text-tertiary); margin-top: 3px; }

        .xs-portfolio { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .xs-side { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px; box-shadow: var(--shadow-card); }
        .xs-side-title { font-size: 12px; font-weight: 800; margin-bottom: 10px; letter-spacing: 0.02em; }
        .xs-empty-small { color: var(--text-tertiary); font-size: 13px; }
        .xs-pos { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border); }
        .xs-pos:last-child { border-bottom: none; }
        .xs-pos-sym { font-weight: 700; font-size: 13px; min-width: 56px; }
        .xs-pos-mom { font-size: 11px; color: var(--text-tertiary); font-family: var(--font-mono); margin-left: auto; }
        .xs-pos-pnl { font-size: 13px; font-family: var(--font-mono); font-weight: 700; min-width: 56px; text-align: right; }
        .xs-pos-pnl.pos { color: var(--long); } .xs-pos-pnl.neg { color: var(--short); }

        .xs-ranking { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 6px; }
        .xs-rank-item { display: flex; align-items: center; gap: 6px; padding: 6px 10px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 12px; }
        .xs-rank-item.rl { border-color: var(--long); background: var(--long-soft); }
        .xs-rank-item.rs { border-color: var(--short); background: var(--short-soft); }
        .xs-rank-num { color: var(--text-tertiary); font-family: var(--font-mono); min-width: 18px; }
        .xs-rank-sym { font-weight: 700; }
        .xs-rank-mom { margin-left: auto; font-family: var(--font-mono); }
        .xs-rank-mom.pos { color: var(--long); } .xs-rank-mom.neg { color: var(--short); }
      `}</style>
    </div>
  )
}
