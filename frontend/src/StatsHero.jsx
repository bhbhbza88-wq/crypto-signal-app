import { useState, useEffect } from 'react'
import WinrateRing from './WinrateRing'

const PERIODS = [
  { key: 'today',    label: 'Сегодня' },
  { key: 'week',     label: 'Неделя' },
  { key: 'all_time', label: 'Всё время' },
]

// Иконки монет (emoji-fallback, работает везде)
const COIN_ICONS = {
  BTC: '₿', ETH: 'Ξ', BNB: 'B', SOL: '◎', XRP: '✕',
}

function useTicker() {
  const [ticker, setTicker] = useState(null)
  const [fearGreed, setFearGreed] = useState(null)

  useEffect(() => {
    async function fetchTicker() {
      try {
        const [btcRes, ethRes] = await Promise.all([
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT'),
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=ETHUSDT'),
        ])
        const btcData = await btcRes.json()
        const ethData = await ethRes.json()
        const btc = btcData?.result?.list?.[0]
        const eth = ethData?.result?.list?.[0]
        if (btc && eth) {
          setTicker({
            btc: {
              price: parseFloat(btc.lastPrice).toLocaleString('ru-RU', { maximumFractionDigits: 0 }),
              change: parseFloat(btc.price24hPcnt * 100).toFixed(2),
              positive: parseFloat(btc.price24hPcnt) >= 0,
            },
            eth: {
              price: parseFloat(ethData.result.list[0].lastPrice).toLocaleString('ru-RU', { maximumFractionDigits: 0 }),
              change: parseFloat(ethData.result.list[0].price24hPcnt * 100).toFixed(2),
              positive: parseFloat(ethData.result.list[0].price24hPcnt) >= 0,
            },
          })
        }
      } catch {}
    }

    async function fetchFearGreed() {
      try {
        const res = await fetch('https://api.alternative.me/fng/?limit=1')
        const data = await res.json()
        const val = data?.data?.[0]
        if (val) setFearGreed({ value: val.value, label: val.value_classification })
      } catch {}
    }

    fetchTicker()
    fetchFearGreed()
    const id = setInterval(fetchTicker, 30000)
    return () => clearInterval(id)
  }, [])

  return { ticker, fearGreed }
}

function FearGreedArc({ value }) {
  const size = 80
  const stroke = 7
  const radius = (size - stroke) / 2
  const circumference = Math.PI * radius
  const offset = circumference - (value / 100) * circumference
  const color = value >= 75 ? 'var(--long)' : value >= 45 ? 'var(--amber)' : 'var(--short)'
  const label = value >= 75 ? 'Жадность' : value >= 55 ? 'Умер. жадность' : value >= 45 ? 'Нейтрально' : value >= 25 ? 'Страх' : 'Макс. страх'

  return (
    <div className="fg-wrap">
      <svg width={size} height={size / 2 + 8} viewBox={`0 0 ${size} ${size / 2 + 8}`}>
        <path
          d={`M ${stroke / 2} ${size / 2} A ${radius} ${radius} 0 0 1 ${size - stroke / 2} ${size / 2}`}
          fill="none" stroke="var(--border)" strokeWidth={stroke} strokeLinecap="round"
        />
        <path
          d={`M ${stroke / 2} ${size / 2} A ${radius} ${radius} 0 0 1 ${size - stroke / 2} ${size / 2}`}
          fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="fg-center">
        <span className="fg-value" style={{ color }}>{value}</span>
        <span className="fg-label">{label}</span>
      </div>
      <style>{`
        .fg-wrap { position: relative; display: flex; flex-direction: column; align-items: center; }
        .fg-center { display: flex; flex-direction: column; align-items: center; margin-top: -8px; }
        .fg-value { font-family: var(--font-mono); font-size: 22px; font-weight: 700; line-height: 1; }
        .fg-label { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; margin-top: 2px; }
      `}</style>
    </div>
  )
}

export default function StatsHero({ stats }) {
  const [period, setPeriod] = useState('today')
  const { ticker, fearGreed } = useTicker()

  return (
    <div className="stats-wrap">

      {/* ── ТИКЕР BTC / ETH + Fear & Greed ── */}
      <div className="ticker-row">
        {ticker ? (
          <>
            <TickerCard icon="₿" name="Bitcoin" sym="BTC" price={ticker.btc.price} change={ticker.btc.change} positive={ticker.btc.positive} />
            <TickerCard icon="Ξ" name="Ethereum" sym="ETH" price={ticker.eth.price} change={ticker.eth.change} positive={ticker.eth.positive} />
          </>
        ) : (
          <>
            <div className="ticker-card skeleton" />
            <div className="ticker-card skeleton" />
          </>
        )}

        {fearGreed ? (
          <div className="ticker-card fg-card">
            <span className="ticker-name">Страх и жадность</span>
            <FearGreedArc value={parseInt(fearGreed.value)} />
          </div>
        ) : (
          <div className="ticker-card skeleton" />
        )}
      </div>

      {/* ── СТАТИСТИКА ТОРГОВЛИ ── */}
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

        {!stats ? (
          <div className="hero-skeleton" />
        ) : (() => {
          const data = stats[period]
          const pnlPositive = data.total_pnl > 0
          const pnlColor = data.total === 0
            ? 'var(--text-tertiary)'
            : pnlPositive ? 'var(--long)' : data.total_pnl < 0 ? 'var(--short)' : 'var(--text-secondary)'

          return (
            <>
              <div className="hero-body">
                <WinrateRing winrate={data.winrate} total={data.total} />
                <div className="hero-metrics">
                  <Metric label="Сделок" value={data.total} />
                  <Metric label="PnL" value={data.total === 0 ? '—' : `${pnlPositive ? '+' : ''}${data.total_pnl}%`} color={pnlColor} emphasis />
                  <Metric label="Средний PnL" value={data.total === 0 ? '—' : `${data.avg_pnl > 0 ? '+' : ''}${data.avg_pnl}%`} />
                </div>
              </div>

              {data.total > 0 && (
                <div className="hero-breakdown">
                  <BreakdownChip label="TP1"  value={data.tp1}       tone="long" />
                  <BreakdownChip label="TP2+" value={data.tp2_plus}  tone="long" />
                  <BreakdownChip label="Стоп" value={data.stops}     tone="short" />
                  <BreakdownChip label="Б/У"  value={data.breakeven} tone="neutral" />
                </div>
              )}
            </>
          )
        })()}
      </div>

      <style>{`
        .stats-wrap { display: flex; flex-direction: column; gap: 14px; }

        /* ── TICKER ROW ── */
        .ticker-row {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 12px;
        }
        .ticker-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-card);
          padding: 18px 20px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          transition: border-color 0.15s;
        }
        .ticker-card:hover { border-color: var(--border-strong); }
        .ticker-card.skeleton {
          min-height: 90px;
          background: var(--surface-hover);
          animation: shimmer 1.5s infinite;
        }
        @keyframes shimmer {
          0%,100% { opacity: 1; } 50% { opacity: 0.5; }
        }
        .ticker-top { display: flex; align-items: center; gap: 10px; }
        .ticker-icon {
          width: 36px; height: 36px;
          border-radius: 10px;
          background: var(--accent-soft);
          display: flex; align-items: center; justify-content: center;
          font-size: 18px; font-weight: 700;
          color: var(--accent);
          flex-shrink: 0;
        }
        .ticker-info { display: flex; flex-direction: column; gap: 1px; }
        .ticker-name { font-size: 11px; color: var(--text-tertiary); }
        .ticker-sym { font-size: 13px; font-weight: 700; color: var(--text); font-family: var(--font-mono); }
        .ticker-price { font-family: var(--font-mono); font-size: 22px; font-weight: 700; color: var(--text); }
        .ticker-change {
          font-family: var(--font-mono); font-size: 13px; font-weight: 600;
          display: flex; align-items: center; gap: 4px;
        }
        .fg-card { align-items: center; justify-content: center; gap: 4px; }

        /* ── STATS HERO ── */
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
        .hero-skeleton { min-height: 160px; }

        .period-switch {
          display: inline-flex;
          align-self: flex-start;
          background: var(--surface-hover);
          border-radius: 10px;
          padding: 3px;
          gap: 2px;
        }
        .period-btn {
          border: none; background: transparent;
          color: var(--text-secondary); font-size: 13px; font-weight: 500;
          padding: 7px 14px; border-radius: 8px;
          transition: background 0.15s, color 0.15s;
        }
        .period-btn.active {
          background: var(--surface); color: var(--text);
          box-shadow: 0 1px 2px rgba(20,20,15,0.08);
        }
        .period-btn:hover:not(.active) { color: var(--text); }

        .hero-body { display: flex; align-items: center; gap: 28px; flex-wrap: wrap; }
        .hero-metrics { display: flex; gap: 28px; flex-wrap: wrap; }
        .metric { display: flex; flex-direction: column; gap: 4px; }
        .metric-label { font-size: 12px; color: var(--text-tertiary); }
        .metric-value { font-family: var(--font-mono); font-size: 20px; font-weight: 600; }
        .metric-value.emphasis { font-size: 26px; }

        .hero-breakdown {
          display: flex; gap: 8px; flex-wrap: wrap;
          padding-top: 16px; border-top: 1px solid var(--border);
        }
        .breakdown-chip {
          display: flex; align-items: baseline; gap: 6px;
          padding: 7px 12px; border-radius: 9px; font-size: 13px;
        }
        .chip-val { font-family: var(--font-mono); font-weight: 600; }
        .chip-lbl { font-size: 12px; opacity: 0.85; }

        @media (max-width: 680px) {
          .ticker-row { grid-template-columns: 1fr 1fr; }
          .ticker-row > :last-child { grid-column: 1 / -1; }
        }
        @media (max-width: 400px) {
          .ticker-row { grid-template-columns: 1fr; }
          .ticker-row > :last-child { grid-column: auto; }
        }
      `}</style>
    </div>
  )
}

function TickerCard({ icon, name, sym, price, change, positive }) {
  return (
    <div className="ticker-card">
      <div className="ticker-top">
        <div className="ticker-icon">{icon}</div>
        <div className="ticker-info">
          <span className="ticker-name">{name}</span>
          <span className="ticker-sym">{sym}</span>
        </div>
      </div>
      <span className="ticker-price">${price}</span>
      <span className="ticker-change" style={{ color: positive ? 'var(--long)' : 'var(--short)' }}>
        {positive ? '▲' : '▼'} {Math.abs(change)}%
      </span>
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
  const bg    = tone === 'long' ? 'var(--long-soft)'  : tone === 'short' ? 'var(--short-soft)'  : 'var(--surface-hover)'
  const color = tone === 'long' ? 'var(--long)'       : tone === 'short' ? 'var(--short)'       : 'var(--text-secondary)'
  return (
    <div className="breakdown-chip" style={{ background: bg, color }}>
      <span className="chip-val">{value}</span>
      <span className="chip-lbl">{label}</span>
    </div>
  )
}
