import { useEffect, useState, useCallback } from 'react'
import { api } from './api'

const KIND_COLOR = {
  'Высокочастотная': 'var(--accent)',
  'Рыночно-нейтральная': 'var(--purple)',
  'Защита от просадок': 'var(--long)',
}

export default function StrategiesCompare() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const d = await api.getStrategiesSummary()
      setData(d); setError(null)
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

  if (loading && !data) {
    return <div className="bt-loading animate-in"><div className="bt-spinner" /><div>Загрузка...</div></div>
  }

  const strategies = data?.strategies || []

  return (
    <div className="sc-page animate-in">
      <div className="page-header" style={{ marginBottom: 8 }}>
        <h1 className="page-title">Сравнение стратегий <span className="hot-tag">LIVE</span></h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          Три независимые бумажные стратегии на живых данных — какая реально работает
        </p>
      </div>

      {error && <div className="bt-error animate-in">❌ {error}</div>}

      <div className="sc-grid">
        {strategies.map(s => {
          const pos = s.realized_pnl_pct >= 0
          return (
            <div key={s.key} className="sc-card">
              <div className="sc-kind" style={{ color: KIND_COLOR[s.kind] || 'var(--text-secondary)' }}>{s.kind}</div>
              <div className="sc-name">{s.name}</div>
              <div className={`sc-pnl ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{s.realized_pnl_pct}%</div>
              <div className="sc-metric-note">{s.metric_note}</div>
              <div className="sc-stats">
                <div className="sc-stat">
                  <span className="sc-stat-val">{s.closed_trades}</span>
                  <span className="sc-stat-lbl">закрытых</span>
                </div>
                <div className="sc-stat">
                  <span className="sc-stat-val">{s.winrate != null ? s.winrate + '%' : '—'}</span>
                  <span className="sc-stat-lbl">винрейт</span>
                </div>
                <div className="sc-stat">
                  <span className="sc-stat-val">{s.open_positions}</span>
                  <span className="sc-stat-lbl">открыто</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="sc-disclaimer">
        ⚠️ {data?.note}
      </div>

      <div className="sc-explain">
        <h3>Как читать</h3>
        <ul>
          <li><b>Momentum</b> — высокочастотная (несколько сделок/день). По бэктесту слабая, у границы безубытка.</li>
          <li><b>Long-Short</b> — рыночно-нейтральная, ребаланс раз в неделю. Не зависит от направления рынка. Sharpe ~0.4 (слабая).</li>
          <li><b>Trend-Following</b> — редкие сделки (~раз в 7 недель), защита от просадок. Лучший бэктест (Sharpe 0.73), но это не альфа, а снижение риска в крахи.</li>
        </ul>
        <p className="sc-honest">Честно: ни одна стратегия не имеет доказанного edge на живых данных — это и проверяет дальран. Метрики посчитаны по-разному (разная механика), поэтому прямое сравнение чисел приблизительно.</p>
      </div>

      <style>{`
        .sc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
        .sc-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px; box-shadow: var(--shadow-card); }
        .sc-kind { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
        .sc-name { font-size: 18px; font-weight: 800; color: var(--text); margin: 4px 0 10px; }
        .sc-pnl { font-size: 30px; font-weight: 800; font-family: var(--font-mono); }
        .sc-pnl.pos { color: var(--long); } .sc-pnl.neg { color: var(--short); }
        .sc-metric-note { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
        .sc-stats { display: flex; gap: 16px; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border); }
        .sc-stat { display: flex; flex-direction: column; }
        .sc-stat-val { font-size: 16px; font-weight: 700; font-family: var(--font-mono); color: var(--text); }
        .sc-stat-lbl { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; }
        .sc-disclaimer { margin: 18px 0; padding: 12px 16px; background: var(--amber-soft); border: 1px solid var(--amber); border-radius: var(--radius-md); font-size: 12px; color: var(--text-secondary); }
        .sc-explain { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 16px 20px; }
        .sc-explain h3 { font-size: 14px; margin-bottom: 10px; color: var(--text); }
        .sc-explain ul { margin: 0 0 10px 18px; display: flex; flex-direction: column; gap: 6px; }
        .sc-explain li { font-size: 13px; color: var(--text-secondary); }
        .sc-honest { font-size: 12px; color: var(--text-tertiary); font-style: italic; }
      `}</style>
    </div>
  )
}
