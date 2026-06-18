import { useState } from 'react'
import WinrateRing from './WinrateRing'

const PERIODS = [
  { key: 'today', label: 'Сегодня' },
  { key: 'week', label: 'Неделя' },
  { key: 'all_time', label: 'Всё время' },
]

export default function StatsHero({ stats }) {
  const [period, setPeriod] = useState('today')

  if (!stats) {
    return (
      <div className="stats-hero skeleton">
        <style>{heroStyles}</style>
      </div>
    )
  }

  const data = stats[period]
  const pnlPositive = data.total_pnl > 0
  const pnlColor = data.total === 0 ? 'var(--text-tertiary)' : pnlPositive ? 'var(--long)' : data.total_pnl < 0 ? 'var(--short)' : 'var(--text-secondary)'

  return (
    <div className="stats-hero">
      <div className="period-switch">
        {PERIODS.map((p) => (
          <button
            key={p.key}
            className={`period-btn ${period === p.key ? 'active' : ''}`}
            onClick={() => setPeriod(p.key)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="hero-body">
        <WinrateRing winrate={data.winrate} total={data.total} />

        <div className="hero-metrics">
          <Metric label="Сделок" value={data.total} />
          <Metric
            label="PnL"
            value={data.total === 0 ? '—' : `${pnlPositive ? '+' : ''}${data.total_pnl}%`}
            color={pnlColor}
            emphasis
          />
          <Metric
            label="Средний PnL"
            value={data.total === 0 ? '—' : `${data.avg_pnl > 0 ? '+' : ''}${data.avg_pnl}%`}
          />
        </div>
      </div>

      {data.total > 0 && (
        <div className="hero-breakdown">
          <BreakdownChip label="TP1" value={data.tp1} tone="long" />
          <BreakdownChip label="TP2+" value={data.tp2_plus} tone="long" />
          <BreakdownChip label="Стоп" value={data.stops} tone="short" />
          <BreakdownChip label="Б/У" value={data.breakeven} tone="neutral" />
        </div>
      )}

      <style>{heroStyles}</style>
    </div>
  )
}

function Metric({ label, value, color, emphasis }) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <span className={`metric-value ${emphasis ? 'emphasis' : ''}`} style={{ color: color || 'var(--text)' }}>
        {value}
      </span>
    </div>
  )
}

function BreakdownChip({ label, value, tone }) {
  const bg = tone === 'long' ? 'var(--long-soft)' : tone === 'short' ? 'var(--short-soft)' : 'var(--surface-hover)'
  const color = tone === 'long' ? 'var(--long)' : tone === 'short' ? 'var(--short)' : 'var(--text-secondary)'
  return (
    <div className="breakdown-chip" style={{ background: bg, color }}>
      <span className="chip-value">{value}</span>
      <span className="chip-label">{label}</span>
    </div>
  )
}

const heroStyles = `
  .stats-hero {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-card);
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }
  .stats-hero.skeleton { min-height: 220px; }

  .period-switch {
    display: inline-flex;
    align-self: flex-start;
    background: var(--surface-hover);
    border-radius: 10px;
    padding: 3px;
    gap: 2px;
  }
  .period-btn {
    border: none;
    background: transparent;
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 500;
    padding: 7px 14px;
    border-radius: 8px;
    transition: background 0.15s, color 0.15s;
  }
  .period-btn.active {
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 1px 2px rgba(20,20,15,0.08);
  }
  .period-btn:hover:not(.active) { color: var(--text); }

  .hero-body {
    display: flex;
    align-items: center;
    gap: 28px;
    flex-wrap: wrap;
  }

  .hero-metrics {
    display: flex;
    gap: 28px;
    flex-wrap: wrap;
  }
  .metric { display: flex; flex-direction: column; gap: 4px; }
  .metric-label {
    font-size: 12px;
    color: var(--text-tertiary);
  }
  .metric-value {
    font-family: var(--font-mono);
    font-size: 20px;
    font-weight: 600;
  }
  .metric-value.emphasis { font-size: 26px; }

  .hero-breakdown {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }
  .breakdown-chip {
    display: flex;
    align-items: baseline;
    gap: 6px;
    padding: 7px 12px;
    border-radius: 9px;
    font-size: 13px;
  }
  .chip-value { font-family: var(--font-mono); font-weight: 600; }
  .chip-label { font-size: 12px; opacity: 0.85; }

  @media (max-width: 560px) {
    .hero-body { gap: 20px; }
    .hero-metrics { gap: 18px; }
  }
`
