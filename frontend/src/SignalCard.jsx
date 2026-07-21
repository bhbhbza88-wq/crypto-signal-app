import { useEffect, useRef, useState } from 'react'
import { createChart, ColorType, LineStyle, CrosshairMode } from 'lightweight-charts'
import { useI18n } from './i18n'

/** Где торгуется монета — для мелкой подписи на карточке. */
function formatListingsNote(listedOn, t) {
  const parts = String(listedOn || 'bybit')
    .split(',')
    .map(s => s.trim().toLowerCase())
    .filter(Boolean)
  const bybit = parts.includes('bybit')
  const binance = parts.includes('binance')
  if (bybit && binance) return t('signal.venuesBoth')
  if (binance && !bybit) return t('signal.venuesBinanceOnly')
  if (bybit && !binance) return t('signal.venuesBybitOnly')
  return t('signal.venuesDefault')
}

/** Живая цена с Bybit (linear → spot) или Binance futures. */
function useLiveSignalPrice(symbol, exchange = 'bybit', fallback = null) {
  const [price, setPrice] = useState(fallback)
  useEffect(() => {
    if (fallback != null) setPrice(fallback)
  }, [fallback])

  useEffect(() => {
    if (!symbol) return
    const raw = String(symbol).replace('/', '').toUpperCase()
    const ex = String(exchange || 'bybit').toLowerCase()
    let dead = false

    async function pull() {
      try {
        let p = null
        if (ex === 'binance') {
          const res = await fetch(`https://fapi.binance.com/fapi/v1/ticker/price?symbol=${raw}`)
          const data = await res.json()
          p = parseFloat(data?.price)
        } else {
          for (const category of ['linear', 'spot']) {
            const res = await fetch(
              `https://api.bybit.com/v5/market/tickers?category=${category}&symbol=${raw}`
            )
            const data = await res.json()
            p = parseFloat(data?.result?.list?.[0]?.lastPrice)
            if (Number.isFinite(p) && p > 0) break
            p = null
          }
        }
        if (!dead && Number.isFinite(p) && p > 0) setPrice(p)
      } catch {
        /* keep last */
      }
    }

    pull()
    const id = setInterval(pull, 5000)
    return () => { dead = true; clearInterval(id) }
  }, [symbol, exchange])

  return price
}

function ConfidenceBar({ score, maxScore = 20, t }) {
  const pct = Math.round((score / maxScore) * 100)
  const color = pct >= 80 ? 'var(--long)' : pct >= 60 ? 'var(--amber)' : 'var(--short)'
  const label = pct >= 80 ? t('signal.confHigh') : pct >= 60 ? t('signal.confMed') : t('signal.confLow')

  return (
    <div className="confidence-wrap">
      <div className="confidence-header">
        <span className="confidence-label">{t('signal.confidence')}</span>
        <span className="confidence-pct" style={{ color }}>{pct}%</span>
      </div>
      <div className="confidence-track">
        <div
          className="confidence-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <div className="confidence-footer">
        <span className="confidence-score">{t('signal.score', { score, max: maxScore })}</span>
        <span className="confidence-grade" style={{ color }}>{label} {t('signal.confSuffix')}</span>
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
function CandleChart({ signal, t, livePrice }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const lastBarRef = useRef(null)
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

    if (livePrice != null && data.length) {
      const last = data[data.length - 1]
      data[data.length - 1] = {
        ...last,
        close: livePrice,
        high: Math.max(last.high, livePrice),
        low: Math.min(last.low, livePrice),
      }
    }
    series.setData(data)
    lastBarRef.current = data[data.length - 1] || null

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
    addLine(signal.entry, cssVar('--accent', '#3b7cf4'), t('signal.entryLine'))
    addLine(signal.stop, cssVar('--short', '#f04a59'), 'SL')
    addLine(signal.tp1, cssVar('--long', '#00c896'), 'TP1')
    addLine(signal.tp2, cssVar('--long', '#00c896'), 'TP2', true)
    addLine(signal.tp3, cssVar('--long', '#00c896'), 'TP3', true)

    chartRef.current?.timeScale().fitContent()
    return () => { lines.forEach(l => { try { series.removePriceLine(l) } catch {} }) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(candles), signal.entry, signal.stop, signal.tp1, signal.tp2, signal.tp3, t])

  // тик live-цены без полной перерисовки
  useEffect(() => {
    const series = seriesRef.current
    const base = lastBarRef.current
    if (!series || livePrice == null || !base) return
    try {
      series.update({
        time: base.time,
        open: base.open,
        high: Math.max(base.high, livePrice),
        low: Math.min(base.low, livePrice),
        close: livePrice,
      })
    } catch { /* ignore */ }
  }, [livePrice])

  return <div ref={containerRef} className="tv-chart-canvas" />
}

export default function SignalCard({ signal, onNeedPremium }) {
  const { t } = useI18n()
  const isLong = signal.signal === 'LONG'
  const tone = isLong ? 'var(--long)' : 'var(--short)'
  const toneSoft = isLong ? 'var(--long-soft)' : 'var(--short-soft)'
  const sym = signal.symbol.replace('/USDT', '')
  const levelsLocked = !!signal.levels_locked
  // Premium Aggregator: confidence от техсканера нет; свечи с биржи трекинга
  const isAggregated = signal.trader?.source_type === 'telegram_aggregate'
  const exitTrail = signal.exit_mode === 'tp1_trail' || isAggregated
  const venuesNote = formatListingsNote(signal.listed_on || signal.exchange, t)

  const candles = signal.candles || []
  const lastClose = candles.length ? candles[candles.length - 1].close : null
  const livePrice = useLiveSignalPrice(
    signal.symbol,
    signal.exchange || 'bybit',
    signal.live_price ?? lastClose,
  )
  const displayPrice = livePrice ?? lastClose
  const livePnlPct = (!levelsLocked && displayPrice != null && signal.entry != null)
    ? (isLong ? (displayPrice - signal.entry) / signal.entry * 100 : (signal.entry - displayPrice) / signal.entry * 100)
    : null

  const stage = levelsLocked
    ? t('signal.stageLocked')
    : exitTrail && signal.tp1_hit
      ? t('signal.stageTrail')
      : signal.tp2_hit
        ? t('signal.stageTp2')
        : signal.tp1_hit
          ? t('signal.stageTp1')
          : t('signal.stageOpen')
  const pct = Math.round(((signal.score || 0) / 20) * 100)
  const confColor = pct >= 80 ? 'var(--long)' : pct >= 60 ? 'var(--amber)' : 'var(--short)'

  return (
    <div className={`signal-card ${levelsLocked ? 'levels-locked' : ''}`}>
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
            <span className="signal-pair">/ USDT</span>
            <div className="signal-venues">{venuesNote}</div>
          </div>
        </div>
        <div className="signal-meta">
          <MetaTag label={t('signal.mode')} value={isAggregated ? 'AI Scan' : signal.regime} />
          <MetaTag label={t('signal.stage')} value={stage} highlight={stage !== t('signal.stageOpen') && stage !== t('signal.stageLocked')} />
        </div>
      </div>

      {/* Шкала уверенности — только для сигналов техсканера. У Premium Aggregator
          Feed score принципиально нет (не наш алгоритм это оценивал). */}
      {!isAggregated && !levelsLocked && (
        <div className="confidence-section">
          <ConfidenceBar score={signal.score} maxScore={20} t={t} />
        </div>
      )}

      {/* TradingView-style свечной график */}
      <div className="tv-card">
        <div className="tv-chrome">
          <span className="tv-dot r" /><span className="tv-dot a" /><span className="tv-dot g" />
          <span className="tv-pair">{sym}/USDT</span>
          <span className="tv-live"><span className="tv-live-dot" />LIVE</span>
          {displayPrice != null && (
            <span className="tv-price">
              ${displayPrice < 1 ? displayPrice.toFixed(5) : displayPrice.toFixed(2)}
              {livePnlPct != null && (
                <span className={`tv-pnl ${livePnlPct >= 0 ? 'pos' : 'neg'}`}>
                  {livePnlPct >= 0 ? '▲' : '▼'}{Math.abs(livePnlPct).toFixed(2)}%
                </span>
              )}
            </span>
          )}
        </div>
        {candles.length > 0 ? (
          <CandleChart signal={signal} t={t} livePrice={displayPrice} />
        ) : (
          <div className="tv-empty">{t('signal.chartLoading')}</div>
        )}
        {levelsLocked ? (
          <div className="tv-locked">
            <div className="tv-locked-title">{t('signal.levelsLockedTitle')}</div>
            <div className="tv-locked-hint">{t('signal.levelsLockedHint')}</div>
            <button type="button" className="tv-locked-btn" onClick={() => onNeedPremium?.()}>
              {t('signal.levelsLockedCta')}
            </button>
          </div>
        ) : (
          <div className="tv-legend">
            <LegendChip color="var(--accent)" label={t('signal.legend.entry')} value={signal.entry} />
            <LegendChip color="var(--short)" label={t('signal.legend.sl')} value={signal.stop} />
            <LegendChip color="var(--long)" label={t('signal.legend.tp1')} value={signal.tp1} />
            {!exitTrail && (
              <>
                <LegendChip color="var(--long)" label={t('signal.legend.tp2')} value={signal.tp2} dashed />
                <LegendChip color="var(--long)" label={t('signal.legend.tp3')} value={signal.tp3} dashed />
              </>
            )}
            {exitTrail && <span className="tv-trail-note">{t('signal.trailNote')}</span>}
          </div>
        )}
      </div>

      {signal.position_size != null && !levelsLocked && (
        <div className="position-row">
          <span className="position-label">{t('signal.positionSize')}</span>
          <span className="position-value">{signal.position_size.toFixed(0)} USDT</span>
        </div>
      )}

      <style>{`
        .signal-card {
          background: color-mix(in srgb, var(--bg) 35%, var(--surface));
          border: 1px solid var(--border);
          border-radius: 12px;
          box-shadow: var(--inset-highlight);
          backdrop-filter: saturate(160%) blur(14px);
          overflow: hidden;
          transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s;
        }
        .signal-card:hover {
          border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
          box-shadow: var(--shadow-card);
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
          width: 44px; height: 44px; border-radius: 12px;
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0;
        }
        .signal-sym-row { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
        .symbol { font-size: 22px; font-weight: 700; color: var(--text); font-family: var(--font-mono); letter-spacing: -0.02em; }
        .signal-pair { font-size: 11px; color: var(--text-tertiary); }
        .signal-venues {
          margin-top: 2px;
          font-size: 10px;
          line-height: 1.3;
          color: var(--text-tertiary);
          opacity: 0.9;
        }
        .badge {
          font-size: 11px; font-weight: 700;
          padding: 4px 10px; border-radius: 8px;
          letter-spacing: 0.04em; font-family: var(--font-mono);
        }
        .signal-meta { display: flex; gap: 16px; }

        .confidence-section {
          padding: 0 22px 16px;
          border-bottom: 1px solid var(--border);
          margin-bottom: 4px;
        }

        .tv-card {
          margin: 14px 22px 18px; border: 1px solid var(--border); border-radius: var(--radius-md);
          overflow: hidden; background: color-mix(in srgb, var(--bg) 70%, transparent);
          box-shadow: var(--inset-highlight);
        }
        .tv-chrome {
          display: flex; align-items: center; gap: 7px; padding: 10px 12px;
          background: color-mix(in srgb, var(--surface-hover) 80%, transparent); border-bottom: 1px solid var(--border);
        }
        .tv-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; box-shadow: inset 0 0 0 .5px rgba(0,0,0,.15); }
        .tv-dot.r { background: #ff5f57; } .tv-dot.a { background: #febc2e; } .tv-dot.g { background: #28c840; }
        .tv-pair { font-size: 11px; font-family: var(--font-mono); font-weight: 650; color: var(--text-secondary); margin-left: 4px; }
        .tv-live { display: flex; align-items: center; gap: 4px; font-size: 9px; font-weight: 700; color: var(--long); text-transform: uppercase; letter-spacing: 0.06em; margin-left: 10px; }
        .tv-live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; }
        .tv-price { margin-left: auto; font-family: var(--font-mono); font-size: 12px; font-weight: 650; color: var(--text); display: flex; align-items: center; gap: 7px; }
        .tv-pnl { font-size: 11px; font-weight: 650; }
        .tv-pnl.pos { color: var(--long); } .tv-pnl.neg { color: var(--short); }
        .tv-chart-canvas { width: 100%; height: 240px; }
        .tv-empty { height: 240px; display: flex; align-items: center; justify-content: center; color: var(--text-tertiary); font-size: 12px; }
        .tv-legend { display: flex; flex-wrap: wrap; gap: 14px; padding: 10px 14px; border-top: 1px solid var(--border); background: color-mix(in srgb, var(--surface-hover) 70%, transparent); }
        .tv-trail-note { font-size: 11px; color: var(--text-tertiary); align-self: center; }
        .tv-locked { padding: 16px 14px 18px; text-align: center; border-top: 1px solid var(--border); background: color-mix(in srgb, var(--accent) 6%, transparent); }
        .tv-locked-title { font-size: 14px; font-weight: 650; color: var(--text); margin-bottom: 4px; }
        .tv-locked-hint { font-size: 12px; color: var(--text-secondary); margin-bottom: 12px; }
        .tv-locked-btn { border: none; border-radius: 980px; padding: 10px 18px; font-size: 13px; font-weight: 650; cursor: pointer; background: var(--accent); color: #fff; }

        .position-row {
          display: flex; justify-content: space-between; align-items: center;
          margin: 0 22px 18px;
          padding: 12px 14px;
          background: var(--accent-soft); border-radius: var(--radius-md);
          border: 1px solid color-mix(in srgb, var(--accent) 20%, transparent);
        }
        .position-label { font-size: 12px; color: var(--text-secondary); }
        .position-value { font-family: var(--font-mono); font-weight: 650; color: var(--accent); font-size: 14px; }
        .source-attribution { margin: 10px 0 0; font-size: 13px; color: var(--text); font-weight: 600; }

        @keyframes pulse { 0%{box-shadow:0 0 0 0 color-mix(in srgb, var(--long) 40%, transparent)} 70%{box-shadow:0 0 0 5px transparent} 100%{box-shadow:0 0 0 0 transparent} }

        @media (max-width: 480px) {
          .signal-header { padding: 16px 16px 0; }
          .signal-meta { gap: 12px; }
          .symbol { font-size: 20px; }
          .confidence-section { padding: 0 16px 14px; }
          .tv-card { margin: 12px 14px 14px; }
          .tv-chart-canvas { height: 210px; }
          .tv-legend { gap: 8px 12px; padding: 10px 12px; }
          .position-row { margin: 0 14px 14px; padding: 11px 12px; }
          .position-label { font-size: 11px; }
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
        .meta-label { font-size: 10px; color: var(--text-tertiary); font-family: var(--font-mono); }
        .meta-value { font-size: 12px; font-weight: 600; font-family: var(--font-mono); }
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
