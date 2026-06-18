import { ComposedChart, Line, ReferenceLine, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

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

export default function SignalCard({ signal }) {
  const isLong = signal.signal === 'LONG'
  const tone = isLong ? 'var(--long)' : 'var(--short)'
  const toneSoft = isLong ? 'var(--long-soft)' : 'var(--short-soft)'
  const sym = signal.symbol.replace('/USDT', '')

  const chartData = (signal.candles || []).map((c) => ({
    time: new Date(c.timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }),
    close: c.close,
  }))

  const allLevels = [signal.entry, signal.stop, signal.tp1, signal.tp2, signal.tp3]
  const yMin = Math.min(...allLevels, ...chartData.map((d) => d.close)) * 0.998
  const yMax = Math.max(...allLevels, ...chartData.map((d) => d.close)) * 1.002

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

      {/* Шкала уверенности */}
      <div className="confidence-section">
        <ConfidenceBar score={signal.score} maxScore={20} />
      </div>

      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={chartData} margin={{ top: 8, right: 50, bottom: 0, left: 0 }}>
            <XAxis dataKey="time" tick={{ fill: 'var(--text-tertiary)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={{ stroke: 'var(--border)' }} tickLine={false} minTickGap={40} />
            <YAxis domain={[yMin, yMax]} tick={{ fill: 'var(--text-tertiary)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} width={0} />
            <Tooltip
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, fontFamily: 'var(--font-mono)', fontSize: 12, boxShadow: 'var(--shadow-card)' }}
              labelStyle={{ color: 'var(--text-secondary)' }}
              formatter={(v) => [v.toFixed(4), 'Цена']}
            />
            <ReferenceLine y={signal.entry} stroke="var(--accent)" strokeDasharray="4 4" label={{ value: 'Вход', position: 'right', fill: 'var(--accent)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
            <ReferenceLine y={signal.stop} stroke="var(--short)" label={{ value: 'SL', position: 'right', fill: 'var(--short)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
            <ReferenceLine y={signal.tp1} stroke="var(--long)" label={{ value: 'TP1', position: 'right', fill: 'var(--long)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
            <ReferenceLine y={signal.tp2} stroke="var(--long)" strokeDasharray="4 4" strokeOpacity={0.55} label={{ value: 'TP2', position: 'right', fill: 'var(--long)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
            <ReferenceLine y={signal.tp3} stroke="var(--long)" strokeDasharray="2 4" strokeOpacity={0.4} label={{ value: 'TP3', position: 'right', fill: 'var(--long)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
            <Line type="monotone" dataKey="close" stroke="var(--text)" strokeWidth={1.8} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="levels-row">
        <Level label="Вход" value={signal.entry} />
        <Level label="Стоп" value={signal.stop} tone="short" />
        <Level label="TP1" value={signal.tp1} tone="long" />
        <Level label="TP2" value={signal.tp2} tone="long" />
        <Level label="TP3" value={signal.tp3} tone="long" />
      </div>

      {signal.position_size != null && (
        <div className="position-row">
          <span className="position-label">Рекомендованный размер позиции</span>
          <span className="position-value">{signal.position_size.toFixed(0)} USDT</span>
        </div>
      )}

      {signal.entry_reasons?.length > 0 && (
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

        .chart-wrap { padding: 0 6px; margin-bottom: 8px; }
        .levels-row {
          display: flex; gap: 20px; flex-wrap: wrap;
          padding: 16px 22px;
          border-top: 1px solid var(--border);
        }
        .position-row {
          display: flex; justify-content: space-between; align-items: center;
          margin: 0 22px 16px;
          padding: 12px 14px;
          background: var(--accent-soft); border-radius: 10px;
        }
        .position-label { font-size: 12px; color: var(--text-secondary); }
        .position-value { font-family: var(--font-mono); font-weight: 700; color: var(--accent); font-size: 14px; }
        .reasons-block {
          margin: 0 22px 20px;
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

function Level({ label, value, tone }) {
  const color = tone === 'long' ? 'var(--long)' : tone === 'short' ? 'var(--short)' : 'var(--text)'
  return (
    <div className="level">
      <span className="level-label">{label}</span>
      <span className="level-value" style={{ color }}>{value?.toFixed(4)}</span>
      <style>{`
        .level { display: flex; flex-direction: column; gap: 3px; }
        .level-label { font-size: 11px; color: var(--text-tertiary); }
        .level-value { font-size: 14px; font-weight: 600; font-family: var(--font-mono); }
      `}</style>
    </div>
  )
}
