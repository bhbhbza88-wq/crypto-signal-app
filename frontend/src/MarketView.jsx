const REGIME_LABELS = {
  UPTREND: 'Аптренд',
  DOWNTREND: 'Даунтренд',
  CHOP: 'Флэт/шум',
  FLAT: 'Без движения',
  'НЕТ ДАННЫХ': 'Нет данных',
}

const REGIME_COLORS = {
  UPTREND: { bg: 'var(--long-soft)', text: 'var(--long)' },
  DOWNTREND: { bg: 'var(--short-soft)', text: 'var(--short)' },
  CHOP: { bg: 'var(--surface-hover)', text: 'var(--text-secondary)' },
  FLAT: { bg: 'var(--surface-hover)', text: 'var(--text-tertiary)' },
  'НЕТ ДАННЫХ': { bg: 'var(--surface-hover)', text: 'var(--text-tertiary)' },
}

export default function MarketView({ market }) {
  if (!market) {
    return <div className="placeholder">Загрузка рынка...</div>
  }

  const btcColor = REGIME_COLORS[market.btc_regime] || REGIME_COLORS.CHOP
  const sorted = [...market.symbols].sort((a, b) => {
    const order = { UPTREND: 0, DOWNTREND: 1, CHOP: 2, FLAT: 3, 'НЕТ ДАННЫХ': 4 }
    return (order[a.regime] ?? 9) - (order[b.regime] ?? 9)
  })

  return (
    <div className="market-view">
      <div className="btc-card">
        <div className="btc-label">Режим BTC</div>
        <div className="btc-regime" style={{ color: btcColor.text }}>
          {REGIME_LABELS[market.btc_regime] || market.btc_regime}
        </div>
        <div className="btc-sub">
          Сигналы против режима BTC автоматически блокируются сканером
        </div>
      </div>

      <div className="market-summary">
        <SummaryChip label="В аптренде" value={market.uptrend_count} tone="long" />
        <SummaryChip label="В даунтренде" value={market.downtrend_count} tone="short" />
        <SummaryChip label="Без тренда" value={market.chop_count} tone="neutral" />
      </div>

      <div className="heatmap">
        {sorted.map((s) => {
          const colors = REGIME_COLORS[s.regime] || REGIME_COLORS.CHOP
          return (
            <div
              key={s.symbol}
              className="heatmap-cell"
              style={{ background: colors.bg, color: colors.text }}
              title={`${REGIME_LABELS[s.regime] || s.regime} · ADX ${s.adx}`}
            >
              <span className="cell-symbol">{s.symbol.replace('/USDT', '')}</span>
              <span className="cell-adx">ADX {s.adx}</span>
            </div>
          )
        })}
      </div>

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

        .market-summary {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
        }

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
  const bg = tone === 'long' ? 'var(--long-soft)' : tone === 'short' ? 'var(--short-soft)' : 'var(--surface-hover)'
  const color = tone === 'long' ? 'var(--long)' : tone === 'short' ? 'var(--short)' : 'var(--text-secondary)'
  return (
    <div className="summary-chip" style={{ background: bg, color }}>
      <span className="chip-value">{value}</span>
      <span className="chip-label">{label}</span>
      <style>{`
        .summary-chip {
          display: flex;
          align-items: baseline;
          gap: 6px;
          padding: 9px 14px;
          border-radius: 10px;
          font-size: 13px;
        }
        .chip-value { font-family: var(--font-mono); font-weight: 700; font-size: 16px; }
        .chip-label { font-size: 12px; opacity: 0.85; }
      `}</style>
    </div>
  )
}
