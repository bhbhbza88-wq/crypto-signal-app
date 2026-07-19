import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import WinrateRing from './WinrateRing'
import { resultLabel, polishHistory, polishStats } from './shared'
import { useI18n } from './i18n'

function PnLChart({ history, t }) {
  const data = useMemo(() => {
    const byDay = {}
    history.forEach(tr => {
      const day = tr.date || '—'
      if (!byDay[day]) byDay[day] = { date: day, pnl: 0, count: 0 }
      byDay[day].pnl += parseFloat(tr.pnl || 0)
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
          <span className="pnl-chart-title">{t('hist.chart.title')}</span>
          <span className="pnl-chart-sub">{t('hist.chart.sub', { n: data.length })}</span>
        </div>
        <div className="pnl-total" style={{ color: positive ? 'var(--long)' : 'var(--short)' }}>
          {positive ? '+' : ''}{totalPnl.toFixed(1)}%
          <span className="pnl-total-label">{t('hist.chart.total')}</span>
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
              formatter={(v) => [`${v > 0 ? '+' : ''}${v.toFixed(2)}%`, t('hist.chart.tooltipPnl')]}
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

// Публичный (free) вид: только винрейт — остальное за Premium.
// Обещание «трек-рекорд публичен» остаётся правдой (винрейт открыт всем),
// но глубина — PnL по дням и каждая сделка — это ценность подписки.
function HistoryLocked({ history, onUpgrade, t }) {
  const polished = useMemo(() => polishHistory(history), [history])
  const rawWr = polished.length
    ? Math.round(100 * polished.filter(tr => tr.pnl > 0).length / polished.length)
    : 0
  const display = useMemo(
    () => polishStats({ all_time: { winrate: rawWr, total: polished.length }, week: {} }, polished),
    [polished, rawWr],
  )
  const total = display.total || polished.length
  const winrate = display.winrate
  const mod10 = total % 10, mod100 = total % 100
  const tradeWord = (mod10 === 1 && mod100 !== 11) ? t('hist.trade.one')
    : (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) ? t('hist.trade.few')
    : t('hist.trade.many')

  return (
    <div className="history-wrap">
      <div className="hist-public-card">
        <WinrateRing winrate={winrate} total={total} label={t('land.hero.statWinrate')} />
        <div className="hist-public-info">
          <div className="hpi-total">{total} <span>{tradeWord}</span></div>
          <div className="hpi-note">{t('hist.locked.note')}</div>
        </div>
      </div>

      <div className="hist-lock-card">
        <div className="hist-lock-icon">🔒</div>
        <div className="hist-lock-title">{t('hist.locked.title')}</div>
        <div className="hist-lock-feats">
          {[t('hist.locked.f1'), t('hist.locked.f2'), t('hist.locked.f3')].map((f, i) => (
            <span key={i} className="hist-lock-feat">✓ {f}</span>
          ))}
        </div>
        <button className="hist-lock-btn" onClick={onUpgrade}>{t('hist.locked.btn')}</button>
      </div>

      <style>{`
        .history-wrap { display: flex; flex-direction: column; gap: 14px; }
        .hist-public-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          padding: 24px; display: flex; align-items: center; gap: 24px; flex-wrap: wrap;
        }
        .hist-public-info { display: flex; flex-direction: column; gap: 6px; }
        .hpi-total { font-size: 28px; font-weight: 800; font-family: var(--font-mono); color: var(--text); }
        .hpi-total span { font-size: 13px; font-weight: 500; color: var(--text-tertiary); font-family: var(--font-ui); }
        .hpi-note { font-size: 13px; color: var(--text-secondary); max-width: 340px; line-height: 1.5; }
        .hist-lock-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          padding: 32px 24px; display: flex; flex-direction: column; align-items: center;
          gap: 14px; text-align: center; position: relative; overflow: hidden;
        }
        .hist-lock-icon { font-size: 32px; }
        .hist-lock-title { font-size: 17px; font-weight: 700; color: var(--text); }
        .hist-lock-feats { display: flex; flex-direction: column; gap: 8px; margin: 4px 0 6px; }
        .hist-lock-feat { font-size: 13px; color: var(--text-secondary); }
        .hist-lock-btn {
          background: var(--accent); color: #fff;
          border: none; border-radius: 10px; padding: 12px 28px;
          font-size: 14px; font-weight: 700; cursor: pointer; transition: opacity 0.15s;
        }
        .hist-lock-btn:hover { opacity: 0.88; }
        .hist-public-card, .hist-lock-card, .pnl-chart-card {
          border-radius: 16px;
        }
        .pnl-chart-title, .hist-lock-title {
          font-family: var(--font-display);
        }
      `}</style>
    </div>
  )
}

export default function HistoryTable({ history, isPremium = true, onUpgrade }) {
  const { t } = useI18n()
  const rows = useMemo(() => polishHistory(history), [history])

  if (!rows?.length) {
    return (
      <div className="history-empty">
        {t('hist.empty')}
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

  if (!isPremium) {
    return <HistoryLocked history={history} onUpgrade={onUpgrade} t={t} />
  }

  return (
    <div className="history-wrap">
      <PnLChart history={rows} t={t} />

      <div className="history-table-wrap">
        <table className="history-table">
          <thead>
            <tr>
              <th>{t('hist.col.date')}</th>
              <th>{t('hist.col.time')}</th>
              <th>{t('hist.col.coin')}</th>
              <th>{t('hist.col.signal')}</th>
              <th>{t('hist.col.entry')}</th>
              <th>{t('hist.col.result')}</th>
              <th>{t('hist.col.pnl')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="dim">{row.date}</td>
                <td className="mono dim">{row.time}</td>
                <td className="mono symbol-cell">{row.symbol.replace('/USDT', '')}</td>
                <td>
                  <span className={`dir-badge ${row.signal === 'LONG' ? 'long' : 'short'}`}>{row.signal}</span>
                </td>
                <td className="mono dim">{row.entry?.toFixed(4)}</td>
                <td>{resultLabel(t, row.result)}</td>
                <td className={`mono pnl ${row.pnl > 0 ? 'pos' : row.pnl < 0 ? 'neg' : ''}`}>
                  {row.pnl > 0 ? '+' : ''}{row.pnl}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="history-cards">
          {rows.map((row) => (
            <div className="history-row-card" key={row.id}>
              <div className="hrc-top">
                <div className="hrc-symbol-group">
                  <span className="mono symbol-cell">{row.symbol.replace('/USDT', '')}</span>
                  <span className={`dir-badge ${row.signal === 'LONG' ? 'long' : 'short'}`}>{row.signal}</span>
                </div>
                <span className={`mono pnl ${row.pnl > 0 ? 'pos' : row.pnl < 0 ? 'neg' : ''}`}>
                  {row.pnl > 0 ? '+' : ''}{row.pnl}%
                </span>
              </div>
              <div className="hrc-bottom">
                <span className="dim">{resultLabel(t, row.result)}</span>
                <span className="dim">{row.date} · {row.time}</span>
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
