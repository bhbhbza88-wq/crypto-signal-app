import { useState, useEffect } from 'react'
import WinrateRing from './WinrateRing'

const PERIODS = [
  { key: 'today',    label: 'Сегодня' },
  { key: 'week',     label: 'Неделя' },
  { key: 'all_time', label: 'Всё время' },
]

function useMarketData() {
  const [data, setData] = useState(null)
  const [fearGreed, setFearGreed] = useState(null)

  useEffect(() => {
    async function fetch_all() {
      try {
        const [btcRes, ethRes, globalRes] = await Promise.all([
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT'),
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=ETHUSDT'),
          fetch('https://api.coingecko.com/api/v3/global'),
        ])
        const btcData = await btcRes.json()
        const ethData = await ethRes.json()
        const globalData = await globalRes.json()

        const btc = btcData?.result?.list?.[0]
        const eth = ethData?.result?.list?.[0]
        const g = globalData?.data

        setData({
          btc: btc ? {
            price: parseFloat(btc.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }),
            change: (parseFloat(btc.price24hPcnt) * 100).toFixed(2),
            positive: parseFloat(btc.price24hPcnt) >= 0,
            volume: (parseFloat(btc.volume24h) * parseFloat(btc.lastPrice) / 1e9).toFixed(1),
          } : null,
          eth: eth ? {
            price: parseFloat(eth.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }),
            change: (parseFloat(eth.price24hPcnt) * 100).toFixed(2),
            positive: parseFloat(eth.price24hPcnt) >= 0,
          } : null,
          dominance: g ? parseFloat(g.market_cap_percentage?.btc).toFixed(1) : null,
          altseason: g ? Math.round(100 - parseFloat(g.market_cap_percentage?.btc)) : null,
          totalVolume: g ? (parseFloat(g.total_volume?.usd) / 1e9).toFixed(0) : null,
          marketCap: g ? (parseFloat(g.total_market_cap?.usd) / 1e12).toFixed(2) : null,
        })
      } catch {}

      try {
        const fgRes = await fetch('https://api.alternative.me/fng/?limit=1')
        const fgData = await fgRes.json()
        const val = fgData?.data?.[0]
        if (val) setFearGreed({ value: parseInt(val.value), label: val.value_classification })
      } catch {}
    }

    fetch_all()
    const id = setInterval(fetch_all, 60000)
    return () => clearInterval(id)
  }, [])

  return { data, fearGreed }
}

function FearGreedGauge({ value }) {
  const size = 90
  const stroke = 8
  const radius = (size - stroke) / 2
  const circumference = Math.PI * radius
  const offset = circumference - (value / 100) * circumference
  const color = value >= 75 ? 'var(--long)' : value >= 45 ? 'var(--amber)' : 'var(--short)'
  const label = value >= 75 ? 'Жадность' : value >= 55 ? 'Ум. жадность' : value >= 45 ? 'Нейтрально' : value >= 25 ? 'Страх' : 'Макс. страх'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <svg width={size} height={size / 2 + 10} viewBox={`0 0 ${size} ${size / 2 + 10}`}>
        <path d={`M ${stroke/2} ${size/2} A ${radius} ${radius} 0 0 1 ${size-stroke/2} ${size/2}`}
          fill="none" stroke="var(--border)" strokeWidth={stroke} strokeLinecap="round" />
        <path d={`M ${stroke/2} ${size/2} A ${radius} ${radius} 0 0 1 ${size-stroke/2} ${size/2}`}
          fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.8s ease' }} />
      </svg>
      <div style={{ textAlign: 'center', marginTop: -6 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
        <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>{label}</div>
      </div>
    </div>
  )
}

function TickerCard({ icon, name, sym, price, change, positive, extra }) {
  return (
    <div className="ticker-card animate-in">
      <div className="ticker-top">
        <div className="ticker-icon" style={{ background: sym === 'BTC' ? '#f7931a22' : '#627eea22' }}>
          <span style={{ fontSize: 18, color: sym === 'BTC' ? '#f7931a' : '#627eea' }}>{icon}</span>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{name}</div>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>{sym}/USDT</div>
        </div>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color: 'var(--text)' }}>${price}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: positive ? 'var(--long)' : 'var(--short)', display: 'flex', alignItems: 'center', gap: 3 }}>
          {positive ? '▲' : '▼'} {Math.abs(change)}%
        </span>
        {extra && <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{extra}</span>}
      </div>
    </div>
  )
}

function StatWidget({ label, value, sub, color, icon }) {
  return (
    <div className="stat-widget animate-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{ fontSize: 11, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</span>
        <span style={{ fontSize: 16 }}>{icon}</span>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color: color || 'var(--text)', marginTop: 8 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export default function StatsHero({ stats, loading }) {
  const [period, setPeriod] = useState('today')
  const { data, fearGreed } = useMarketData()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* ── ROW 1: BTC + ETH + Fear&Greed ── */}
      <div className="ticker-row">
        {data?.btc ? (
          <TickerCard icon="₿" name="Bitcoin" sym="BTC" price={data.btc.price} change={data.btc.change} positive={data.btc.positive} extra={`Vol $${data.btc.volume}B`} />
        ) : <div className="ticker-card skeleton" style={{ height: 120 }} />}

        {data?.eth ? (
          <TickerCard icon="Ξ" name="Ethereum" sym="ETH" price={data.eth.price} change={data.eth.change} positive={data.eth.positive} />
        ) : <div className="ticker-card skeleton" style={{ height: 120 }} />}

        <div className="ticker-card animate-in" style={{ alignItems: 'center', justifyContent: 'center', gap: 4 }}>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Страх и жадность</div>
          {fearGreed ? <FearGreedGauge value={fearGreed.value} /> : <div className="skeleton" style={{ width: 90, height: 60 }} />}
        </div>
      </div>

      {/* ── ROW 2: Market stats ── */}
      <div className="stats-row">
        {data?.dominance ? (
          <StatWidget label="BTC Доминация" value={`${data.dominance}%`} sub="Доля рынка" icon="₿" color="var(--amber)" />
        ) : <div className="stat-widget skeleton" style={{ height: 90 }} />}

        {data?.altseason !== null && data?.altseason !== undefined ? (
          <StatWidget
            label="Altcoin Season"
            value={`${data.altseason}%`}
            sub={data.altseason > 50 ? '🔥 Сезон альтов' : '😴 Сезон BTC'}
            icon="🌊"
            color={data.altseason > 50 ? 'var(--long)' : 'var(--text-secondary)'}
          />
        ) : <div className="stat-widget skeleton" style={{ height: 90 }} />}

        {data?.totalVolume ? (
          <StatWidget label="Объём рынка 24h" value={`$${data.totalVolume}B`} sub="Общий оборот" icon="📊" />
        ) : <div className="stat-widget skeleton" style={{ height: 90 }} />}

        {data?.marketCap ? (
          <StatWidget label="Капитализация" value={`$${data.marketCap}T`} sub="Весь крипторынок" icon="🌐" />
        ) : <div className="stat-widget skeleton" style={{ height: 90 }} />}
      </div>

      {/* ── TRADING STATS ── */}
      <div className="stats-hero-card animate-in">
        <div className="period-switch">
          {PERIODS.map((p) => (
            <button key={p.key} className={`period-btn ${period === p.key ? 'active' : ''}`} onClick={() => setPeriod(p.key)}>
              {p.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div style={{ display: 'flex', gap: 28, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
            <div className="skeleton" style={{ width: 132, height: 132, borderRadius: '50%' }} />
            <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
              {[80, 60, 100].map((w, i) => <div key={i} className="skeleton" style={{ width: w, height: 48 }} />)}
            </div>
          </div>
        ) : stats ? (() => {
          const d = stats[period]
          const pos = d.total_pnl > 0
          const pnlColor = d.total === 0 ? 'var(--text-tertiary)' : pos ? 'var(--long)' : 'var(--short)'
          return (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 28, flexWrap: 'wrap' }}>
                <WinrateRing winrate={d.winrate} total={d.total} />
                <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
                  <Metric label="Сделок" value={d.total} />
                  <Metric label="PnL" value={d.total === 0 ? '—' : `${pos ? '+' : ''}${d.total_pnl}%`} color={pnlColor} emphasis />
                  <Metric label="Средний PnL" value={d.total === 0 ? '—' : `${d.avg_pnl > 0 ? '+' : ''}${d.avg_pnl}%`} />
                </div>
              </div>
              {d.total > 0 && (
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                  <Chip label="TP1"  value={d.tp1}       tone="long" />
                  <Chip label="TP2+" value={d.tp2_plus}  tone="long" />
                  <Chip label="Стоп" value={d.stops}     tone="short" />
                  <Chip label="Б/У"  value={d.breakeven} tone="neutral" />
                </div>
              )}
            </>
          )
        })() : null}
      </div>

      <style>{`
        .ticker-row {
          display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
        }
        .ticker-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          padding: 18px 20px; display: flex; flex-direction: column; gap: 10px;
          transition: all 0.2s ease;
        }
        .ticker-card:hover { border-color: var(--border-strong); transform: translateY(-1px); box-shadow: var(--shadow-lg); }
        .ticker-top { display: flex; align-items: center; gap: 10px; }
        .ticker-icon { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }

        .stats-row {
          display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
        }
        .stat-widget {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          padding: 16px 18px;
          transition: all 0.2s ease;
        }
        .stat-widget:hover { border-color: var(--border-strong); transform: translateY(-1px); }

        .stats-hero-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          padding: 24px; display: flex; flex-direction: column; gap: 20px;
        }
        .period-switch {
          display: inline-flex; align-self: flex-start;
          background: var(--surface-hover); border-radius: 10px; padding: 3px; gap: 2px;
        }
        .period-btn {
          border: none; background: transparent; color: var(--text-secondary);
          font-size: 13px; font-weight: 500; padding: 7px 14px; border-radius: 8px;
          transition: all 0.2s;
        }
        .period-btn.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
        .period-btn:hover:not(.active) { color: var(--text); }

        @media (max-width: 900px) {
          .stats-row { grid-template-columns: repeat(2, 1fr); }
        }
        @media (max-width: 600px) {
          .ticker-row { grid-template-columns: 1fr 1fr; }
          .ticker-row > :last-child { grid-column: 1 / -1; }
          .stats-row { grid-template-columns: 1fr 1fr; }
        }
        @media (max-width: 400px) {
          .ticker-row { grid-template-columns: 1fr; }
          .ticker-row > :last-child { grid-column: auto; }
        }
      `}</style>
    </div>
  )
}

function Metric({ label, value, color, emphasis }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: emphasis ? 26 : 20, fontWeight: 600, color: color || 'var(--text)' }}>{value}</span>
    </div>
  )
}

function Chip({ label, value, tone }) {
  const bg    = tone === 'long' ? 'var(--long-soft)'  : tone === 'short' ? 'var(--short-soft)'  : 'var(--surface-hover)'
  const color = tone === 'long' ? 'var(--long)'       : tone === 'short' ? 'var(--short)'       : 'var(--text-secondary)'
  return (
    <div style={{ background: bg, color, display: 'flex', alignItems: 'baseline', gap: 6, padding: '7px 12px', borderRadius: 9 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{value}</span>
      <span style={{ fontSize: 12, opacity: 0.85 }}>{label}</span>
    </div>
  )
}
