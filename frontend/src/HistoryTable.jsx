import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from 'recharts'
import WinrateRing from './WinrateRing'
import { resultLabel, polishHistory, polishStats, buildShowcaseCurve, TG_RESULTS_CHANNEL } from './shared'
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
    <section className="hist-sec">
      <div className="dash-sec-head">
        <h2 className="dash-sec-title mono">{t('hist.chart.title')}</h2>
        <span className="hist-sec-meta mono">{t('hist.chart.sub', { n: data.length })}</span>
        <span className={`hist-chart-total mono ${positive ? 'pos' : 'neg'}`}>
          {positive ? '+' : ''}{totalPnl.toFixed(1)}%
        </span>
      </div>
      <div className="rs-card hist-chart-card">
        <div className="hist-chart-inner">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barSize={data.length > 20 ? 8 : 14}>
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
    </section>
  )
}

function MonthOverview({ history, stats, t }) {
  const polished = useMemo(() => polishHistory(history), [history])
  const display = useMemo(() => polishStats(stats, polished), [stats, polished])
  const curve = useMemo(() => buildShowcaseCurve(history), [history])
  const wins = polished.filter(tr => tr.pnl > 0).length
  const best = polished.reduce((b, tr) => (!b || tr.pnl > b.pnl ? tr : b), null)

  return (
    <div className="hist-overview">
      <div className="hist-overview-top">
        <div className="hist-overview-copy">
          <p className="hist-overview-sub">{t('hist.period.sub')}</p>
          <a className="hist-channel-link mono" href={TG_RESULTS_CHANNEL} target="_blank" rel="noopener noreferrer">
            {t('hist.channel.link')}
          </a>
        </div>
        <WinrateRing winrate={display.winrate} total={display.total} label={t('land.hero.statWinrate')} />
      </div>

      <div className="kpi-grid hist-kpi-grid">
        <div className="kpi-card accent">
          <div className="kpi-key mono">trades</div>
          <div className="kpi-val">{display.total}</div>
          <div className="kpi-meta">
            <span className="kpi-label">{t('hist.kpi.trades')}</span>
            <span className="kpi-sub">{t('hist.kpi.wins', { n: wins })}</span>
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-key mono">avg_pnl</div>
          <div className="kpi-val pos">+{display.avgPnl}%</div>
          <div className="kpi-meta">
            <span className="kpi-label">{t('hist.kpi.avg')}</span>
            <span className="kpi-sub">{t('hist.kpi.perTrade')}</span>
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-key mono">sum_pnl</div>
          <div className={`kpi-val ${display.totalPnl >= 0 ? 'pos' : 'neg'}`}>
            {display.totalPnl >= 0 ? '+' : ''}{display.totalPnl}%
          </div>
          <div className="kpi-meta">
            <span className="kpi-label">{t('hist.kpi.sum')}</span>
            <span className="kpi-sub">{t('hist.kpi.monthSum')}</span>
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-key mono">best</div>
          <div className="kpi-val pos">{best ? `+${best.pnl}%` : '—'}</div>
          <div className="kpi-meta">
            <span className="kpi-label">{t('hist.kpi.best')}</span>
            <span className="kpi-sub">
              {best ? String(best.symbol || '').replace('/USDT', '') : t('hist.kpi.noBest')}
            </span>
          </div>
        </div>
      </div>

      {curve.length > 1 && (
        <div className="rs-card hist-equity">
          <div className="rs-chrome">
            <span className="rs-prompt mono">{t('hist.equity.title')}</span>
            <strong className="mono pos">
              {curve[curve.length - 1]?.equity != null
                ? `+${curve[curve.length - 1].equity}%`
                : '—'}
            </strong>
          </div>
          <div className="hist-equity-chart">
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

      <div className="rs-card hist-lock-card">
        <div className="hist-lock-kicker mono">premium</div>
        <div className="hist-lock-title">{t('hist.locked.title')}</div>
        <div className="hist-lock-feats">
          {[t('hist.locked.f1'), t('hist.locked.f2'), t('hist.locked.f3')].map((f, i) => (
            <span key={i} className="hist-lock-feat">{f}</span>
          ))}
        </div>
        <button type="button" className="hist-lock-btn" onClick={onUpgrade}>{t('hist.locked.btn')}</button>
      </div>
    </div>
  )
}

export default function HistoryTable({ history, stats = null, isPremium = true, onUpgrade }) {
  const { t } = useI18n()
  const rows = useMemo(() => polishHistory(history), [history])

  if (!rows?.length) {
    return (
      <div className="history-empty rs-card">
        <span className="mono">{t('hist.empty')}</span>
        <style>{`
          .history-empty {
            padding: 36px 20px; text-align: center;
            color: var(--text-tertiary); font-size: 13px;
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

        <section className="hist-sec">
          <div className="dash-sec-head">
            <h2 className="dash-sec-title mono">{t('hist.table.title')}</h2>
            <span className="sec-count mono">{rows.length}</span>
          </div>
          <div className="rs-card history-table-wrap">
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
        </section>
      </div>
      <HistoryStyles />
    </>
  )
}

function HistoryStyles() {
  return (
    <style>{`
      .history-wrap { display: flex; flex-direction: column; gap: 22px; }
      .hist-overview { display: flex; flex-direction: column; gap: 16px; }
      .hist-overview-top {
        display: flex; justify-content: space-between; align-items: center;
        gap: 20px; flex-wrap: wrap;
      }
      .hist-overview-sub {
        margin: 0; font-size: 13px; line-height: 1.5;
        color: var(--text-secondary); max-width: 48ch;
      }
      .hist-channel-link {
        display: inline-block; margin-top: 10px; font-size: 12px; font-weight: 650;
        color: var(--accent); text-decoration: none;
      }
      .hist-channel-link:hover { text-decoration: underline; }

      .hist-sec { display: flex; flex-direction: column; gap: 0; }
      .hist-sec-meta { font-size: 11px; color: var(--text-tertiary); }
      .hist-chart-total { font-size: 13px; font-weight: 700; margin-left: auto; }
      .hist-chart-card { padding: 8px 10px 4px; }
      .hist-chart-inner { height: 148px; }

      .hist-equity { overflow: hidden; }
      .hist-equity .rs-chrome strong { font-size: 13px; }
      .hist-equity-chart { height: 72px; padding: 4px 10px 10px; }

      .hist-lock-card {
        padding: 28px 24px; display: flex; flex-direction: column; align-items: center;
        gap: 10px; text-align: center;
      }
      .hist-lock-kicker {
        font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
        color: var(--accent); background: var(--accent-soft);
        padding: 4px 10px; border-radius: 8px;
      }
      .hist-lock-title {
        font-size: 16px; font-weight: 700; color: var(--text);
        font-family: var(--font-display); letter-spacing: -0.02em;
      }
      .hist-lock-feats { display: flex; flex-direction: column; gap: 7px; margin: 4px 0 8px; }
      .hist-lock-feat {
        font-size: 13px; color: var(--text-secondary);
        padding: 8px 12px; border-radius: 10px;
        background: color-mix(in srgb, var(--bg) 45%, transparent);
        border: 1px solid var(--border);
      }
      .hist-lock-btn {
        background: var(--accent); color: #fff;
        border: none; border-radius: 10px; padding: 11px 24px;
        font-size: 13px; font-weight: 700; cursor: pointer;
      }
      .hist-lock-btn:hover { opacity: 0.92; }

      .history-table-wrap { overflow: hidden; }
      .history-table { width: 100%; border-collapse: collapse; font-size: 13px; display: table; }
      .history-table th {
        text-align: left; padding: 12px 16px;
        color: var(--text-tertiary); font-size: 10px;
        text-transform: uppercase; letter-spacing: 0.05em;
        font-weight: 650; border-bottom: 1px solid var(--border); white-space: nowrap;
        background: color-mix(in srgb, var(--surface-hover) 50%, transparent);
      }
      .history-table td {
        padding: 11px 16px; border-bottom: 1px solid var(--border);
        color: var(--text); white-space: nowrap;
      }
      .history-table tbody tr:last-child td { border-bottom: none; }
      .history-table tbody tr:hover { background: color-mix(in srgb, var(--bg) 40%, transparent); }
      .mono { font-family: var(--font-mono); }
      .dim { color: var(--text-secondary); }
      .symbol-cell { font-weight: 650; color: var(--text); }
      .dir-badge {
        font-size: 11px; font-weight: 650; padding: 3px 8px; border-radius: 6px;
        font-family: var(--font-mono);
      }
      .dir-badge.long { background: var(--long-soft); color: var(--long); }
      .dir-badge.short { background: var(--short-soft); color: var(--short); }
      .pnl.pos, .pos { color: var(--long); }
      .pnl.neg, .neg { color: var(--short); }
      .history-cards { display: none; }

      @media (max-width: 1100px) {
        .hist-kpi-grid { grid-template-columns: repeat(2, 1fr); }
      }
      @media (max-width: 680px) {
        .history-table { display: none; }
        .history-cards { display: flex; flex-direction: column; }
        .history-row-card { padding: 14px 16px; border-bottom: 1px solid var(--border); }
        .history-row-card:last-child { border-bottom: none; }
        .hrc-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
        .hrc-symbol-group { display: flex; align-items: center; gap: 8px; }
        .hrc-bottom { display: flex; justify-content: space-between; font-size: 12px; }
        .hist-overview-top { flex-direction: column; align-items: flex-start; }
      }
    `}</style>
  )
}
