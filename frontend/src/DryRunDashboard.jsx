import { useEffect, useState, useCallback } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts'
import { api } from './api'

const RESULT_LABELS = {
  sl: 'Стоп', tp1: 'TP1', tp2: 'TP2', tp3: 'TP3',
  timeout: 'Таймаут', be: 'Б/У', potential: 'Раннее закрытие',
}
const RESULT_COLOR = {
  sl: 'var(--short)', tp1: 'var(--accent)', tp2: 'var(--long)', tp3: 'var(--long)',
  timeout: 'var(--text-tertiary)', be: 'var(--amber)', potential: 'var(--amber)',
}

function StatusBar({ status }) {
  if (!status) return null
  const lossPct = status.daily_loss_pct ?? 0
  const lossLimit = status.daily_loss_limit_pct ?? 4
  const lossRatio = Math.min(100, (lossPct / lossLimit) * 100)
  const slotsUsed = status.open_trades_count ?? 0
  const slotsMax = status.max_open_trades ?? 3

  return (
    <div className="dr-status-grid">
      <div className="dr-status-card">
        <div className="dr-status-label">Режим</div>
        <div className="dr-status-val">🚀 {status.strategy_mode}</div>
      </div>

      <div className="dr-status-card">
        <div className="dr-status-label">Слоты позиций</div>
        <div className="dr-status-val">{slotsUsed} / {slotsMax}</div>
        <div className="dr-bar-track">
          <div className="dr-bar-fill" style={{ width: `${(slotsUsed / slotsMax) * 100}%`, background: 'var(--accent)' }} />
        </div>
      </div>

      <div className={`dr-status-card ${!status.daily_loss_ok ? 'dr-alert' : ''}`}>
        <div className="dr-status-label">Дневной лимит убытка</div>
        <div className={`dr-status-val ${!status.daily_loss_ok ? 'neg' : ''}`}>
          {lossPct.toFixed(2)}% / {lossLimit}%
        </div>
        <div className="dr-bar-track">
          <div className="dr-bar-fill" style={{ width: `${lossRatio}%`, background: lossRatio > 75 ? 'var(--short)' : 'var(--amber)' }} />
        </div>
        {!status.daily_loss_ok && <div className="dr-alert-text">⛔ Торговля остановлена до конца дня</div>}
      </div>

      <div className="dr-status-card">
        <div className="dr-status-label">Cooldown</div>
        {status.cooldowns?.length > 0 ? (
          <div className="dr-cooldown-list">
            {status.cooldowns.map(c => (
              <div key={c.symbol} className="dr-cooldown-item">
                <span>{c.symbol.replace('/USDT', '')}</span>
                <span style={{ color: 'var(--text-tertiary)' }}>{c.minutes_left}м</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="dr-status-val" style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>нет активных</div>
        )}
      </div>
    </div>
  )
}

function OpenTrades({ trades }) {
  if (!trades?.length) {
    return <div className="dr-empty">Нет открытых позиций — сканер ждёт сигнала</div>
  }
  return (
    <div className="dr-open-list">
      {trades.map(t => {
        const pos = t.pnl_pct >= 0
        return (
          <div key={t.symbol} className="dr-open-card">
            <div className="dr-open-head">
              <span className={`dr-side-badge ${t.signal === 'LONG' ? 'long' : 'short'}`}>{t.signal}</span>
              <span className="dr-open-symbol">{t.symbol.replace('/USDT', '')}</span>
              <span className={`dr-open-pnl ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{t.pnl_pct}%</span>
            </div>
            <div className="dr-open-levels">
              <span>Вход {t.entry}</span>
              <span>Сейчас {t.price}</span>
              <span style={{ color: 'var(--short)' }}>SL {t.stop}</span>
              {t.time_exit ? (
                <span style={{ color: 'var(--text-tertiary)' }}>⏱ выход по времени (~36ч)</span>
              ) : (
                <span style={{ color: 'var(--long)' }}>TP1 {t.tp1}{t.tp1_hit ? ' ✓' : ''}</span>
              )}
            </div>
            <div className="dr-open-meta">
              <span>{t.position_size?.toFixed(0)}$</span>
              {t.score != null && <span>score {t.score}</span>}
              {t.opened_at && <span>{new Date(t.opened_at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>}
              {t.opened_at && t.time_exit && (() => {
                const hoursLeft = 36 - (Date.now() - new Date(t.opened_at).getTime()) / 3600000
                return <span>{hoursLeft > 0 ? `до выхода ~${hoursLeft.toFixed(0)}ч` : 'пора закрыться'}</span>
              })()}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ResultBreakdown({ byResult }) {
  const entries = Object.entries(byResult || {})
  if (!entries.length) return null
  const total = entries.reduce((s, [, v]) => s + v.count, 0)
  return (
    <div className="dr-breakdown-grid">
      {entries.map(([result, v]) => (
        <div key={result} className="dr-breakdown-card">
          <div className="dr-breakdown-label" style={{ color: RESULT_COLOR[result] || 'var(--text)' }}>
            {RESULT_LABELS[result] || result}
          </div>
          <div className="dr-breakdown-count">{v.count}</div>
          <div className="dr-breakdown-bar-track">
            <div className="dr-breakdown-bar-fill" style={{ width: `${(v.count / total) * 100}%`, background: RESULT_COLOR[result] || 'var(--text-tertiary)' }} />
          </div>
          <div className={`dr-breakdown-pnl ${v.sum_pnl >= 0 ? 'pos' : 'neg'}`}>{v.sum_pnl >= 0 ? '+' : ''}{v.sum_pnl}%</div>
        </div>
      ))}
    </div>
  )
}

export default function DryRunDashboard() {
  const [status, setStatus] = useState(null)
  const [openTrades, setOpenTrades] = useState([])
  const [breakdown, setBreakdown] = useState(null)
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const [s, o, b] = await Promise.all([
        api.getDryrunStatus(),
        api.getDryrunOpen(),
        api.getDryrunBreakdown(days),
      ])
      setStatus(s); setOpenTrades(o); setBreakdown(b)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  const cum = breakdown?.equity_curve || []
  const pos = (breakdown?.total_pnl_pct ?? 0) >= 0

  return (
    <div className="dr-page animate-in">
      <div className="page-header" style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h1 className="page-title">Дальран — мониторинг</h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
            Живой статус momentum-стратегии · обновляется каждые 30с
          </p>
        </div>
        <div className="bf-toggle">
          {[7, 30, 90].map(d => (
            <button key={d} className={`bft ${days === d ? 'active' : ''}`} onClick={() => setDays(d)}>{d}д</button>
          ))}
        </div>
      </div>

      {error && <div className="bt-error animate-in">❌ {error}</div>}
      {loading && !status ? (
        <div className="bt-loading animate-in"><div className="bt-spinner" /><div>Загрузка...</div></div>
      ) : (
        <>
          <StatusBar status={status} />

          <h3 className="dr-section-title">Открытые позиции ({openTrades.length})</h3>
          <OpenTrades trades={openTrades} />

          <h3 className="dr-section-title">Разбивка по результатам ({days}д)</h3>
          <ResultBreakdown byResult={breakdown?.by_result} />

          {cum.length > 1 && (
            <div className="bt-chart-card">
              <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', marginBottom: 16 }}>
                Накопленный PnL ({breakdown.total_trades} сделок, {pos ? '+' : ''}{breakdown.total_pnl_pct}%)
              </h3>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={cum}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-tertiary)', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'var(--text-tertiary)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} tickFormatter={v => `${v}%`} width={48} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, fontFamily: 'var(--font-mono)', fontSize: 12 }}
                    formatter={(v, n, p) => [`${v}%`, `${p.payload.symbol} · ${RESULT_LABELS[p.payload.result] || p.payload.result}`]} />
                  <ReferenceLine y={0} stroke="var(--text-tertiary)" strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="cum_pnl" stroke={pos ? 'var(--long)' : 'var(--short)'} strokeWidth={2.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}

      <style>{`
        .dr-status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }
        .dr-status-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px 16px; box-shadow: var(--shadow-card); }
        .dr-status-card.dr-alert { border-color: var(--short); }
        .dr-status-label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 6px; }
        .dr-status-val { font-size: 18px; font-weight: 800; font-family: var(--font-mono); color: var(--text); }
        .dr-status-val.neg { color: var(--short); }
        .dr-alert-text { font-size: 11px; color: var(--short); margin-top: 6px; font-weight: 600; }
        .dr-bar-track { height: 5px; background: var(--surface-2); border-radius: 3px; margin-top: 8px; overflow: hidden; }
        .dr-bar-fill { height: 100%; border-radius: 3px; transition: width 0.3s ease; }
        .dr-cooldown-list { display: flex; flex-direction: column; gap: 4px; margin-top: 2px; }
        .dr-cooldown-item { display: flex; justify-content: space-between; font-size: 12px; font-family: var(--font-mono); }

        .dr-section-title { font-size: 14px; font-weight: 700; color: var(--text); margin: 24px 0 12px; }

        .dr-empty { padding: 24px; text-align: center; color: var(--text-tertiary); font-size: 13px; background: var(--surface); border: 1px dashed var(--border); border-radius: var(--radius-md); }

        .dr-open-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
        .dr-open-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px 16px; box-shadow: var(--shadow-card); }
        .dr-open-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
        .dr-side-badge { font-size: 11px; font-weight: 800; padding: 2px 8px; border-radius: 6px; }
        .dr-side-badge.long { background: var(--long-soft); color: var(--long); }
        .dr-side-badge.short { background: var(--short-soft); color: var(--short); }
        .dr-open-symbol { font-weight: 700; font-size: 14px; }
        .dr-open-pnl { margin-left: auto; font-family: var(--font-mono); font-weight: 800; font-size: 15px; }
        .dr-open-pnl.pos { color: var(--long); }
        .dr-open-pnl.neg { color: var(--short); }
        .dr-open-levels { display: flex; flex-wrap: wrap; gap: 10px; font-size: 11px; font-family: var(--font-mono); color: var(--text-secondary); margin-bottom: 8px; }
        .dr-open-meta { display: flex; gap: 10px; font-size: 11px; color: var(--text-tertiary); }

        .dr-breakdown-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
        .dr-breakdown-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 12px 14px; box-shadow: var(--shadow-card); }
        .dr-breakdown-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 6px; }
        .dr-breakdown-count { font-size: 22px; font-weight: 800; font-family: var(--font-mono); color: var(--text); }
        .dr-breakdown-bar-track { height: 4px; background: var(--surface-2); border-radius: 2px; margin: 8px 0; overflow: hidden; }
        .dr-breakdown-bar-fill { height: 100%; border-radius: 2px; }
        .dr-breakdown-pnl { font-size: 12px; font-family: var(--font-mono); font-weight: 700; }
        .dr-breakdown-pnl.pos { color: var(--long); }
        .dr-breakdown-pnl.neg { color: var(--short); }
      `}</style>
    </div>
  )
}
