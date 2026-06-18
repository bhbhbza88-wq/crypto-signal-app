import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const RESULT_LABELS = {
  tp1: 'TP1', tp2: 'TP2', tp3: 'TP3',
  sl: 'Стоп', be: 'Б/У', potential: 'Закрыт',
}

function PnLChart({ history }) {
  const data = useMemo(() => {
    const byDay = {}
    history.forEach(t => {
      const day = t.date || '—'
      if (!byDay[day]) byDay[day] = { date: day, pnl: 0, count: 0 }
      byDay[day].pnl += parseFloat(t.pnl || 0)
      byDay[day].count += 1
    })
    return Object.values(byDay).slice(-14)
  }, [history])

  if (data.length === 0) return null

  const totalPnl = data.reduce((s, d) => s + d.pnl, 0)
  const positive = totalPnl >= 0

  return (
    <div className="pnl-chart-card">
      <div className="pnl-chart-header">
        <div>
          <span className="pnl-chart-title">PnL по дням</span>
          <span className="pnl-chart-sub">Последние {data.length} дней</span>
        </div>
        <div className="pnl-total" style={{ color: positive ? 'var(--long)' : 'var(--short)' }}>
          {positive ? '+' : ''}{totalPnl.toFixed(1)}%
          <span className="pnl-total-label">Итого</span>
        </div>
      </div>
      <div style={{ height: 120 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barSize={20}>
            <XAxis
              dataKey="date"
              tick={{ fill: 'var(--text-tertiary)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={false} tickLine={false}
              tickFormatter={v => v.slice(5)}
            />
            <YAxis hide />
            <Tooltip
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, fontFamily: 'var(--font-mono)', fontSize: 12 }}
              formatter={(v) => [`${v > 0 ? '+' : ''}${v.toFixed(2)}%`, 'PnL']}
              labelFormatter={v => `📅 ${v}`}
            />
            <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.pnl >= 0 ? 'var(--long)' : 'var(--short)'} opacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <style>{`
        .pnl-chart-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          padding: 20px 20px 12px; display: flex; flex-direction: column; gap: 14px;
        }
        .pnl-chart-header { display: flex; justify-content: space-between; align-items: flex-start; }
        .pnl-chart-title { display: block; font-size: 14px; font-weight: 700; color: var(--text); }
        .pnl-chart-sub { display: block; font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
        .pnl-total {
          font-family: var(--font-mono); font-size: 24px; font-weight: 700;
          display: flex; flex-direction: column; align-items: flex-end; gap: 2px;
        }
        .pnl-total-label { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
      `}</style>
    </div>
  )
}

export default function HistoryTable({ history }) {
  if (!history?.length) {
    return (
      <div className="history-empty">
        Сделок пока не было. Как только сканер найдёт и закроет сигнал — он появится здесь.
        <style>{`
          .history-empty {
            padding: 36px 20px; text-align: center;
            color: var(--text-tertiary); font-size: 13px;
            background: var(--surface);
            border: 1px dashed var(--border-strong);
            border-radius: var(--radius-lg);
          }
        `}</style>
      </div>
    )
  }

  return (
    <div className="history-wrap">
      <PnLChart history={history} />

      <div className="history-table-wrap">
        <table className="history-table">
          <thead>
            <tr>
              <th>Дата</th>
              <th>Время</th>
              <th>Монета</th>
              <th>Сигнал</th>
              <th>Вход</th>
              <th>Результат</th>
              <th>PnL</th>
            </tr>
          </thead>
          <tbody>
            {history.map((t) => (
              <tr key={t.id}>
                <td className="dim">{t.date}</td>
                <td className="mono dim">{t.time}</td>
                <td className="mono symbol-cell">{t.symbol.replace('/USDT', '')}</td>
                <td>
                  <span className={`dir-badge ${t.signal === 'LONG' ? 'long' : 'short'}`}>{t.signal}</span>
                </td>
                <td className="mono dim">{t.entry?.toFixed(4)}</td>
                <td>{RESULT_LABELS[t.result] || t.result}</td>
                <td className={`mono pnl ${t.pnl > 0 ? 'pos' : t.pnl < 0 ? 'neg' : ''}`}>
                  {t.pnl > 0 ? '+' : ''}{t.pnl}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="history-cards">
          {history.map((t) => (
            <div className="history-row-card" key={t.id}>
              <div className="hrc-top">
                <div className="hrc-symbol-group">
                  <span className="mono symbol-cell">{t.symbol.replace('/USDT', '')}</span>
                  <span className={`dir-badge ${t.signal === 'LONG' ? 'long' : 'short'}`}>{t.signal}</span>
                </div>
                <span className={`mono pnl ${t.pnl > 0 ? 'pos' : t.pnl < 0 ? 'neg' : ''}`}>
                  {t.pnl > 0 ? '+' : ''}{t.pnl}%
                </span>
              </div>
              <div className="hrc-bottom">
                <span className="dim">{RESULT_LABELS[t.result] || t.result}</span>
                <span className="dim">{t.date} · {t.time}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <style>{`
        .history-wrap { display: flex; flex-direction: column; gap: 14px; }
        .history-table-wrap {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card); overflow: hidden;
        }
        .history-table { width: 100%; border-collapse: collapse; font-size: 13px; display: table; }
        .history-table th {
          text-align: left; padding: 13px 18px;
          color: var(--text-tertiary); font-size: 11px;
          text-transform: uppercase; letter-spacing: 0.05em;
          font-weight: 500; border-bottom: 1px solid var(--border); white-space: nowrap;
        }
        .history-table td {
          padding: 12px 18px; border-bottom: 1px solid var(--border);
          color: var(--text); white-space: nowrap;
        }
        .history-table tbody tr:last-child td { border-bottom: none; }
        .history-table tbody tr:hover { background: var(--surface-hover); }
        .mono { font-family: var(--font-mono); }
        .dim { color: var(--text-secondary); }
        .symbol-cell { font-weight: 600; color: var(--text); }
        .dir-badge { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 6px; font-family: var(--font-mono); }
        .dir-badge.long { background: var(--long-soft); color: var(--long); }
        .dir-badge.short { background: var(--short-soft); color: var(--short); }
        .pnl.pos { color: var(--long); }
        .pnl.neg { color: var(--short); }
        .history-cards { display: none; }
        @media (max-width: 680px) {
          .history-table { display: none; }
          .history-cards { display: flex; flex-direction: column; }
          .history-row-card { padding: 14px 16px; border-bottom: 1px solid var(--border); }
          .history-row-card:last-child { border-bottom: none; }
          .hrc-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
          .hrc-symbol-group { display: flex; align-items: center; gap: 8px; }
          .hrc-bottom { display: flex; justify-content: space-between; font-size: 12px; }
        }
      `}</style>
    </div>
  )
}
