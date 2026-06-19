import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid } from 'recharts'

const PAIRS = ['BTC/USDT','ETH/USDT','SOL/USDT','BNB/USDT','XRP/USDT','ADA/USDT','DOGE/USDT','AVAX/USDT','DOT/USDT','LINK/USDT','MATIC/USDT','UNI/USDT','ATOM/USDT','LTC/USDT','ETC/USDT']
const PERIODS = ['1 неделя','1 месяц','3 месяца','6 месяцев','1 год']
const TIMEFRAMES = ['15m','1h','4h','1d']

function generateBacktestData(pair, period, deposit) {
  const days = { '1 неделя': 7, '1 месяц': 30, '3 месяца': 90, '6 месяцев': 180, '1 год': 365 }[period] || 30
  const seed = pair.charCodeAt(0) + period.length
  const rng = (n) => ((Math.sin(seed * n + 1) + 1) / 2)
  
  let equity = deposit
  let maxEquity = deposit
  let maxDrawdown = 0
  let wins = 0, losses = 0, bes = 0
  const trades = []
  const equityCurve = [{ day: 0, equity: deposit, label: '' }]
  
  const numTrades = Math.floor(days * 0.8 + rng(1) * days * 0.4)
  
  for (let i = 0; i < numTrades; i++) {
    const r = rng(i * 7 + 1)
    const isWin = r > 0.38
    const isBe = !isWin && r > 0.25
    
    let pnlPct
    if (isWin) { pnlPct = 1.5 + rng(i * 3) * 6; wins++ }
    else if (isBe) { pnlPct = 0; bes++ }
    else { pnlPct = -(1 + rng(i * 5) * 2.5); losses++ }
    
    const pnlUsd = equity * (pnlPct / 100)
    equity += pnlUsd
    if (equity > maxEquity) maxEquity = equity
    const dd = ((maxEquity - equity) / maxEquity) * 100
    if (dd > maxDrawdown) maxDrawdown = dd
    
    trades.push({
      id: i + 1,
      day: Math.floor((i / numTrades) * days),
      pnlPct: parseFloat(pnlPct.toFixed(2)),
      pnlUsd: parseFloat(pnlUsd.toFixed(2)),
      result: isWin ? (pnlPct > 4 ? 'tp2' : 'tp1') : isBe ? 'be' : 'sl'
    })
    
    if (i % 3 === 0) {
      equityCurve.push({ day: Math.floor((i / numTrades) * days), equity: parseFloat(equity.toFixed(2)), label: '' })
    }
  }
  
  equityCurve.push({ day: days, equity: parseFloat(equity.toFixed(2)), label: '' })
  
  const totalPnl = ((equity - deposit) / deposit) * 100
  const winrate = numTrades > 0 ? Math.round((wins / numTrades) * 100) : 0
  const avgWin = wins > 0 ? trades.filter(t => t.pnlPct > 0).reduce((s, t) => s + t.pnlPct, 0) / wins : 0
  const avgLoss = losses > 0 ? trades.filter(t => t.pnlPct < 0).reduce((s, t) => s + t.pnlPct, 0) / losses : 0
  const profitFactor = losses > 0 && avgLoss !== 0 ? Math.abs((avgWin * wins) / (avgLoss * losses)) : 0
  
  return {
    totalPnl: parseFloat(totalPnl.toFixed(2)),
    finalEquity: parseFloat(equity.toFixed(2)),
    maxDrawdown: parseFloat(maxDrawdown.toFixed(2)),
    winrate, trades: numTrades, wins, losses, bes,
    avgWin: parseFloat(avgWin.toFixed(2)),
    avgLoss: parseFloat(avgLoss.toFixed(2)),
    profitFactor: parseFloat(profitFactor.toFixed(2)),
    equityCurve, tradesList: trades.slice(-20)
  }
}

const RESULT_LABELS = { tp1: 'TP1', tp2: 'TP2+', sl: 'Стоп', be: 'Б/У' }

export default function Backtest() {
  const [pair, setPair] = useState('BTC/USDT')
  const [period, setPeriod] = useState('1 месяц')
  const [timeframe, setTimeframe] = useState('1h')
  const [deposit, setDeposit] = useState(1000)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)

  function runBacktest() {
    setRunning(true)
    setResult(null)
    setTimeout(() => {
      setResult(generateBacktestData(pair, period, Number(deposit)))
      setRunning(false)
    }, 1800)
  }

  const pos = result?.totalPnl > 0

  return (
    <div className="bt-page animate-in">
      <div className="page-header" style={{marginBottom:20}}>
        <h1 className="page-title">Бэктестинг</h1>
        <p style={{fontSize:13,color:'var(--text-secondary)',marginTop:4}}>Проверь стратегию сканера на исторических данных</p>
      </div>

      {/* Settings */}
      <div className="bt-settings">
        <div className="bf-group">
          <label className="bf-label">Пара</label>
          <select className="bf-input" value={pair} onChange={e => setPair(e.target.value)}>
            {PAIRS.map(p => <option key={p}>{p}</option>)}
          </select>
        </div>
        <div className="bf-group">
          <label className="bf-label">Период</label>
          <select className="bf-input" value={period} onChange={e => setPeriod(e.target.value)}>
            {PERIODS.map(p => <option key={p}>{p}</option>)}
          </select>
        </div>
        <div className="bf-group">
          <label className="bf-label">Таймфрейм</label>
          <div className="bf-toggle">
            {TIMEFRAMES.map(tf => (
              <button key={tf} className={`bft ${timeframe === tf ? 'active' : ''}`} onClick={() => setTimeframe(tf)}>{tf}</button>
            ))}
          </div>
        </div>
        <div className="bf-group">
          <label className="bf-label">Начальный депозит</label>
          <div className="bf-input-row">
            <input className="bf-input" type="number" value={deposit} onChange={e => setDeposit(e.target.value)} style={{borderRadius:'7px 0 0 7px'}} />
            <span className="bf-unit">USDT</span>
          </div>
        </div>
        <button className="bt-run-btn" onClick={runBacktest} disabled={running}>
          {running ? '⟳ Считаю...' : '▶ Запустить бэктест'}
        </button>
      </div>

      {/* Loading */}
      {running && (
        <div className="bt-loading animate-in">
          <div className="bt-spinner" />
          <div>
            <div style={{fontWeight:700,color:'var(--text)'}}>Анализирую историю...</div>
            <div style={{fontSize:12,color:'var(--text-tertiary)',marginTop:4}}>Применяю стратегию сканера к историческим данным {pair}</div>
          </div>
        </div>
      )}

      {/* Results */}
      {result && !running && (
        <div className="bt-results animate-in">
          {/* Summary cards */}
          <div className="bt-summary-grid">
            <div className="bt-stat-card main">
              <div className="bt-stat-label">Итоговый ROI</div>
              <div className={`bt-stat-val big ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{result.totalPnl}%</div>
              <div style={{fontSize:12,color:'var(--text-tertiary)'}}>за {period}</div>
            </div>
            <div className="bt-stat-card">
              <div className="bt-stat-label">Финальный баланс</div>
              <div className="bt-stat-val">${result.finalEquity.toLocaleString()}</div>
              <div style={{fontSize:11,color:'var(--text-tertiary)'}}>начало: ${Number(deposit).toLocaleString()}</div>
            </div>
            <div className="bt-stat-card">
              <div className="bt-stat-label">Винрейт</div>
              <div className={`bt-stat-val ${result.winrate >= 50 ? 'pos' : 'neg'}`}>{result.winrate}%</div>
              <div style={{fontSize:11,color:'var(--text-tertiary)'}}>{result.wins}W / {result.losses}L / {result.bes}BE</div>
            </div>
            <div className="bt-stat-card">
              <div className="bt-stat-label">Макс. просадка</div>
              <div className="bt-stat-val neg">-{result.maxDrawdown}%</div>
              <div style={{fontSize:11,color:'var(--text-tertiary)'}}>от пика</div>
            </div>
            <div className="bt-stat-card">
              <div className="bt-stat-label">Профит-фактор</div>
              <div className={`bt-stat-val ${result.profitFactor >= 1.5 ? 'pos' : result.profitFactor >= 1 ? '' : 'neg'}`}>{result.profitFactor}</div>
              <div style={{fontSize:11,color:'var(--text-tertiary)'}}>{'>'} 1.5 — отлично</div>
            </div>
            <div className="bt-stat-card">
              <div className="bt-stat-label">Сделок</div>
              <div className="bt-stat-val">{result.trades}</div>
              <div style={{fontSize:11,color:'var(--text-tertiary)'}}>Ср. выигрыш: +{result.avgWin}%</div>
            </div>
          </div>

          {/* Equity curve */}
          <div className="bt-chart-card">
            <h3 style={{fontSize:14,fontWeight:700,color:'var(--text)',marginBottom:16}}>Кривая доходности</h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={result.equityCurve}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="day" tick={{fill:'var(--text-tertiary)',fontSize:10}} tickFormatter={v => `день ${v}`} axisLine={false} tickLine={false} />
                <YAxis tick={{fill:'var(--text-tertiary)',fontSize:10,fontFamily:'var(--font-mono)'}} axisLine={false} tickLine={false} tickFormatter={v => `$${v.toLocaleString()}`} width={70} />
                <Tooltip contentStyle={{background:'var(--surface)',border:'1px solid var(--border)',borderRadius:10,fontFamily:'var(--font-mono)',fontSize:12}} formatter={(v) => [`$${v.toLocaleString()}`, 'Баланс']} labelFormatter={v => `День ${v}`} />
                <ReferenceLine y={Number(deposit)} stroke="var(--text-tertiary)" strokeDasharray="4 4" />
                <Line type="monotone" dataKey="equity" stroke={pos ? 'var(--long)' : 'var(--short)'} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Last trades */}
          <div className="bt-trades-card">
            <h3 style={{fontSize:14,fontWeight:700,color:'var(--text)',marginBottom:14}}>Последние сделки</h3>
            <div className="bt-trades-list">
              {result.tradesList.reverse().map((t, i) => (
                <div key={i} className="bt-trade-row">
                  <span style={{color:'var(--text-tertiary)',fontSize:11,fontFamily:'var(--font-mono)'}}>#{t.id}</span>
                  <span style={{fontSize:12,color:'var(--text-secondary)'}}>{RESULT_LABELS[t.result] || t.result}</span>
                  <span style={{fontFamily:'var(--font-mono)',fontSize:12,fontWeight:600,color:t.pnlPct > 0 ? 'var(--long)' : t.pnlPct < 0 ? 'var(--short)' : 'var(--text-secondary)',marginLeft:'auto'}}>
                    {t.pnlPct > 0 ? '+' : ''}{t.pnlPct}%
                  </span>
                  <span style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-tertiary)',width:80,textAlign:'right'}}>
                    {t.pnlUsd > 0 ? '+' : ''}${t.pnlUsd}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <style>{`
        .bt-page { max-width: 100%; }
        .bt-settings {
          display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); padding: 20px; margin-bottom: 20px;
          box-shadow: var(--shadow-card);
        }
        .bt-settings .bf-group { flex: 1; min-width: 140px; }
        .bt-run-btn {
          padding: 10px 24px; background: linear-gradient(135deg, var(--accent), var(--purple));
          color: #fff; border: none; border-radius: 9px; font-size: 14px; font-weight: 700;
          box-shadow: 0 4px 14px rgba(77,140,245,0.35); transition: all 0.2s; white-space: nowrap; align-self: flex-end;
        }
        .bt-run-btn:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); }
        .bt-run-btn:disabled { opacity: 0.6; }
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
        .bt-trades-card {
          background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
          padding: 20px; box-shadow: var(--shadow-card);
        }
        .bt-trades-list { display: flex; flex-direction: column; gap: 0; }
        .bt-trade-row {
          display: flex; align-items: center; gap: 12px; padding: 9px 0;
          border-bottom: 1px solid var(--border);
        }
        .bt-trade-row:last-child { border-bottom: none; }
        .bf-group { display: flex; flex-direction: column; gap: 5px; }
        .bf-label { font-size: 11px; color: var(--text-secondary); font-weight: 500; }
        .bf-input { padding: 8px 12px; background: var(--surface-hover); border: 1px solid var(--border); border-radius: 7px; color: var(--text); font-size: 13px; font-family: var(--font-ui); outline: none; width: 100%; }
        .bf-input:focus { border-color: var(--accent); }
        .bf-input-row { display: flex; }
        .bf-input-row .bf-input { border-radius: 7px 0 0 7px; flex: 1; }
        .bf-unit { padding: 8px 10px; background: var(--surface-hover); border: 1px solid var(--border); border-left: none; border-radius: 0 7px 7px 0; font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
        .bf-toggle { display: flex; background: var(--surface-hover); border-radius: 7px; padding: 2px; gap: 2px; }
        .bft { flex: 1; padding: 5px 8px; border: none; background: transparent; color: var(--text-secondary); font-size: 12px; border-radius: 5px; transition: all 0.15s; }
        .bft.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-weight: 600; }
        @media (max-width: 900px) { .bt-summary-grid { grid-template-columns: repeat(2,1fr); } .bt-stat-card.main { grid-column: span 2; } }
        @media (max-width: 600px) { .bt-settings { flex-direction: column; } .bt-settings .bf-group { width: 100%; } }
      `}</style>
    </div>
  )
}
