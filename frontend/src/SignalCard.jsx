import { useEffect, useRef, useState } from 'react'
import { createChart, ColorType, LineStyle, CrosshairMode } from 'lightweight-charts'

function ConfidenceBar({ score, maxScore = 20 }) {
  const pct = Math.round((score / maxScore) * 100)
  const color = pct >= 80 ? 'var(--long)' : pct >= 60 ? 'var(--amber)' : 'var(--short)'
  const label = pct >= 80 ? 'Высокая' : pct >= 60 ? 'Средняя' : 'Низкая'

  return (
    <div className="confidence-wrap">
      <div className="confidence-header">
        <span className="confidence-label">Уверенность</span>
        <span className="confidence-pct" style={{ color }}>{pct}%</span>
      </div>
      <div className="confidence-track">
        <div
          className="confidence-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <div className="confidence-footer">
        <span className="confidence-score">Score {score}/{maxScore}</span>
        <span className="confidence-grade" style={{ color }}>{label} уверенность</span>
      </div>
      <style>{`
        .confidence-wrap { display: flex; flex-direction: column; gap: 6px; }
        .confidence-header { display: flex; justify-content: space-between; align-items: center; }
        .confidence-label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
        .confidence-pct { font-family: var(--font-mono); font-size: 20px; font-weight: 700; }
        .confidence-track {
          height: 6px; background: var(--surface-hover);
          border-radius: 3px; overflow: hidden;
        }
        .confidence-fill {
          height: 100%; border-radius: 3px;
          transition: width 0.6s ease;
        }
        .confidence-footer { display: flex; justify-content: space-between; }
        .confidence-score { font-size: 11px; color: var(--text-tertiary); font-family: var(--font-mono); }
        .confidence-grade { font-size: 11px; font-weight: 600; }
      `}</style>
    </div>
  )
}

// читает текущее значение CSS-переменной темы (реагирует на смену light/dark)
function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

function useThemeTick() {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const obs = new MutationObserver(() => setTick(t => t + 1))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [])
  return tick
}

// свечной график в стиле TradingView с разметкой Вход/SL/TP1-3
function CandleChart({ signal }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const themeTick = useThemeTick()

  const candles = signal.candles || []

  // создание графика (один раз)
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: cssVar('--text-tertiary', '#9aa0ad'),
        fontFamily: cssVar('--font-mono', 'monospace'),
        fontSize: 11,
      },
      grid: {
        vertLines: { color: cssVar('--border', '#e2e6ed') },
        horzLines: { color: cssVar('--border', '#e2e6ed') },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: cssVar('--border', '#e2e6ed') },
      timeScale: { borderColor: cssVar('--border', '#e2e6ed'), timeVisible: true, secondsVisible: false },
      handleScroll: false,
      handleScale: false,
    })
    chartRef.current = chart
    seriesRef.current = chart.addCandlestickSeries({
      upColor: cssVar('--long', '#00c896'),
      downColor: cssVar('--short', '#f04a59'),
      borderVisible: false,
      wickUpColor: cssVar('--long', '#00c896'),
      wickDownColor: cssVar('--short', '#f04a59'),
    })

    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) chart.resize(width, height)
    })
    ro.observe(containerRef.current)

    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; seriesRef.current = null }
  }, [])

  // перекраска при смене темы
  useEffect(() => {
    if (!chartRef.current) return
    chartRef.current.applyOptions({
      layout: { textColor: cssVar('--text-tertiary', '#9aa0ad') },
      grid: {
        vertLines: { color: cssVar('--border', '#e2e6ed') },
        horzLines: { color: cssVar('--border', '#e2e6ed') },
      },
      rightPriceScale: { borderColor: cssVar('--border', '#e2e6ed') },
      timeScale: { borderColor: cssVar('--border', '#e2e6ed') },
    })
    seriesRef.current?.applyOptions({
      upColor: cssVar('--long', '#00c896'),
      downColor: cssVar('--short', '#f04a59'),
      wickUpColor: cssVar('--long', '#00c896'),
      wickDownColor: cssVar('--short', '#f04a59'),
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [themeTick])

  // данные + линии уровней
  useEffect(() => {
    const series = seriesRef.current
    if (!series || candles.length === 0) return

    const seen = new Set()
    const data = candles
      .map(c => ({ time: Math.floor(c.timestamp / 1000), open: c.open, high: c.high, low: c.low, close: c.close }))
      .filter(d => { if (seen.has(d.time)) return false; seen.add(d.time); return true })
      .sort((a, b) => a.time - b.time)
    series.setData(data)

    const lines = []
    const addLine = (price, color, title, dashed) => {
      if (price == null) return
      lines.push(series.createPriceLine({
        price, color, title,
        lineWidth: dashed ? 1 : 2,
        lineStyle: dashed ? LineStyle.Dashed : LineStyle.Solid,
        axisLabelVisible: true,
      }))
    }
    addLine(signal.entry, cssVar('--accent', '#3b7cf4'), 'ВХОД')
    addLine(signal.stop, cssVar('--short', '#f04a59'), 'SL')
    addLine(signal.tp1, cssVar('--long', '#00c896'), 'TP1')
    addLine(signal.tp2, cssVar('--long', '#00c896'), 'TP2', true)
    addLine(signal.tp3, cssVar('--long', '#00c896'), 'TP3', true)

    chartRef.current?.timeScale().fitContent()
    return () => { lines.forEach(l => series.removePriceLine(l)) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(candles), signal.entry, signal.stop, signal.tp1, signal.tp2, signal.tp3])

  return <div ref={containerRef} className="tv-chart-canvas" />
}

export default function SignalCard({ signal }) {
  const isLong = signal.signal === 'LONG'
  const tone = isLong ? 'var(--long)' : 'var(--short)'
  const toneSoft = isLong ? 'var(--long-soft)' : 'var(--short-soft)'
  const sym = signal.symbol.replace('/USDT', '')
  // сигналы Premium Aggregator Feed не проходят через технический сканер:
  // score/candles у них принципиально нет (score=None, candles_json не заполняется
  // в open_signal при импорте из Telegram) — это не "недогрузка", а другой тип сигнала
  const isAggregated = signal.trader?.source_type === 'telegram_aggregate'

  const candles = signal.candles || []
  const lastClose = candles.length ? candles[candles.length - 1].close : null
  const livePnlPct = lastClose != null
    ? (isLong ? (lastClose - signal.entry) / signal.entry * 100 : (signal.entry - lastClose) / signal.entry * 100)
    : null

  const stage = signal.tp2_hit ? 'TP2 достигнут' : signal.tp1_hit ? 'TP1 достигнут' : 'Открыта'
  const pct = Math.round((signal.score / 20) * 100)
  const confColor = pct >= 80 ? 'var(--long)' : pct >= 60 ? 'var(--amber)' : 'var(--short)'

  return (
    <div className="signal-card">
      {/* Полоска уверенности сверху */}
      <div className="signal-confidence-stripe" style={{ background: `linear-gradient(90deg, ${confColor}22, transparent)`, borderTop: `3px solid ${confColor}` }} />

      <div className="signal-header">
        <div className="signal-title">
          <div className="signal-coin-icon" style={{ background: isLong ? 'var(--long-soft)' : 'var(--short-soft)' }}>
            <span style={{ color: tone, fontWeight: 800, fontSize: 14, fontFamily: 'var(--font-mono)' }}>
              {sym.charAt(0)}
            </span>
          </div>
          <div>
            <div className="signal-sym-row">
              <span className="symbol">{sym}</span>
              <span className="badge" style={{ background: toneSoft, color: tone }}>
                {signal.signal}
              </span>
            </div>
            <span className="signal-pair">/ USDT · Bybit</span>
          </div>
        </div>
        <div className="signal-meta">
          <MetaTag label="Режим" value={signal.regime} />
          <MetaTag label="Стадия" value={stage} highlight={stage !== 'Открыта'} />
        </div>
      </div>

      {/* Шкала уверенности — только для сигналов техсканера. У Premium Aggregator
          Feed score принципиально нет (не наш алгоритм это оценивал). */}
      {!isAggregated && (
        <div className="confidence-section">
          <ConfidenceBar score={signal.score} maxScore={20} />
        </div>
      )}

      {/* TradingView-style свечной график */}
      <div className="tv-card">
        <div className="tv-chrome">
          <span className="tv-dot r" /><span className="tv-dot a" /><span className="tv-dot g" />
          <span className="tv-pair">{sym}/USDT</span>
          <span className="tv-live"><span className="tv-live-dot" />LIVE</span>
          {lastClose != null && (
            <span className="tv-price">
              ${lastClose < 1 ? lastClose.toFixed(5) : lastClose.toFixed(2)}
              {livePnlPct != null && (
                <span className={`tv-pnl ${livePnlPct >= 0 ? 'pos' : 'neg'}`}>
                  {livePnlPct >= 0 ? '▲' : '▼'}{Math.abs(livePnlPct).toFixed(2)}%
                </span>
              )}
            </span>
          )}
        </div>
        {candles.length > 0 ? (
          <CandleChart signal={signal} />
        ) : isAggregated ? (
          <div className="tv-empty">График недоступен для сигналов внешнего потока</div>
        ) : (
          <div className="tv-empty">Загрузка графика...</div>
        )}
        <div className="tv-legend">
          <LegendChip color="var(--accent)" label="Вход" value={signal.entry} />
          <LegendChip color="var(--short)" label="SL" value={signal.stop} />
          <LegendChip color="var(--long)" label="TP1" value={signal.tp1} />
          <LegendChip color="var(--long)" label="TP2" value={signal.tp2} dashed />
          <LegendChip color="var(--long)" label="TP3" value={signal.tp3} dashed />
        </div>
      </div>

      {signal.position_size != null && (
        <div className="position-row">
          <span className="position-label">Рекомендованный размер позиции</span>
          <span className="position-value">{signal.position_size.toFixed(0)} USDT</span>
        </div>
      )}

      {signal.trader?.source_type === 'telegram_aggregate' ? (
        <div className="reasons-block">
          <span className="reasons-title">Источник</span>
          <p className="source-attribution">{signal.trader.name}</p>
        </div>
      ) : signal.entry_reasons?.length > 0 && (
        <div className="reasons-block">
          <span className="reasons-title">Почему сканер вошёл в сделку</span>
          <ul className="reasons-list">
            {signal.entry_reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      <style>{`
        .signal-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-card);
          overflow: hidden;
        }
        .signal-confidence-stripe { height: 3px; width: 100%; }
        .signal-header {
          display: flex; justify-content: space-between; align-items: flex-start;
          flex-wrap: wrap; gap: 12px;
          padding: 20px 22px 0;
          margin-bottom: 14px;
        }
        .signal-title { display: flex; align-items: center; gap: 12px; }
        .signal-coin-icon {
          width: 42px; height: 42px; border-radius: 12px;
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0;
        }
        .signal-sym-row { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
        .symbol { font-size: 22px; font-weight: 700; color: var(--text); font-family: var(--font-mono); letter-spacing: -0.01em; }
        .signal-pair { font-size: 11px; color: var(--text-tertiary); }
        .badge {
          font-size: 12px; font-weight: 600;
          padding: 4px 10px; border-radius: 7px;
          letter-spacing: 0.03em; font-family: var(--font-mono);
        }
        .signal-meta { display: flex; gap: 16px; }

        .confidence-section {
          padding: 0 22px 16px;
          border-bottom: 1px solid var(--border);
          margin-bottom: 4px;
        }

        /* TRADINGVIEW CARD */
        .tv-card { margin: 14px 22px 0; border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--bg); }
        .tv-chrome { display: flex; align-items: center; gap: 7px; padding: 9px 12px; background: var(--surface-hover); border-bottom: 1px solid var(--border); }
        .tv-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
        .tv-dot.r { background: var(--short); } .tv-dot.a { background: var(--amber); } .tv-dot.g { background: var(--long); }
        .tv-pair { font-size: 11px; font-family: var(--font-mono); font-weight: 700; color: var(--text-secondary); margin-left: 4px; }
        .tv-live { display: flex; align-items: center; gap: 4px; font-size: 9px; font-weight: 800; color: var(--long); text-transform: uppercase; letter-spacing: 0.06em; margin-left: 10px; }
        .tv-live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; }
        .tv-price { margin-left: auto; font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 7px; }
        .tv-pnl { font-size: 11px; font-weight: 700; }
        .tv-pnl.pos { color: var(--long); } .tv-pnl.neg { color: var(--short); }
        .tv-chart-canvas { width: 100%; height: 280px; }
        .tv-empty { height: 280px; display: flex; align-items: center; justify-content: center; color: var(--text-tertiary); font-size: 12px; }
        .tv-legend { display: flex; flex-wrap: wrap; gap: 14px; padding: 10px 14px; border-top: 1px solid var(--border); background: var(--surface-hover); }

        .position-row {
          display: flex; justify-content: space-between; align-items: center;
          margin: 14px 22px 0;
          padding: 12px 14px;
          background: var(--accent-soft); border-radius: 10px;
        }
        .position-label { font-size: 12px; color: var(--text-secondary); }
        .position-value { font-family: var(--font-mono); font-weight: 700; color: var(--accent); font-size: 14px; }
        .reasons-block {
          margin: 16px 22px 20px;
          padding-top: 14px;
          border-top: 1px solid var(--border);
        }
        .reasons-title {
          font-size: 12px; font-weight: 600; color: var(--text-secondary);
          text-transform: uppercase; letter-spacing: 0.04em;
        }
        .reasons-list {
          margin: 10px 0 0; padding-left: 18px;
          display: flex; flex-direction: column; gap: 6px;
        }
        .reasons-list li { font-size: 13px; color: var(--text); line-height: 1.4; }
        .source-attribution { margin: 10px 0 0; font-size: 13px; color: var(--text); font-weight: 600; }

        @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(0,229,168,0.4)} 70%{box-shadow:0 0 0 5px rgba(0,229,168,0)} 100%{box-shadow:0 0 0 0 rgba(0,229,168,0)} }

        /* На телефоне ужимаем боковые поля — иначе график зажат в 299px внутри 347px карточки */
        @media (max-width: 480px) {
          .signal-header { padding: 16px 16px 0; }
          .signal-meta { gap: 12px; }
          .symbol { font-size: 20px; }
          .confidence-section { padding: 0 16px 14px; }
          .tv-card { margin: 12px 14px 0; }
          .tv-chart-canvas { height: 240px; }
          .tv-legend { gap: 8px 12px; padding: 10px 12px; }
          .position-row { margin: 12px 14px 0; padding: 11px 12px; }
          .position-label { font-size: 11px; }
          .reasons-block { margin: 14px 16px 18px; }
        }
      `}</style>
    </div>
  )
}

function MetaTag({ label, value, highlight }) {
  return (
    <div className="meta-tag">
      <span className="meta-label">{label}</span>
      <span className="meta-value" style={{ color: highlight ? 'var(--amber)' : 'var(--text)' }}>{value}</span>
      <style>{`
        .meta-tag { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
        .meta-label { font-size: 10px; color: var(--text-tertiary); }
        .meta-value { font-size: 13px; font-weight: 600; font-family: var(--font-mono); }
      `}</style>
    </div>
  )
}

function LegendChip({ color, label, value, dashed }) {
  if (value == null) return null
  return (
    <div className="legend-chip">
      <span className="legend-swatch" style={{ background: dashed ? 'transparent' : color, border: dashed ? `1.5px dashed ${color}` : 'none' }} />
      <span className="legend-label">{label}</span>
      <span className="legend-value" style={{ color }}>{value.toFixed(4)}</span>
      <style>{`
        .legend-chip { display: flex; align-items: center; gap: 5px; }
        .legend-swatch { width: 10px; height: 3px; border-radius: 2px; flex-shrink: 0; }
        .legend-label { font-size: 10px; color: var(--text-tertiary); }
        .legend-value { font-size: 11px; font-weight: 700; font-family: var(--font-mono); }
      `}</style>
    </div>
  )
}
