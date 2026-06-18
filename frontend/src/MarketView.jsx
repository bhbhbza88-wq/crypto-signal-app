import { useState, useEffect, useRef } from 'react'

const REGIME_LABELS = {
  UPTREND: 'Аптренд', DOWNTREND: 'Даунтренд',
  CHOP: 'Флэт', FLAT: 'Без движения', 'НЕТ ДАННЫХ': 'Нет данных',
}
const REGIME_COLORS = {
  UPTREND:      { bg: 'var(--long-soft)',     text: 'var(--long)' },
  DOWNTREND:    { bg: 'var(--short-soft)',    text: 'var(--short)' },
  CHOP:         { bg: 'var(--surface-hover)', text: 'var(--text-secondary)' },
  FLAT:         { bg: 'var(--surface-hover)', text: 'var(--text-tertiary)' },
  'НЕТ ДАННЫХ': { bg: 'var(--surface-hover)', text: 'var(--text-tertiary)' },
}

// Цвета иконок монет
const COIN_COLORS = {
  BTC: '#f7931a', ETH: '#627eea', BNB: '#f3ba2f', SOL: '#9945ff',
  XRP: '#00aae4', ADA: '#0033ad', AVAX: '#e84142', DOT: '#e6007a',
  ATOM: '#2e3148', SUI: '#4da2ff', APT: '#00c2ff', INJ: '#00c2ff',
  TIA: '#8b5cf6', SEI: '#9d4edd', UNI: '#ff007a', AAVE: '#b6509e',
  ARB: '#28a0f0', SHIB: '#e01c26', PEPE: '#4caf50', LTC: '#bfbbbb',
  BCH: '#8dc351', ETC: '#328332', FIL: '#0090ff', ICP: '#29abe2',
  STX: '#5546ff', FET: '#1c2d4e', WLD: '#000000', THETA: '#2ab8e6',
  VET: '#15bdff', LINK: '#2a5ada', OP: '#ff0420', HBAR: '#222222',
  TRX: '#eb0029',
}

function CoinIcon({ symbol, size = 32 }) {
  const sym = symbol.replace('/USDT', '')
  const color = COIN_COLORS[sym] || 'var(--accent)'
  const letter = sym.charAt(0)
  return (
    <div style={{
      width: size, height: size,
      borderRadius: '50%',
      background: color,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0,
      boxShadow: `0 2px 8px ${color}44`,
    }}>
      <span style={{
        color: '#fff', fontSize: size * 0.4,
        fontWeight: 700, fontFamily: 'var(--font-mono)',
      }}>{letter}</span>
    </div>
  )
}

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
      interval: '30', timezone: 'Europe/Moscow',
      theme: isDark ? 'dark' : 'light',
      style: '1', locale: 'ru',
      enable_publishing: false, hide_top_toolbar: false,
      save_image: false, calendar: false,
      support_host: 'https://www.tradingview.com',
      studies: ['RSI@tv-basicstudies', 'MASimple@tv-basicstudies'],
    })
    const container = document.createElement('div')
    container.style.height = '100%'
    container.style.width = '100%'
    containerRef.current.appendChild(container)
    containerRef.current.appendChild(script)
    return () => { if (containerRef.current) containerRef.current.innerHTML = '' }
  }, [symbol])
  return <div ref={containerRef} style={{ height: '100%', width: '100%' }} />
}

function CoinDetail({ coin, onClose }) {
  const sym = coin.symbol.replace('/USDT', '')
  const colors = REGIME_COLORS[coin.regime] || REGIME_COLORS.CHOP
  return (
    <div className="coin-detail">
      <div className="cd-header">
        <div className="cd-title">
          <CoinIcon symbol={coin.symbol} size={40} />
          <div>
            <div className="cd-sym-row">
              <span className="cd-sym">{sym}</span>
              <span className="cd-pair">/ USDT</span>
              <span className="cd-regime" style={{ background: colors.bg, color: colors.text }}>
                {REGIME_LABELS[coin.regime] || coin.regime}
              </span>
            </div>
            <span className="cd-exchange">Bybit · Spot</span>
          </div>
        </div>
        <button className="close-btn" onClick={onClose}>✕</button>
      </div>
      <div className="cd-stats">
        <StatChip label="ADX" value={coin.adx} />
        <StatChip label="Режим" value={REGIME_LABELS[coin.regime] || coin.regime} />
        <StatChip label="Биржа" value="Bybit" />
        <StatChip label="Пара" value={coin.symbol} />
      </div>
      <div style={{ height: 520 }}>
        <TradingViewChart symbol={coin.symbol} />
      </div>
      <style>{`
        .coin-detail {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card); overflow: hidden;
        }
        .cd-header {
          display: flex; justify-content: space-between; align-items: center;
          padding: 18px 20px; border-bottom: 1px solid var(--border);
          gap: 12px; flex-wrap: wrap;
        }
        .cd-title { display: flex; align-items: center; gap: 14px; }
        .cd-sym-row { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
        .cd-sym { font-family: var(--font-mono); font-size: 22px; font-weight: 700; color: var(--text); }
        .cd-pair { font-family: var(--font-mono); font-size: 14px; color: var(--text-tertiary); }
        .cd-regime { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 7px; }
        .cd-exchange { font-size: 11px; color: var(--text-tertiary); }
        .close-btn {
          border: 1px solid var(--border); background: var(--surface-hover);
          color: var(--text-secondary); width: 32px; height: 32px;
          border-radius: 8px; font-size: 14px; flex-shrink: 0;
          transition: background 0.15s;
        }
        .close-btn:hover { background: var(--short-soft); color: var(--short); }
        .cd-stats {
          display: flex; gap: 8px; padding: 14px 20px;
          border-bottom: 1px solid var(--border); flex-wrap: wrap;
        }
      `}</style>
    </div>
  )
}

function StatChip({ label, value }) {
  return (
    <div style={{
      background: 'var(--surface-hover)', padding: '8px 14px',
      borderRadius: 10, display: 'flex', flexDirection: 'column', gap: 2,
    }}>
      <span style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{value}</span>
    </div>
  )
}

const FILTERS = [
  { key: 'all',      label: 'Все' },
  { key: 'UPTREND',  label: 'Аптренд' },
  { key: 'DOWNTREND',label: 'Даунтренд' },
  { key: 'strong',   label: 'ADX > 30' },
]
const SORTS = [
  { key: 'regime', label: 'По тренду' },
  { key: 'adx',   label: 'По ADX' },
  { key: 'alpha', label: 'А–Я' },
]

export default function MarketView({ market }) {
  const [search, setSearch]         = useState('')
  const [selectedCoin, setSelectedCoin] = useState(null)
  const [filter, setFilter]         = useState('all')
  const [sort, setSort]             = useState('regime')

  if (!market) return <div className="placeholder">Загрузка рынка...</div>

  const btcColor = REGIME_COLORS[market.btc_regime] || REGIME_COLORS.CHOP

  let coins = [...market.symbols]

  // Фильтр
  if (filter === 'UPTREND')   coins = coins.filter(s => s.regime === 'UPTREND')
  if (filter === 'DOWNTREND') coins = coins.filter(s => s.regime === 'DOWNTREND')
  if (filter === 'strong')    coins = coins.filter(s => parseFloat(s.adx) > 30)

  // Поиск
  if (search.trim()) coins = coins.filter(s =>
    s.symbol.toLowerCase().includes(search.toLowerCase()) ||
    s.symbol.replace('/USDT', '').toLowerCase().includes(search.toLowerCase())
  )

  // Сортировка
  if (sort === 'regime') {
    const order = { UPTREND: 0, DOWNTREND: 1, CHOP: 2, FLAT: 3, 'НЕТ ДАННЫХ': 4 }
    coins.sort((a, b) => (order[a.regime] ?? 9) - (order[b.regime] ?? 9))
  } else if (sort === 'adx') {
    coins.sort((a, b) => parseFloat(b.adx) - parseFloat(a.adx))
  } else if (sort === 'alpha') {
    coins.sort((a, b) => a.symbol.localeCompare(b.symbol))
  }

  return (
    <div className="market-view">

      {/* BTC режим */}
      <div className="btc-card">
        <div className="btc-left">
          <CoinIcon symbol="BTC/USDT" size={44} />
          <div>
            <div className="btc-label">Режим BTC</div>
            <div className="btc-regime" style={{ color: btcColor.text }}>
              {REGIME_LABELS[market.btc_regime] || market.btc_regime}
            </div>
          </div>
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

      {/* Поиск + фильтры + сортировка */}
      <div className="controls">
        <div className="search-wrap">
          <span className="search-icon">⌕</span>
          <input
            className="search-input"
            type="text"
            placeholder="Поиск... BTC, ETH, SOL"
            value={search}
            onChange={e => { setSearch(e.target.value); setSelectedCoin(null) }}
          />
          {search && <button className="search-clear" onClick={() => setSearch('')}>✕</button>}
        </div>

        <div className="filter-sort-row">
          <div className="filter-group">
            {FILTERS.map(f => (
              <button
                key={f.key}
                className={`filter-btn ${filter === f.key ? 'active' : ''}`}
                onClick={() => { setFilter(f.key); setSelectedCoin(null) }}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="sort-group">
            <span className="sort-label">Сортировка:</span>
            {SORTS.map(s => (
              <button
                key={s.key}
                className={`sort-btn ${sort === s.key ? 'active' : ''}`}
                onClick={() => setSort(s.key)}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Детальный вид */}
      {selectedCoin && (
        <CoinDetail coin={selectedCoin} onClose={() => setSelectedCoin(null)} />
      )}

      {/* Heatmap */}
      {coins.length === 0 ? (
        <div className="placeholder">Монета не найдена</div>
      ) : (
        <div className="heatmap">
          {coins.map((s) => {
            const colors = REGIME_COLORS[s.regime] || REGIME_COLORS.CHOP
            const isSelected = selectedCoin?.symbol === s.symbol
            const sym = s.symbol.replace('/USDT', '')
            return (
              <div
                key={s.symbol}
                className={`heatmap-cell ${isSelected ? 'selected' : ''}`}
                style={{ background: colors.bg, borderColor: isSelected ? 'var(--accent)' : 'transparent' }}
                onClick={() => setSelectedCoin(isSelected ? null : s)}
              >
                <div className="cell-top">
                  <CoinIcon symbol={s.symbol} size={28} />
                  <div className="cell-info">
                    <span className="cell-symbol" style={{ color: colors.text }}>{sym}</span>
                    <span className="cell-adx" style={{ color: colors.text }}>ADX {s.adx}</span>
                  </div>
                </div>
                <span className="cell-regime" style={{ color: colors.text }}>
                  {REGIME_LABELS[s.regime] || s.regime}
                </span>
              </div>
            )
          })}
        </div>
      )}

      <style>{`
        .market-view { display: flex; flex-direction: column; gap: 14px; }

        .btc-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          padding: 20px 22px;
          display: flex; justify-content: space-between; align-items: center;
          flex-wrap: wrap; gap: 12px;
        }
        .btc-left { display: flex; align-items: center; gap: 14px; }
        .btc-label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
        .btc-regime { font-size: 26px; font-weight: 700; font-family: var(--font-mono); }
        .btc-sub { font-size: 12px; color: var(--text-tertiary); max-width: 280px; }

        .market-summary { display: flex; gap: 10px; flex-wrap: wrap; }

        /* ── CONTROLS ── */
        .controls { display: flex; flex-direction: column; gap: 10px; }
        .search-wrap { position: relative; display: flex; align-items: center; }
        .search-icon { position: absolute; left: 14px; font-size: 18px; color: var(--text-tertiary); pointer-events: none; }
        .search-input {
          width: 100%; padding: 11px 40px 11px 42px;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-md); color: var(--text);
          font-family: var(--font-ui); font-size: 14px; outline: none;
          transition: border-color 0.15s;
        }
        .search-input::placeholder { color: var(--text-tertiary); }
        .search-input:focus { border-color: var(--accent); }
        .search-clear { position: absolute; right: 12px; border: none; background: transparent; color: var(--text-tertiary); font-size: 13px; }
        .search-clear:hover { color: var(--text); }

        .filter-sort-row { display: flex; gap: 12px; flex-wrap: wrap; justify-content: space-between; }
        .filter-group { display: flex; gap: 6px; flex-wrap: wrap; }
        .filter-btn {
          border: 1px solid var(--border); background: var(--surface);
          color: var(--text-secondary); font-size: 12px; font-weight: 500;
          padding: 6px 14px; border-radius: 8px;
          transition: background 0.15s, color 0.15s, border-color 0.15s;
        }
        .filter-btn:hover { background: var(--surface-hover); color: var(--text); }
        .filter-btn.active { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); font-weight: 600; }

        .sort-group { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
        .sort-label { font-size: 11px; color: var(--text-tertiary); }
        .sort-btn {
          border: none; background: transparent;
          color: var(--text-tertiary); font-size: 12px; font-weight: 500;
          padding: 5px 10px; border-radius: 7px;
          transition: background 0.15s, color 0.15s;
        }
        .sort-btn:hover { background: var(--surface-hover); color: var(--text); }
        .sort-btn.active { background: var(--surface-hover); color: var(--text); font-weight: 600; }

        /* ── HEATMAP ── */
        .heatmap {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
          gap: 8px;
        }
        .heatmap-cell {
          padding: 12px; border-radius: 12px;
          display: flex; flex-direction: column; gap: 8px;
          cursor: pointer; border: 2px solid transparent;
          transition: transform 0.12s, border-color 0.15s, box-shadow 0.15s;
        }
        .heatmap-cell:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
        .heatmap-cell.selected { border-color: var(--accent) !important; transform: translateY(-2px); }
        .cell-top { display: flex; align-items: center; gap: 8px; }
        .cell-info { display: flex; flex-direction: column; gap: 1px; }
        .cell-symbol { font-family: var(--font-mono); font-weight: 700; font-size: 13px; }
        .cell-adx { font-family: var(--font-mono); font-size: 11px; opacity: 0.75; }
        .cell-regime { font-size: 10px; opacity: 0.8; text-transform: uppercase; letter-spacing: 0.04em; }

        .placeholder {
          padding: 30px; text-align: center; color: var(--text-tertiary); font-size: 13px;
          background: var(--surface); border: 1px dashed var(--border-strong);
          border-radius: var(--radius-lg);
        }
      `}</style>
    </div>
  )
}

function SummaryChip({ label, value, tone }) {
  const bg    = tone === 'long' ? 'var(--long-soft)'  : tone === 'short' ? 'var(--short-soft)'  : 'var(--surface-hover)'
  const color = tone === 'long' ? 'var(--long)'       : tone === 'short' ? 'var(--short)'       : 'var(--text-secondary)'
  return (
    <div style={{ background: bg, color, display: 'flex', alignItems: 'baseline', gap: 6, padding: '9px 14px', borderRadius: 10 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 16 }}>{value}</span>
      <span style={{ fontSize: 12, opacity: 0.85 }}>{label}</span>
    </div>
  )
}
