import { useState, useEffect, useRef } from 'react'

const REGIME_LABELS = {
  UPTREND: 'Аптренд',
  DOWNTREND: 'Даунтренд',
  CHOP: 'Флэт/шум',
  FLAT: 'Без движения',
  'НЕТ ДАННЫХ': 'Нет данных',
}

const REGIME_COLORS = {
  UPTREND:      { bg: 'var(--long-soft)',        text: 'var(--long)' },
  DOWNTREND:    { bg: 'var(--short-soft)',       text: 'var(--short)' },
  CHOP:         { bg: 'var(--surface-hover)',    text: 'var(--text-secondary)' },
  FLAT:         { bg: 'var(--surface-hover)',    text: 'var(--text-tertiary)' },
  'НЕТ ДАННЫХ': { bg: 'var(--surface-hover)',    text: 'var(--text-tertiary)' },
}

// TradingView виджет
function TradingViewChart({ symbol }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current) return
    containerRef.current.innerHTML = ''

    const isDark = document.documentElement.getAttribute('data-theme') === 'dark'

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.async = true
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: `BYBIT:${symbol.replace('/', '')}`,
      interval: '30',
      timezone: 'Europe/Moscow',
      theme: isDark ? 'dark' : 'light',
      style: '1',
      locale: 'ru',
      enable_publishing: false,
      hide_top_toolbar: false,
      hide_legend: false,
      save_image: false,
      calendar: false,
      support_host: 'https://www.tradingview.com',
      studies: ['RSI@tv-basicstudies', 'MASimple@tv-basicstudies'],
    })

    const container = document.createElement('div')
    container.className = 'tradingview-widget-container__widget'
    container.style.height = '100%'
    container.style.width = '100%'

    containerRef.current.appendChild(container)
    containerRef.current.appendChild(script)

    return () => {
      if (containerRef.current) containerRef.current.innerHTML = ''
    }
  }, [symbol])

  return (
    <div
      ref={containerRef}
      className="tradingview-widget-container"
      style={{ height: '100%', width: '100%' }}
    />
  )
}

// Панель с деталями монеты
function CoinDetail({ coin, onClose }) {
  const sym = coin.symbol.replace('/USDT', '')
  const colors = REGIME_COLORS[coin.regime] || REGIME_COLORS.CHOP

  return (
    <div className="coin-detail">
      <div className="coin-detail-header">
        <div className="coin-detail-title">
          <span className="coin-detail-sym">{sym}</span>
          <span className="coin-detail-pair">/ USDT</span>
          <span
            className="coin-regime-badge"
            style={{ background: colors.bg, color: colors.text }}
          >
            {REGIME_LABELS[coin.regime] || coin.regime}
          </span>
        </div>
        <button className="close-btn" onClick={onClose}>✕</button>
      </div>

      <div className="coin-stats-row">
        <StatChip label="ADX" value={coin.adx} />
        <StatChip label="Режим" value={REGIME_LABELS[coin.regime] || coin.regime} />
        <StatChip label="Биржа" value="Bybit" />
        <StatChip label="Пара" value={coin.symbol} />
      </div>

      <div className="chart-container">
        <TradingViewChart symbol={coin.symbol} />
      </div>

      <style>{`
        .coin-detail {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-card);
          overflow: hidden;
          display: flex;
          flex-direction: column;
          gap: 0;
        }
        .coin-detail-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 18px 20px;
          border-bottom: 1px solid var(--border);
          gap: 12px;
          flex-wrap: wrap;
        }
        .coin-detail-title {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .coin-detail-sym {
          font-family: var(--font-mono);
          font-size: 22px;
          font-weight: 700;
          color: var(--text);
        }
        .coin-detail-pair {
          font-family: var(--font-mono);
          font-size: 14px;
          color: var(--text-tertiary);
        }
        .coin-regime-badge {
          font-size: 12px;
          font-weight: 600;
          padding: 4px 10px;
          border-radius: 8px;
        }
        .close-btn {
          border: 1px solid var(--border);
          background: var(--surface-hover);
          color: var(--text-secondary);
          width: 32px; height: 32px;
          border-radius: 8px;
          font-size: 14px;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          transition: background 0.15s;
        }
        .close-btn:hover { background: var(--short-soft); color: var(--short); }

        .coin-stats-row {
          display: flex;
          gap: 8px;
          padding: 14px 20px;
          border-bottom: 1px solid var(--border);
          flex-wrap: wrap;
        }
        .chart-container {
          height: 520px;
          width: 100%;
        }
      `}</style>
    </div>
  )
}

function StatChip({ label, value }) {
  return (
    <div className="stat-chip">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      <style>{`
        .stat-chip {
          display: flex;
          flex-direction: column;
          gap: 2px;
          background: var(--surface-hover);
          padding: 8px 14px;
          border-radius: 10px;
        }
        .stat-label { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
        .stat-value { font-family: var(--font-mono); font-size: 13px; font-weight: 600; color: var(--text); }
      `}</style>
    </div>
  )
}

export default function MarketView({ market }) {
  const [search, setSearch] = useState('')
  const [selectedCoin, setSelectedCoin] = useState(null)

  if (!market) {
    return <div className="placeholder">Загрузка рынка...</div>
  }

  const btcColor = REGIME_COLORS[market.btc_regime] || REGIME_COLORS.CHOP

  const sorted = [...market.symbols].sort((a, b) => {
    const order = { UPTREND: 0, DOWNTREND: 1, CHOP: 2, FLAT: 3, 'НЕТ ДАННЫХ': 4 }
    return (order[a.regime] ?? 9) - (order[b.regime] ?? 9)
  })

  const filtered = search.trim()
    ? sorted.filter(s =>
        s.symbol.toLowerCase().includes(search.toLowerCase()) ||
        s.symbol.replace('/USDT', '').toLowerCase().includes(search.toLowerCase())
      )
    : sorted

  return (
    <div className="market-view">

      {/* BTC режим */}
      <div className="btc-card">
        <div className="btc-label">Режим BTC</div>
        <div className="btc-regime" style={{ color: btcColor.text }}>
          {REGIME_LABELS[market.btc_regime] || market.btc_regime}
        </div>
        <div className="btc-sub">
          Сигналы против режима BTC автоматически блокируются сканером
        </div>
      </div>

      {/* Сводка */}
      <div className="market-summary">
        <SummaryChip label="В аптренде"   value={market.uptrend_count}   tone="long" />
        <SummaryChip label="В даунтренде" value={market.downtrend_count} tone="short" />
        <SummaryChip label="Без тренда"   value={market.chop_count}      tone="neutral" />
      </div>

      {/* Поиск */}
      <div className="search-wrap">
        <span className="search-icon">⌕</span>
        <input
          className="search-input"
          type="text"
          placeholder="Поиск монеты... (BTC, ETH, SOL)"
          value={search}
          onChange={e => { setSearch(e.target.value); setSelectedCoin(null) }}
        />
        {search && (
          <button className="search-clear" onClick={() => setSearch('')}>✕</button>
        )}
      </div>

      {/* Детальный вид выбранной монеты */}
      {selectedCoin && (
        <CoinDetail
          coin={selectedCoin}
          onClose={() => setSelectedCoin(null)}
        />
      )}

      {/* Heatmap */}
      {filtered.length === 0 ? (
        <div className="placeholder">Монета не найдена</div>
      ) : (
        <div className="heatmap">
          {filtered.map((s) => {
            const colors = REGIME_COLORS[s.regime] || REGIME_COLORS.CHOP
            const isSelected = selectedCoin?.symbol === s.symbol
            return (
              <div
                key={s.symbol}
                className={`heatmap-cell ${isSelected ? 'selected' : ''}`}
                style={{ background: colors.bg, color: colors.text }}
                title={`${REGIME_LABELS[s.regime] || s.regime} · ADX ${s.adx}`}
                onClick={() => setSelectedCoin(isSelected ? null : s)}
              >
                <span className="cell-symbol">{s.symbol.replace('/USDT', '')}</span>
                <span className="cell-adx">ADX {s.adx}</span>
              </div>
            )
          })}
        </div>
      )}

      <style>{`
        .market-view { display: flex; flex-direction: column; gap: 16px; }

        .btc-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-card);
          padding: 22px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .btc-label { font-size: 12px; color: var(--text-tertiary); }
        .btc-regime { font-size: 28px; font-weight: 700; font-family: var(--font-mono); }
        .btc-sub { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; }

        .market-summary { display: flex; gap: 10px; flex-wrap: wrap; }

        /* Поиск */
        .search-wrap {
          position: relative;
          display: flex;
          align-items: center;
        }
        .search-icon {
          position: absolute;
          left: 14px;
          font-size: 18px;
          color: var(--text-tertiary);
          pointer-events: none;
        }
        .search-input {
          width: 100%;
          padding: 12px 40px 12px 42px;
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius-md);
          color: var(--text);
          font-family: var(--font-ui);
          font-size: 14px;
          outline: none;
          transition: border-color 0.15s;
        }
        .search-input::placeholder { color: var(--text-tertiary); }
        .search-input:focus { border-color: var(--accent); }
        .search-clear {
          position: absolute;
          right: 12px;
          border: none;
          background: transparent;
          color: var(--text-tertiary);
          font-size: 13px;
          padding: 4px;
          border-radius: 4px;
        }
        .search-clear:hover { color: var(--text); }

        /* Heatmap */
        .heatmap {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
          gap: 8px;
        }
        .heatmap-cell {
          padding: 12px 10px;
          border-radius: 10px;
          display: flex;
          flex-direction: column;
          gap: 4px;
          cursor: pointer;
          border: 2px solid transparent;
          transition: transform 0.1s, border-color 0.15s, opacity 0.15s;
        }
        .heatmap-cell:hover { transform: scale(1.04); opacity: 0.9; }
        .heatmap-cell.selected {
          border-color: var(--accent);
          transform: scale(1.04);
        }
        .cell-symbol { font-family: var(--font-mono); font-weight: 700; font-size: 14px; }
        .cell-adx { font-family: var(--font-mono); font-size: 11px; opacity: 0.8; }

        .placeholder {
          padding: 30px;
          text-align: center;
          color: var(--text-tertiary);
          font-size: 13px;
          background: var(--surface);
          border: 1px dashed var(--border-strong);
          border-radius: var(--radius-lg);
        }
      `}</style>
    </div>
  )
}

function SummaryChip({ label, value, tone }) {
  const bg    = tone === 'long' ? 'var(--long-soft)'   : tone === 'short' ? 'var(--short-soft)'  : 'var(--surface-hover)'
  const color = tone === 'long' ? 'var(--long)'        : tone === 'short' ? 'var(--short)'       : 'var(--text-secondary)'
  return (
    <div className="summary-chip" style={{ background: bg, color }}>
      <span className="chip-value">{value}</span>
      <span className="chip-label">{label}</span>
      <style>{`
        .summary-chip { display: flex; align-items: baseline; gap: 6px; padding: 9px 14px; border-radius: 10px; font-size: 13px; }
        .chip-value { font-family: var(--font-mono); font-weight: 700; font-size: 16px; }
        .chip-label { font-size: 12px; opacity: 0.85; }
      `}</style>
    </div>
  )
}
