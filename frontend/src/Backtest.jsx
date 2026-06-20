import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid } from 'recharts'

const PAIRS = [
  'BTC/USDT','ETH/USDT','SOL/USDT','BNB/USDT','XRP/USDT',
  'ADA/USDT','AVAX/USDT','DOT/USDT','ATOM/USDT','LINK/USDT',
  'ARB/USDT','SUI/USDT','INJ/USDT','LTC/USDT','ETC/USDT',
]
const TIMEFRAMES = [
  { label: '15m', value: '15m' },
  { label: '30m', value: '30m' },
  { label: '1h',  value: '1h'  },
  { label: '4h',  value: '4h'  },
]
const PERIODS = [
  { label: '1 месяц',   days: 30  },
  { label: '3 месяца',  days: 90  },
  { label: '6 месяцев', days: 180 },
  { label: '1 год',     days: 365 },
]

const RESULT_LABELS = { tp1: 'TP1', tp2: 'TP2+', sl: 'Стоп', be: 'Б/У', timeout: 'Таймаут' }
const RESULT_COLORS = { tp1: 'var(--long)', tp2: 'var(--long)', sl: 'var(--short)', be: 'var(--text-secondary)', timeout: 'var(--amber)' }

function resolveBase() {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL
  return 'http://localhost:8000'
}

export default function Backtest() {
  const [pair, setPair] = useState('BTC/USDT')
  const [timeframe, setTimeframe] = useState(TIMEFRAMES[2])
  const [period, setPeriod] = useState(PERIODS[0])
  const [deposit, setDeposit] = useState(1000)
  const [commission, setCommission] = useState(0.055)
  const [slippage, setSlippage] = useState(0.05)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [scannerMode, setScannerMode] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function runBacktest() {
    setRunning(true)
    setResult(null)
    setError(null)
    try {
      const res = await fetch(`${resolveBase()}/api/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: pair,
          timeframe: timeframe.value,
          deposit: Number(deposit),
          period_days: period.days,
          commission: Number(commission),
          slippage: Number(slippage),
          scanner_mode: scannerMode,
        }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || `Ошибка ${res.status}`)
      }
      const data = await res.json()
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  const pos = result?.total_pnl > 0

  return (
    <div className="bt-page animate-in">
      <div className="page-header" style={{marginBottom:20}}>
        <h1 className="page-title">Бэктестинг</h1>
        <p style={{fontSize:13,color:'var(--text-secondary)',marginTop:4}}>
          Реальная проверка стратегии сканера на исторических данных Bybit
        </p>
      </div>

      {/* Scanner mode toggle */}
      <div className="bt-scanner-mode">
        <button
          className={`bt-scanner-btn ${scannerMode ? 'active' : ''}`}
          onClick={() => { setScannerMode(v => !v); setResult(null) }}
        >
          <span className="bsm-icon">{scannerMode ? '🟢' : '⚪'}</span>
          <div>
            <div className="bsm-title">Режим сканера (1h + 4h)</div>
            <div className="bsm-sub">
              {scannerMode
                ? 'Активен — 1h основной таймфрейм, 4h подтверждение'
                : 'Выключен — используется выбранный таймфрейм'}
            </div>
          </div>
        </button>
      </div>

      {/* Settings */}
      <div className="bt-settings">
        <div className="bf-group">
          <label className="bf-label">Пара</label>
          <select className="bf-input" value={pair} onChange={e => setPair(e.target.value)}>
            {PAIRS.map(p => <option key={p}>{p}</option>)}
          </select>
        </div>
        <div className="bf-group" style={{opacity: scannerMode ? 0.4 : 1, pointerEvents: scannerMode ? 'none' : 'auto'}}>
          <label className="bf-label">Таймфрейм {scannerMode && <span style={{color:'var(--accent)'}}>— авто (30m)</span>}</label>
          <div className="bf-toggle">
            {TIMEFRAMES.map(tf => (
              <button key={tf.value} className={`bft ${timeframe.value === tf.value ? 'active' : ''}`}
                onClick={() => setTimeframe(tf)}>{tf.label}</button>
            ))}
          </div>
        </div>
        <div className="bf-group">
          <label className="bf-label">Период</label>
          <div className="bf-toggle">
            {PERIODS.map(p => (
              <button key={p.days} className={`bft ${period.days === p.days ? 'active' : ''}`}
                onClick={() => setPeriod(p)}>{p.label}</button>
            ))}
          </div>
        </div>
        <div className="bf-group">
          <label className="bf-label">Начальный депозит</label>
          <div className="bf-input-row">
            <input className="bf-input" type="number" value={deposit}
              onChange={e => setDeposit(e.target.value)} style={{borderRadius:'7px 0 0 7px'}} />
            <span className="bf-unit">USDT</span>
          </div>
        </div>
        <button className="bt-run-btn" onClick={runBacktest} disabled={running}>
          {running ? '⟳ Загружаю...' : '▶ Запустить'}
        </button>
      </div>

      {/* Advanced settings */}
      <div className="bt-advanced-wrap">
        <button className="bt-advanced-toggle" onClick={() => setShowAdvanced(v => !v)}>
          ⚙ Расширенные настройки {showAdvanced ? '▲' : '▼'}
        </button>
        {showAdvanced && (
          <div className="bt-advanced animate-in">
            <div className="bf-group">
              <label className="bf-label">Комиссия Bybit (% за сделку)</label>
              <div className="bf-input-row">
                <input className="bf-input" type="number" step="0.001" value={commission}
                  onChange={e => setCommission(e.target.value)} style={{borderRadius:'7px 0 0 7px'}} />
                <span className="bf-unit">%</span>
              </div>
              <span style={{fontSize:10,color:'var(--text-tertiary)',marginTop:3}}>
                Bybit taker = 0.055% · Учитывается дважды (вход + выход)
              </span>
            </div>
            <div className="bf-group">
              <label className="bf-label">Проскальзывание (% от цены)</label>
              <div className="bf-input-row">
                <input className="bf-input" type="number" step="0.01" value={slippage}
                  onChange={e => setSlippage(e.target.value)} style={{borderRadius:'7px 0 0 7px'}} />
                <span className="bf-unit">%</span>
              </div>
              <span style={{fontSize:10,color:'var(--text-tertiary)',marginTop:3}}>
                Реальная цена исполнения хуже на этот % · Обычно 0.03–0.1%
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="bt-info">
        <span>📡 Данные: реальные свечи Bybit</span>
        {scannerMode
          ? <span style={{color:'var(--long)',fontWeight:600}}>🟢 1h + 4h — режим сканера</span>
          : <span>⚙ Таймфрейм: {timeframe.label}</span>
        }
        <span>📅 Период: {period.label}</span>
        <span>💸 Комиссия: {commission}% × 2</span>
        <span>📉 Проскальзывание: {slippage}%</span>
        <span>💰 Риск: 1.5% депозита</span>
      </div>

      {/* Error */}
      {error && (
        <div className="bt-error animate-in">
          ❌ {error}
        </div>
      )}

      {/* Loading */}
      {running && (
        <div className="bt-loading animate-in">
          <div className="bt-spinner" />
          <div>
            <div style={{fontWeight:700,color:'var(--text)'}}>Загружаю данные с Bybit за {period.label}...</div>
            <div style={{fontSize:12,color:'var(--text-tertiary)',marginTop:4}}>
              Прогоняю стратегию · учитываю комиссии {commission}% и проскальзывание {slippage}% · подожди 15–60 сек
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {result && !running && (
        <div className="bt-results animate-in">

          {/* Real data badge */}
          <div className="bt-real-badge">
            <span className="bt-real-dot" />
            Реальные данные Bybit · {result.candles_used} свечей {result.timeframe} · {result.symbol} · {result.period_days} дней
            <span style={{marginLeft:'auto',color:'var(--text-tertiary)',fontSize:11}}>
              Комиссии: ${result.total_commission} · Проскальзывание: {result.slippage_pct}%
            </span>
          </div>

          {/* Summary cards */}
          <div className="bt-summary-grid">
            <div className="bt-stat-card main">
              <div className="bt-stat-label">Итоговый ROI</div>
              <div className={`bt-stat-val big ${pos ? 'pos' : 'neg'}`}>
                {pos ? '+' : ''}{result.total_pnl}%
              </div>
              <div style={{fontSize:12,color:'var(--text-tertiary)'}}>
                ${Number(deposit).toLocaleString()} → ${result.final_equity.toLocaleString()}
              </div>
            </div>
            <div className="bt-stat-card">
              <div className="bt-stat-label">Винрейт</div>
              <div className={`bt-stat-val ${result.winrate >= 50 ? 'pos' : 'neg'}`}>{result.winrate}%</div>
              <div style={{fontSize:11,color:'var(--text-tertiary)'}}>{result.wins}W / {result.losses}L / {result.breakeven}BE</div>
            </div>
            <div className="bt-stat-card">
              <div className="bt-stat-label">Макс. просадка</div>
              <div className="bt-stat-val neg">-{result.max_drawdown}%</div>
              <div style={{fontSize:11,color:'var(--text-tertiary)'}}>от пика</div>
            </div>
            <div className="bt-stat-card">
              <div className="bt-stat-label">Профит-фактор</div>
              <div className={`bt-stat-val ${result.profit_factor >= 1.5 ? 'pos' : result.profit_factor >= 1 ? '' : 'neg'}`}>
                {result.profit_factor}
              </div>
              <div style={{fontSize:11,color:'var(--text-tertiary)'}}>{'>'} 1.5 — отлично</div>
            </div>
            <div className="bt-stat-card">
              <div className="bt-stat-label">Сделок</div>
              <div className="bt-stat-val">{result.total}</div>
              <div style={{fontSize:11,color:'var(--text-tertiary)'}}>Ср. выигрыш: +${result.avg_win}</div>
            </div>
            <div className="bt-stat-card">
              <div className="bt-stat-label">Уплачено комиссий</div>
              <div className="bt-stat-val neg">${result.total_commission}</div>
              <div style={{fontSize:11,color:'var(--text-tertiary)'}}>{result.commission_pct}% × 2 за сделку</div>
            </div>
          </div>

          {/* Equity curve */}
          {result.equity_curve.length > 1 && (
            <div className="bt-chart-card">
              <h3 style={{fontSize:14,fontWeight:700,color:'var(--text)',marginBottom:16}}>
                Кривая доходности (реальная)
              </h3>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={result.equity_curve}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis
                    dataKey="day"
                    tick={{fill:'var(--text-tertiary)',fontSize:10}}
                    tickFormatter={v => `#${v}`}
                    axisLine={false} tickLine={false}
                  />
                  <YAxis
                    tick={{fill:'var(--text-tertiary)',fontSize:10,fontFamily:'var(--font-mono)'}}
                    axisLine={false} tickLine={false}
                    tickFormatter={v => `$${v.toLocaleString()}`}
                    width={72}
                  />
                  <Tooltip
                    contentStyle={{background:'var(--surface)',border:'1px solid var(--border)',borderRadius:10,fontFamily:'var(--font-mono)',fontSize:12}}
                    formatter={(v) => [`$${v.toLocaleString()}`, 'Баланс']}
                    labelFormatter={v => `Сделка #${v}`}
                  />
                  <ReferenceLine y={Number(deposit)} stroke="var(--text-tertiary)" strokeDasharray="4 4" />
                  <Line
                    type="monotone" dataKey="equity"
                    stroke={pos ? 'var(--long)' : 'var(--short)'}
                    strokeWidth={2.5} dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* No trades message */}
          {result.total === 0 && (
            <div className="bt-no-trades">
              <div style={{fontSize:32,marginBottom:12}}>🔍</div>
              <div style={{fontWeight:700,color:'var(--text)',marginBottom:8}}>Сделок не найдено</div>
              <div style={{fontSize:13,color:'var(--text-secondary)'}}>
                Стратегия не нашла входов на этом периоде. Попробуй другой таймфрейм или пару.
              </div>
            </div>
          )}

          {/* Last trades */}
          {result.trades.length > 0 && (
            <div className="bt-trades-card">
              <h3 style={{fontSize:14,fontWeight:700,color:'var(--text)',marginBottom:14}}>
                Последние сделки (реальные)
              </h3>
              <div className="bt-trades-list">
                {[...result.trades].reverse().map((t, i) => (
                  <div key={i} className="bt-trade-row">
                    <span style={{color:'var(--text-tertiary)',fontSize:11,fontFamily:'var(--font-mono)',width:32}}>#{i+1}</span>
                    <span style={{
                      fontSize:10,fontWeight:700,padding:'2px 7px',borderRadius:4,fontFamily:'var(--font-mono)',
                      background: t.signal==='LONG' ? 'var(--long-soft)' : 'var(--short-soft)',
                      color: t.signal==='LONG' ? 'var(--long)' : 'var(--short)',
                    }}>{t.signal}</span>
                    <span style={{fontSize:11,color:'var(--text-tertiary)',flex:1}}>{t.date} {t.time}</span>
                    <span style={{fontSize:12,color: RESULT_COLORS[t.result] || 'var(--text-secondary)'}}>
                      {RESULT_LABELS[t.result] || t.result}
                    </span>
                    <span style={{
                      fontFamily:'var(--font-mono)',fontSize:13,fontWeight:700,
                      color: t.pnl_pct > 0 ? 'var(--long)' : t.pnl_pct < 0 ? 'var(--short)' : 'var(--text-secondary)',
                      width:72,textAlign:'right'
                    }}>
                      {t.pnl_pct > 0 ? '+' : ''}{t.pnl_pct}%
                    </span>
                    <span style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-tertiary)',width:70,textAlign:'right'}}>
                      {t.pnl_usdt > 0 ? '+' : ''}${t.pnl_usdt}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <style>{`
        .bt-advanced-wrap { margin-bottom: 16px; }
        .bt-advanced-toggle { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; font-weight: 600; padding: 8px 16px; border-radius: 8px; transition: all 0.2s; }
        .bt-advanced-toggle:hover { border-color: var(--accent); color: var(--accent); }
        .bt-advanced { display: flex; gap: 20px; flex-wrap: wrap; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px 20px; margin-top: 8px; box-shadow: var(--shadow-card); }
        .bt-advanced .bf-group { flex: 1; min-width: 200px; }
        .bt-scanner-mode { margin-bottom: 12px; }
        .bt-scanner-btn {
          width: 100%; display: flex; align-items: center; gap: 14px;
          background: var(--surface); border: 2px solid var(--border);
          border-radius: var(--radius-lg); padding: 14px 18px;
          text-align: left; transition: all 0.2s; box-shadow: var(--shadow-card);
        }
        .bt-scanner-btn:hover { border-color: var(--accent); }
        .bt-scanner-btn.active { border-color: var(--long); background: var(--long-soft); }
        .bsm-icon { font-size: 22px; flex-shrink: 0; }
        .bsm-title { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 3px; }
        .bsm-sub { font-size: 12px; color: var(--text-secondary); }
        .bt-scanner-btn.active .bsm-title { color: var(--long); }
        .bt-page { max-width: 100%; }
        .bt-settings {
          display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); padding: 20px; margin-bottom: 12px;
          box-shadow: var(--shadow-card);
        }
        .bt-settings .bf-group { flex: 1; min-width: 140px; }
        .bt-info {
          display: flex; gap: 16px; flex-wrap: wrap;
          padding: 10px 16px; background: var(--surface-hover);
          border: 1px solid var(--border); border-radius: var(--radius-md);
          margin-bottom: 20px; font-size: 12px; color: var(--text-tertiary);
        }
        .bt-run-btn {
          padding: 10px 24px; background: linear-gradient(135deg, var(--accent), var(--purple));
          color: #fff; border: none; border-radius: 9px; font-size: 14px; font-weight: 700;
          box-shadow: 0 4px 14px rgba(77,140,245,0.35); transition: all 0.2s; white-space: nowrap; align-self: flex-end;
        }
        .bt-run-btn:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); }
        .bt-run-btn:disabled { opacity: 0.6; }
        .bt-error {
          background: var(--short-soft); border: 1px solid var(--short);
          border-radius: var(--radius-md); padding: 14px 16px;
          color: var(--short); font-size: 13px; margin-bottom: 16px;
        }
        .bt-loading {
          background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
          padding: 32px; display: flex; align-items: center; gap: 20px; margin-bottom: 20px;
        }
        .bt-spinner {
          width: 36px; height: 36px; border: 3px solid var(--border);
          border-top-color: var(--accent); border-radius: 50%;
          animation: spin 0.8s linear infinite; flex-shrink: 0;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .bt-real-badge {
          display: flex; align-items: center; gap: 8px;
          font-size: 12px; color: var(--long); font-weight: 600;
          padding: 8px 14px; background: var(--long-soft);
          border: 1px solid rgba(0,229,168,0.2); border-radius: 8px;
          margin-bottom: 16px;
        }
        .bt-real-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; flex-shrink: 0; }
        @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(0,229,168,0.4)} 70%{box-shadow:0 0 0 6px rgba(0,229,168,0)} 100%{box-shadow:0 0 0 0 rgba(0,229,168,0)} }
        .bt-results { display: flex; flex-direction: column; gap: 16px; }
        .bt-summary-grid { display: grid; grid-template-columns: repeat(6,1fr); gap: 12px; }
        .bt-stat-card {
          background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
          padding: 16px; box-shadow: var(--shadow-card);
        }
        .bt-stat-card.main { grid-column: span 2; background: var(--surface-hover); }
        .bt-stat-label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px; }
        .bt-stat-val { font-family: var(--font-mono); font-size: 22px; font-weight: 800; color: var(--text); margin-bottom: 4px; }
        .bt-stat-val.big { font-size: 32px; }
        .bt-stat-val.pos { color: var(--long); } .bt-stat-val.neg { color: var(--short); }
        .bt-chart-card {
          background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
          padding: 20px; box-shadow: var(--shadow-card);
        }
        .bt-no-trades {
          background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
          padding: 48px; text-align: center; box-shadow: var(--shadow-card);
        }
        .bt-trades-card {
          background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
          padding: 20px; box-shadow: var(--shadow-card);
        }
        .bt-trades-list { display: flex; flex-direction: column; }
        .bt-trade-row {
          display: flex; align-items: center; gap: 10px; padding: 9px 0;
          border-bottom: 1px solid var(--border);
        }
        .bt-trade-row:last-child { border-bottom: none; }
        .bf-group { display: flex; flex-direction: column; gap: 5px; }
        .bf-label { font-size: 11px; color: var(--text-secondary); font-weight: 500; }
        .bf-input { padding: 8px 12px; background: var(--surface-hover); border: 1px solid var(--border); border-radius: 7px; color: var(--text); font-size: 13px; font-family: var(--font-ui); outline: none; width: 100%; }
        .bf-input:focus { border-color: var(--accent); }
        .bf-input-row { display: flex; }
        .bf-input-row .bf-input { border-radius: 7px 0 0 7px; flex: 1; }
        .bf-unit { padding: 8px 10px; background: var(--surface-hover); border: 1px solid var(--border); border-left: none; border-radius: 0 7px 7px 0; font-size: 12px; color: var(--text-secondary); white-space: nowrap; display: flex; align-items: center; }
        .bf-toggle { display: flex; background: var(--surface-hover); border-radius: 7px; padding: 2px; gap: 2px; }
        .bft { flex: 1; padding: 5px 8px; border: none; background: transparent; color: var(--text-secondary); font-size: 12px; border-radius: 5px; transition: all 0.15s; }
        .bft.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-weight: 600; }
        @media (max-width: 900px) { .bt-summary-grid { grid-template-columns: repeat(2,1fr); } .bt-stat-card.main { grid-column: span 2; } }
        @media (max-width: 600px) { .bt-settings { flex-direction: column; } .bt-settings .bf-group { width: 100%; } .bt-info { flex-direction: column; gap: 6px; } }
      `}</style>
    </div>
  )
}