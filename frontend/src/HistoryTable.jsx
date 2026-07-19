import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from 'recharts'
import WinrateRing from './WinrateRing'
import { resultLabel, polishHistory, polishStats, buildShowcaseCurve } from './shared'
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
    return Object.values(byDay).slice(-30)
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
      <div style={{ height: 140 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barSize={data.length > 20 ? 8 : 14}>
            <XAxis
              dataKey="date"
              tick={{ fill: 'var(--text-tertiary)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={false} tickLine={false}
              tickFormatter={v => String(v).slice(5)}
              interval="preserveStartEnd"
              minTickGap={28}
            />
            <YAxis hide />
            <Tooltip
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, fontFamily: 'var(--font-mono)', fontSize: 12 }}
              formatter={(v) => [`${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%`, t('hist.chart.tooltipPnl')]}
              labelFormatter={v => v}
            />
            <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.pnl >= 0 ? 'var(--long)' : 'var(--short)'} opacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/** Красивый блок месячной статистики — виден всем (free + premium). */
function MonthOverview({ history, stats, t }) {
  const polished = useMemo(() => polishHistory(history), [history])
  const display = useMemo(() => polishStats(stats, polished), [stats, polished])
  const curve = useMemo(() => buildShowcaseCurve(history), [history])
  const wins = polished.filter(tr => tr.pnl > 0).length
  const best = polished.reduce((b, tr) => (!b || tr.pnl > b.pnl ? tr : b), null)

  return (
    <div className="hist-month">
      <div className="hist-month-top">
        <div>
          <div className="hist-month-badge">{t('hist.period.badge')}</div>
          <h2 className="hist-month-title">{t('hist.period.title')}</h2>
          <p className="hist-month-sub">{t('hist.period.sub')}</p>
        </div>
        <WinrateRing winrate={display.winrate} total={display.total} label={t('land.hero.statWinrate')} />
      </div>

      <div className="hist-kpi-grid">
        <div className="hist-kpi">
          <span className="hist-kpi-label">{t('hist.kpi.trades')}</span>
          <span className="hist-kpi-val mono">{display.total}</span>
          <span className="hist-kpi-hint">{t('hist.kpi.wins', { n: wins })}</span>
        </div>
        <div className="hist-kpi">
          <span className="hist-kpi-label">{t('hist.kpi.avg')}</span>
          <span className="hist-kpi-val mono pos">+{display.avgPnl}%</span>
          <span className="hist-kpi-hint">{t('hist.kpi.perTrade')}</span>
        </div>
        <div className="hist-kpi">
          <span className="hist-kpi-label">{t('hist.kpi.sum')}</span>
          <span className={`hist-kpi-val mono ${display.totalPnl >= 0 ? 'pos' : 'neg'}`}>
            {display.totalPnl >= 0 ? '+' : ''}{display.totalPnl}%
          </span>
          <span className="hist-kpi-hint">{t('hist.kpi.monthSum')}</span>
        </div>
        <div className="hist-kpi">
          <span className="hist-kpi-label">{t('hist.kpi.best')}</span>
          <span className="hist-kpi-val mono pos">
            {best ? `+${best.pnl}%` : '—'}
          </span>
          <span className="hist-kpi-hint">
            {best ? String(best.symbol || '').replace('/USDT', '') : t('hist.kpi.noBest')}
          </span>
        </div>
      </div>

      {curve.length > 1 && (
        <div className="hist-equity">
          <div className="hist-equity-head">
            <span>{t('hist.equity.title')}</span>
            <strong className="pos">
              {curve[curve.length - 1]?.equity != null
                ? `+${curve[curve.length - 1].equity}%`
                : '—'}
            </strong>
          </div>
          <div style={{ height: 72 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={curve}>
                <YAxis hide domain={['auto', 'auto']} />
                <Line type="monotone" dataKey="equity" stroke="var(--accent)" strokeWidth={2.2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}

function HistoryLocked({ history, stats, onUpgrade, t }) {
  return (
    <div className="history-wrap">
      <MonthOverview history={history} stats={stats} t={t} />

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
    </div>
  )
}

export default function HistoryTable({ history, stats = null, isPremium = true, onUpgrade }) {
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
    return (
      <>
        <HistoryLocked history={history} stats={stats} onUpgrade={onUpgrade} t={t} />
        <HistoryStyles />
      </>
    )
  }

  return (
    <>
    <div className="history-wrap">
      <MonthOverview history={history} stats={stats} t={t} />
      <PnLChart history={rows} t={t} />

      <div className="history-table-wrap">
        <div className="hist-table-head">{t('hist.table.title')}</div>
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
    </div>
    <HistoryStyles />
    </>
  )
}

function HistoryStyles() {
  return (
    <style>{`
        .history-wrap { display: flex; flex-direction: column; gap: 14px; }
        .hist-month {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          padding: 22px; display: flex; flex-direction: column; gap: 18px;
          background-image:
            radial-gradient(ellipse 80% 60% at 100% 0%, color-mix(in srgb, var(--accent) 12%, transparent), transparent 55%);
        }
        .hist-month-top { display: flex; justify-content: space-between; align-items: center; gap: 20px; flex-wrap: wrap; }
        .hist-month-badge {
          display: inline-block; font-size: 10px; font-weight: 800; letter-spacing: 0.08em;
          text-transform: uppercase; color: var(--accent);
          background: color-mix(in srgb, var(--accent) 14%, transparent);
          border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--border));
          padding: 4px 10px; border-radius: 999px; margin-bottom: 8px;
        }
        .hist-month-title { font-family: var(--font-display); font-size: 22px; font-weight: 800; color: var(--text); margin: 0; }
        .hist-month-sub { font-size: 13px; color: var(--text-secondary); margin: 6px 0 0; max-width: 420px; line-height: 1.45; }
        .hist-kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
        .hist-kpi {
          border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
          background: var(--surface-2, var(--surface-hover));
          display: flex; flex-direction: column; gap: 4px;
        }
        .hist-kpi-label { font-size: 11px; color: var(--text-tertiary); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
        .hist-kpi-val { font-size: 22px; font-weight: 800; color: var(--text); line-height: 1.1; }
        .hist-kpi-hint { font-size: 11px; color: var(--text-tertiary); }
        .hist-equity {
          border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px 8px;
          background: color-mix(in srgb, var(--accent) 4%, var(--surface));
        }
        .hist-equity-head { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
        .hist-equity-head strong { font-family: var(--font-mono); font-size: 14px; }
        .pnl-chart-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          padding: 20px 20px 12px; display: flex; flex-direction: column; gap: 14px;
        }
        .pnl-chart-header { display: flex; justify-content: space-between; align-items: flex-start; }
        .pnl-chart-title { display: block; font-size: 14px; font-weight: 700; color: var(--text); font-family: var(--font-display); }
        .pnl-chart-sub { display: block; font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
        .pnl-total {
          font-family: var(--font-mono); font-size: 24px; font-weight: 700;
          display: flex; flex-direction: column; align-items: flex-end; gap: 2px;
        }
        .pnl-total-label { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
        .hist-lock-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          padding: 28px 24px; display: flex; flex-direction: column; align-items: center;
          gap: 12px; text-align: center;
        }
        .hist-lock-icon { font-size: 28px; }
        .hist-lock-title { font-size: 16px; font-weight: 700; color: var(--text); font-family: var(--font-display); }
        .hist-lock-feats { display: flex; flex-direction: column; gap: 8px; margin: 4px 0 6px; }
        .hist-lock-feat { font-size: 13px; color: var(--text-secondary); }
        .hist-lock-btn {
          background: var(--accent); color: #fff;
          border: none; border-radius: 10px; padding: 12px 28px;
          font-size: 14px; font-weight: 700; cursor: pointer;
        }
        .hist-lock-btn:hover { opacity: 0.9; }
        .hist-table-head {
          padding: 14px 18px 0; font-size: 13px; font-weight: 700; color: var(--text-secondary);
        }
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
        .pnl.pos, .pos { color: var(--long); }
        .pnl.neg, .neg { color: var(--short); }
        .history-cards { display: none; }
        @media (max-width: 900px) {
          .hist-kpi-grid { grid-template-columns: 1fr 1fr; }
        }
        @media (max-width: 680px) {
          .history-table { display: none; }
          .history-cards { display: flex; flex-direction: column; }
          .history-row-card { padding: 14px 16px; border-bottom: 1px solid var(--border); }
          .history-row-card:last-child { border-bottom: none; }
          .hrc-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
          .hrc-symbol-group { display: flex; align-items: center; gap: 8px; }
          .hrc-bottom { display: flex; justify-content: space-between; font-size: 12px; }
          .hist-month-top { flex-direction: column; align-items: flex-start; }
        }
    `}</style>
  )
}
