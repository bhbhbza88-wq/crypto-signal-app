import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid, BarChart, Bar, Cell } from 'recharts'

const ALL_PAIRS = [
  'BTC/USDT','ETH/USDT','SOL/USDT','BNB/USDT','XRP/USDT',
  'ADA/USDT','AVAX/USDT','DOT/USDT','ATOM/USDT','DOGE/USDT',
  'LINK/USDT','UNI/USDT','AAVE/USDT','ARB/USDT','OP/USDT',
  'FET/USDT','THETA/USDT','WLD/USDT','ICP/USDT',
  'SHIB/USDT','PEPE/USDT','FLOKI/USDT',
  'NEAR/USDT','ALGO/USDT','FIL/USDT','SAND/USDT','ENJ/USDT',
  'LTC/USDT','BCH/USDT','ETC/USDT','TRX/USDT',
  'SUI/USDT','APT/USDT','INJ/USDT','TIA/USDT','SEI/USDT',
  'HBAR/USDT','STX/USDT','VET/USDT',
]

const PERIODS = [
  { label: '1 месяц',   days: 30  },
  { label: '3 месяца',  days: 90  },
  { label: '6 месяцев', days: 180 },
  { label: '1 год',     days: 365 },
]

const RESULT_LABELS = { tp2: 'TP2 ✓', tp3: 'TP3 ✓', tp1: 'TP1 ✓', sl: 'Стоп', be: 'Б/У', timeout: 'Таймаут' }
const RESULT_COLORS = { tp1: 'var(--long)', tp2: 'var(--long)', tp3: 'var(--long)', sl: 'var(--short)', be: 'var(--text-secondary)', timeout: 'var(--amber)' }

function resolveBase() {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL
  return 'http://localhost:8000'
}

// ── Одиночный бэктест (результат) ─────────────────────────────
function SingleResult({ result, deposit }) {
  const pos = result.total_pnl > 0
  return (
    <div className="bt-results animate-in">
      <div className="bt-real-badge">
        <span className="bt-real-dot" />
        V8 (MTF+Pullback+Structure) · 30m · {result.candles_used} свечей · {result.symbol} · {result.period_days} дней
        <span style={{ marginLeft: 'auto', color: 'var(--text-tertiary)', fontSize: 11 }}>
          Комиссии: ${result.total_commission}
        </span>
      </div>
      <div className="bt-summary-grid">
        <div className="bt-stat-card main">
          <div className="bt-stat-label">Итоговый ROI</div>
          <div className={`bt-stat-val big ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{result.total_pnl}%</div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            ${Number(deposit).toLocaleString()} → ${result.final_equity.toLocaleString()}
          </div>
        </div>
        <div className="bt-stat-card">
          <div className="bt-stat-label">Винрейт</div>
          <div className={`bt-stat-val ${result.winrate >= 50 ? 'pos' : 'neg'}`}>{result.winrate}%</div>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{result.wins}W / {result.losses}L / {result.breakeven}БУ</div>
        </div>
        <div className="bt-stat-card">
          <div className="bt-stat-label">Макс. просадка</div>
          <div className="bt-stat-val neg">-{result.max_drawdown}%</div>
        </div>
        <div className="bt-stat-card">
          <div className="bt-stat-label">Профит-фактор</div>
          <div className={`bt-stat-val ${result.profit_factor >= 1.5 ? 'pos' : result.profit_factor >= 1 ? '' : 'neg'}`}>
            {result.profit_factor}
          </div>
        </div>
        <div className="bt-stat-card">
          <div className="bt-stat-label">Сделок</div>
          <div className="bt-stat-val">{result.total}</div>
        </div>
        <div className="bt-stat-card">
          <div className="bt-stat-label">Ср. Win / Loss</div>
          <div className="bt-stat-val pos">+${result.avg_win}</div>
          <div style={{ fontSize: 11, color: 'var(--short)' }}>−${Math.abs(result.avg_loss)}</div>
        </div>
      </div>

      {result.equity_curve?.length > 1 && (
        <div className="bt-chart-card">
          <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', marginBottom: 16 }}>Кривая доходности</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={result.equity_curve}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="day" tick={{ fill: 'var(--text-tertiary)', fontSize: 10 }} tickFormatter={v => `#${v}`} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'var(--text-tertiary)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} tickFormatter={v => `$${v.toLocaleString()}`} width={72} />
              <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, fontFamily: 'var(--font-mono)', fontSize: 12 }} formatter={v => [`$${v.toLocaleString()}`, 'Баланс']} />
              <ReferenceLine y={Number(deposit)} stroke="var(--text-tertiary)" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="equity" stroke={pos ? 'var(--long)' : 'var(--short)'} strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {result.trades?.length > 0 && <TradesList trades={result.trades} />}
    </div>
  )
}

// ── Мульти-бэктест (результат) ─────────────────────────────────
function MultiResult({ result }) {
  const s = result.summary
  const pos = s.total_pnl_pct > 0

  return (
    <div className="bt-results animate-in">
      <div className="bt-real-badge">
        <span className="bt-real-dot" />
        Все пары ({result.symbols_with_trades} из {result.symbols_tested}) · {result.period_days} дней
        <span style={{ marginLeft: 'auto', color: 'var(--text-tertiary)', fontSize: 11 }}>
          {s.trades_per_month} сделок/месяц
        </span>
      </div>

      {/* Сводка */}
      <div className="bt-summary-grid">
        <div className="bt-stat-card main">
          <div className="bt-stat-label">Суммарный PnL</div>
          <div className={`bt-stat-val big ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{s.total_pnl_pct}%</div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>по всем парам</div>
        </div>
        <div className="bt-stat-card">
          <div className="bt-stat-label">Всего сделок</div>
          <div className="bt-stat-val">{s.total_trades}</div>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{s.trades_per_month}/мес</div>
        </div>
        <div className="bt-stat-card">
          <div className="bt-stat-label">Винрейт</div>
          <div className={`bt-stat-val ${s.winrate >= 50 ? 'pos' : 'neg'}`}>{s.winrate}%</div>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{s.wins}W / {s.losses}L / {s.breakeven}БУ</div>
        </div>
        <div className="bt-stat-card">
          <div className="bt-stat-label">Профит-фактор</div>
          <div className={`bt-stat-val ${s.profit_factor >= 1.5 ? 'pos' : s.profit_factor >= 1 ? '' : 'neg'}`}>
            {s.profit_factor}
          </div>
        </div>
        <div className="bt-stat-card">
          <div className="bt-stat-label">Ср. PnL/сделку</div>
          <div className={`bt-stat-val ${s.avg_pnl_per_trade >= 0 ? 'pos' : 'neg'}`}>
            {s.avg_pnl_per_trade > 0 ? '+' : ''}{s.avg_pnl_per_trade}%
          </div>
        </div>
        <div className="bt-stat-card">
          <div className="bt-stat-label">Ср. просадка</div>
          <div className="bt-stat-val neg">-{s.avg_drawdown}%</div>
        </div>
      </div>

      {/* График PnL по парам */}
      {result.by_symbol?.length > 0 && (
        <div className="bt-chart-card">
          <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', marginBottom: 16 }}>PnL по парам</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={result.by_symbol} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barSize={16}>
              <XAxis dataKey="symbol" tick={{ fill: 'var(--text-tertiary)', fontSize: 9, fontFamily: 'var(--font-mono)' }}
                tickFormatter={v => v.replace('/USDT', '')} axisLine={false} tickLine={false} />
              <YAxis hide />
              <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, fontFamily: 'var(--font-mono)', fontSize: 12 }}
                formatter={v => [`${v > 0 ? '+' : ''}${v}%`, 'PnL']}
                labelFormatter={v => v} />
              <Bar dataKey="total_pnl_pct" radius={[4, 4, 0, 0]}>
                {result.by_symbol.map((entry, i) => (
                  <Cell key={i} fill={entry.total_pnl_pct >= 0 ? 'var(--long)' : 'var(--short)'} opacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Таблица по парам */}
      <div className="bt-chart-card">
        <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', marginBottom: 14 }}>По парам</h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Пара', 'Сделок', 'Винрейт', 'PnL%', 'Ср.PnL', 'Просадка', 'PF'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '8px 10px', color: 'var(--text-tertiary)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.by_symbol.map((r, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '9px 10px', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{r.symbol.replace('/USDT', '')}</td>
                  <td style={{ padding: '9px 10px', color: 'var(--text-secondary)' }}>{r.total}</td>
                  <td style={{ padding: '9px 10px', color: r.winrate >= 50 ? 'var(--long)' : 'var(--short)', fontFamily: 'var(--font-mono)' }}>{r.winrate}%</td>
                  <td style={{ padding: '9px 10px', color: r.total_pnl_pct >= 0 ? 'var(--long)' : 'var(--short)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                    {r.total_pnl_pct > 0 ? '+' : ''}{r.total_pnl_pct}%
                  </td>
                  <td style={{ padding: '9px 10px', color: r.avg_pnl_pct >= 0 ? 'var(--long)' : 'var(--short)', fontFamily: 'var(--font-mono)' }}>
                    {r.avg_pnl_pct > 0 ? '+' : ''}{r.avg_pnl_pct}%
                  </td>
                  <td style={{ padding: '9px 10px', color: 'var(--short)', fontFamily: 'var(--font-mono)' }}>-{r.max_drawdown}%</td>
                  <td style={{ padding: '9px 10px', color: r.profit_factor >= 1.5 ? 'var(--long)' : r.profit_factor >= 1 ? 'var(--text)' : 'var(--short)', fontFamily: 'var(--font-mono)' }}>{r.profit_factor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {result.all_trades?.length > 0 && <TradesList trades={result.all_trades} showSymbol />}
    </div>
  )
}

// ── Список сделок ──────────────────────────────────────────────
function TradesList({ trades, showSymbol }) {
  return (
    <div className="bt-trades-card">
      <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', marginBottom: 14 }}>
        Последние сделки
      </h3>
      <div className="bt-trades-list">
        {[...trades].reverse().slice(0, 50).map((t, i) => (
          <div key={i} className="bt-trade-row">
            <span style={{ color: 'var(--text-tertiary)', fontSize: 11, fontFamily: 'var(--font-mono)', width: 28 }}>#{i + 1}</span>
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4, fontFamily: 'var(--font-mono)',
              background: t.signal === 'LONG' ? 'var(--long-soft)' : 'var(--short-soft)',
              color: t.signal === 'LONG' ? 'var(--long)' : 'var(--short)',
            }}>{t.signal}</span>
            {showSymbol && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, width: 52 }}>
                {t.symbol?.replace('/USDT', '')}
              </span>
            )}
            <span style={{ fontSize: 11, color: 'var(--text-tertiary)', flex: 1 }}>{t.date} {t.time}</span>
            <span style={{ fontSize: 12, color: RESULT_COLORS[t.result] || 'var(--text-secondary)' }}>
              {RESULT_LABELS[t.result] || t.result}
            </span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700,
              color: t.pnl_pct > 0 ? 'var(--long)' : t.pnl_pct < 0 ? 'var(--short)' : 'var(--text-secondary)',
              width: 72, textAlign: 'right',
            }}>
              {t.pnl_pct > 0 ? '+' : ''}{t.pnl_pct}%
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)', width: 70, textAlign: 'right' }}>
              {t.pnl_usdt > 0 ? '+' : ''}${t.pnl_usdt}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Главный компонент ──────────────────────────────────────────
export default function Backtest() {
  const [mode, setMode] = useState('multi')   // 'single' | 'multi'
  const [pair, setPair] = useState('BTC/USDT')
  const [period, setPeriod] = useState(PERIODS[0])
  const [deposit, setDeposit] = useState(1000)
  const [commission, setCommission] = useState(0.055)
  const [slippage, setSlippage] = useState(0.05)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [progress, setProgress] = useState('')

  async function runBacktest() {
    setRunning(true)
    setResult(null)
    setError(null)

    try {
      if (mode === 'single') {
        setProgress(`Загружаю ${pair}...`)
        const res = await fetch(`${resolveBase()}/api/backtest`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol: pair,
            deposit: Number(deposit),
            period_days: period.days,
            commission: Number(commission),
            slippage: Number(slippage),
          }),
        })
        const data = await res.json()
        if (data.error) throw new Error(data.error)
        setResult({ type: 'single', data })
      } else {
        setProgress(`Тестирую все ${ALL_PAIRS.length} пар... это займёт 2–5 минут`)
        const res = await fetch(`${resolveBase()}/api/backtest/multi`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbols: [],   // пусто = все CANDIDATES
            deposit: Number(deposit),
            period_days: period.days,
            commission: Number(commission),
            slippage: Number(slippage),
          }),
        })
        const data = await res.json()
        if (data.error) throw new Error(data.error)
        setResult({ type: 'multi', data })
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
      setProgress('')
    }
  }

  return (
    <div className="bt-page animate-in">
      <div className="page-header" style={{ marginBottom: 20 }}>
        <h1 className="page-title">Бэктестинг</h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          V8 стратегия (MTF 4h+1h+30m, Pullback, Structure, ADX≥23)
        </p>
      </div>

      {/* Режим */}
      <div className="bt-mode-row">
        <button className={`bt-mode-btn ${mode === 'multi' ? 'active' : ''}`} onClick={() => { setMode('multi'); setResult(null) }}>
          <span className="btm-icon">🌐</span>
          <div>
            <div className="btm-title">Все пары ({ALL_PAIRS.length})</div>
            <div className="btm-sub">Тест по всем CANDIDATES — реальная картина</div>
          </div>
        </button>
        <button className={`bt-mode-btn ${mode === 'single' ? 'active' : ''}`} onClick={() => { setMode('single'); setResult(null) }}>
          <span className="btm-icon">🎯</span>
          <div>
            <div className="btm-title">Одна пара</div>
            <div className="btm-sub">Детальный анализ конкретного инструмента</div>
          </div>
        </button>
      </div>

      {/* Настройки */}
      <div className="bt-settings">
        {mode === 'single' && (
          <div className="bf-group">
            <label className="bf-label">Пара</label>
            <select className="bf-input" value={pair} onChange={e => setPair(e.target.value)}>
              {ALL_PAIRS.map(p => <option key={p}>{p}</option>)}
            </select>
          </div>
        )}
        <div className="bf-group">
          <label className="bf-label">Период</label>
          <div className="bf-toggle">
            {PERIODS.map(p => (
              <button key={p.days} className={`bft ${period.days === p.days ? 'active' : ''}`} onClick={() => setPeriod(p)}>{p.label}</button>
            ))}
          </div>
        </div>
        <div className="bf-group">
          <label className="bf-label">Депозит</label>
          <div className="bf-input-row">
            <input className="bf-input" type="number" value={deposit} onChange={e => setDeposit(e.target.value)} style={{ borderRadius: '7px 0 0 7px' }} />
            <span className="bf-unit">USDT</span>
          </div>
        </div>
        <button className="bt-run-btn" onClick={runBacktest} disabled={running}>
          {running ? '⟳ Считаю...' : mode === 'multi' ? '▶ Запустить по всем парам' : '▶ Запустить'}
        </button>
      </div>

      {/* Расширенные */}
      <div className="bt-advanced-wrap">
        <button className="bt-advanced-toggle" onClick={() => setShowAdvanced(v => !v)}>
          ⚙ Расширенные {showAdvanced ? '▲' : '▼'}
        </button>
        {showAdvanced && (
          <div className="bt-advanced animate-in">
            <div className="bf-group">
              <label className="bf-label">Комиссия %</label>
              <div className="bf-input-row">
                <input className="bf-input" type="number" step="0.001" value={commission} onChange={e => setCommission(e.target.value)} style={{ borderRadius: '7px 0 0 7px' }} />
                <span className="bf-unit">%</span>
              </div>
            </div>
            <div className="bf-group">
              <label className="bf-label">Проскальзывание %</label>
              <div className="bf-input-row">
                <input className="bf-input" type="number" step="0.01" value={slippage} onChange={e => setSlippage(e.target.value)} style={{ borderRadius: '7px 0 0 7px' }} />
                <span className="bf-unit">%</span>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="bt-info">
        <span>📡 Данные: Bybit</span>
        <span>⚙ Таймфрейм: 30m</span>
        <span>📅 {period.label}</span>
        <span>💸 Комиссия: {commission}% × 2</span>
        <span>⚙ ADX≥23 | Score≥13/20 | 💰 Риск 1.5%</span>
        {mode === 'multi' && <span>🌐 Пар: {ALL_PAIRS.length}</span>}
      </div>

      {error && <div className="bt-error animate-in">❌ {error}</div>}

      {running && (
        <div className="bt-loading animate-in">
          <div className="bt-spinner" />
          <div>
            <div style={{ fontWeight: 700, color: 'var(--text)' }}>{progress}</div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
              {mode === 'multi'
                ? 'Загружаю данные и прогоняю стратегию по всем парам — подожди 2–5 мин'
                : 'Прогоняю стратегию · комиссии и проскальзывание учтены'}
            </div>
          </div>
        </div>
      )}

      {result && !running && (
        result.type === 'single'
          ? <SingleResult result={result.data} deposit={deposit} />
          : <MultiResult result={result.data} />
      )}

      <style>{`
        .bt-page { max-width: 100%; }
        .bt-mode-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
        .bt-mode-btn {
          display: flex; align-items: center; gap: 14px;
          background: var(--surface); border: 2px solid var(--border);
          border-radius: var(--radius-lg); padding: 14px 18px;
          text-align: left; transition: all 0.2s; box-shadow: var(--shadow-card);
        }
        .bt-mode-btn:hover { border-color: var(--accent); }
        .bt-mode-btn.active { border-color: var(--accent); background: var(--accent-soft); }
        .btm-icon { font-size: 22px; flex-shrink: 0; }
        .btm-title { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 3px; }
        .btm-sub { font-size: 12px; color: var(--text-secondary); }
        .bt-mode-btn.active .btm-title { color: var(--accent); }

        .bt-settings {
          display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); padding: 20px; margin-bottom: 12px;
          box-shadow: var(--shadow-card);
        }
        .bt-settings .bf-group { flex: 1; min-width: 140px; }
        .bt-advanced-wrap { margin-bottom: 16px; }
        .bt-advanced-toggle { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; font-weight: 600; padding: 8px 16px; border-radius: 8px; transition: all 0.2s; }
        .bt-advanced-toggle:hover { border-color: var(--accent); color: var(--accent); }
        .bt-advanced { display: flex; gap: 20px; flex-wrap: wrap; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px 20px; margin-top: 8px; box-shadow: var(--shadow-card); }
        .bt-advanced .bf-group { flex: 1; min-width: 200px; }
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
        .bt-error { background: var(--short-soft); border: 1px solid var(--short); border-radius: var(--radius-md); padding: 14px 16px; color: var(--short); font-size: 13px; margin-bottom: 16px; }
        .bt-loading { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 32px; display: flex; align-items: center; gap: 20px; margin-bottom: 20px; }
        .bt-spinner { width: 36px; height: 36px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; flex-shrink: 0; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .bt-real-badge { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--long); font-weight: 600; padding: 8px 14px; background: var(--long-soft); border: 1px solid rgba(0,229,168,0.2); border-radius: 8px; margin-bottom: 16px; }
        .bt-real-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; flex-shrink: 0; }
        @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(0,229,168,0.4)} 70%{box-shadow:0 0 0 6px rgba(0,229,168,0)} 100%{box-shadow:0 0 0 0 rgba(0,229,168,0)} }
        .bt-results { display: flex; flex-direction: column; gap: 16px; }
        .bt-summary-grid { display: grid; grid-template-columns: repeat(6,1fr); gap: 12px; }
        .bt-stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px; box-shadow: var(--shadow-card); }
        .bt-stat-card.main { grid-column: span 2; background: var(--surface-hover); }
        .bt-stat-label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px; }
        .bt-stat-val { font-family: var(--font-mono); font-size: 22px; font-weight: 800; color: var(--text); margin-bottom: 4px; }
        .bt-stat-val.big { font-size: 32px; }
        .bt-stat-val.pos { color: var(--long); } .bt-stat-val.neg { color: var(--short); }
        .bt-chart-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px; box-shadow: var(--shadow-card); }
        .bt-trades-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px; box-shadow: var(--shadow-card); }
        .bt-trades-list { display: flex; flex-direction: column; }
        .bt-trade-row { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--border); }
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
        @media (max-width: 900px) { .bt-summary-grid { grid-template-columns: repeat(2,1fr); } .bt-stat-card.main { grid-column: span 2; } .bt-mode-row { grid-template-columns: 1fr; } }
        @media (max-width: 600px) { .bt-settings { flex-direction: column; } .bt-info { flex-direction: column; gap: 6px; } }
      `}</style>
    </div>
  )
}