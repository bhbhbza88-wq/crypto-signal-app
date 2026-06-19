import { useState, useCallback } from 'react'

const PAIRS = ['BTC/USDT','ETH/USDT','SOL/USDT','BNB/USDT','XRP/USDT','ADA/USDT','DOGE/USDT','AVAX/USDT','LINK/USDT','MATIC/USDT']

function useLivePrice(symbol) {
  const [price, setPrice] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchPrice = useCallback(async (sym) => {
    setLoading(true)
    try {
      const s = sym.replace('/', '')
      const res = await fetch(`https://api.bybit.com/v5/market/tickers?category=spot&symbol=${s}`)
      const data = await res.json()
      const p = parseFloat(data?.result?.list?.[0]?.lastPrice)
      if (!isNaN(p)) setPrice(p)
    } catch {}
    setLoading(false)
  }, [])

  return { price, loading, fetchPrice }
}

export default function SmartTrade() {
  const [pair, setPair] = useState('BTC/USDT')
  const [side, setSide] = useState('LONG')
  const [entry, setEntry] = useState('')
  const [deposit, setDeposit] = useState('1000')
  const [risk, setRisk] = useState('1')
  const [stopPct, setStopPct] = useState('2')
  const [tp1Pct, setTp1Pct] = useState('3')
  const [tp2Pct, setTp2Pct] = useState('6')
  const [tp3Pct, setTp3Pct] = useState('10')
  const [leverage, setLeverage] = useState('1')
  const { price, loading, fetchPrice } = useLivePrice()

  const entryPrice = parseFloat(entry) || price || 0
  const dep = parseFloat(deposit) || 0
  const riskAmt = dep * (parseFloat(risk) / 100)
  const stopPctVal = parseFloat(stopPct) / 100
  const positionSize = stopPctVal > 0 ? riskAmt / stopPctVal : 0
  const positionSizeLev = positionSize * parseFloat(leverage || 1)
  const qty = entryPrice > 0 ? positionSizeLev / entryPrice : 0

  const calc = (pct, dir) => {
    if (!entryPrice) return 0
    const mult = dir === 'LONG' ? 1 : -1
    return entryPrice * (1 + mult * parseFloat(pct) / 100)
  }

  const stopPrice = calc(stopPct, side === 'LONG' ? 'SHORT' : 'LONG')
  const tp1Price = calc(tp1Pct, side)
  const tp2Price = calc(tp2Pct, side)
  const tp3Price = calc(tp3Pct, side)

  const rr1 = parseFloat(tp1Pct) / parseFloat(stopPct)
  const rr2 = parseFloat(tp2Pct) / parseFloat(stopPct)

  function handleFetchPrice() {
    fetchPrice(pair)
  }

  function fillFromPrice() {
    if (price) setEntry(price.toFixed(4))
  }

  const isLong = side === 'LONG'

  return (
    <div className="st-page animate-in">
      <div className="page-header" style={{marginBottom:20}}>
        <h1 className="page-title">SmartTrade — Калькулятор позиции</h1>
        <p style={{fontSize:13,color:'var(--text-secondary)',marginTop:4}}>Рассчитай размер позиции, риск и уровни выхода перед сделкой</p>
      </div>

      <div className="st-layout">
        {/* Left — Settings */}
        <div className="st-form-col">
          <div className="st-card">
            <h3 className="st-card-title">📊 Параметры сделки</h3>

            <div className="st-row">
              <div className="bf-group" style={{flex:2}}>
                <label className="bf-label">Торговая пара</label>
                <select className="bf-input" value={pair} onChange={e => { setPair(e.target.value); setEntry('') }}>
                  {PAIRS.map(p => <option key={p}>{p}</option>)}
                </select>
              </div>
              <div className="bf-group" style={{flex:1}}>
                <label className="bf-label">Направление</label>
                <div className="bf-toggle">
                  <button className={`bft ${isLong ? 'active long' : ''}`} onClick={() => setSide('LONG')}>Long</button>
                  <button className={`bft ${!isLong ? 'active short' : ''}`} onClick={() => setSide('SHORT')}>Short</button>
                </div>
              </div>
            </div>

            <div className="st-row">
              <div className="bf-group" style={{flex:1}}>
                <label className="bf-label">Цена входа</label>
                <div style={{display:'flex',gap:6}}>
                  <input className="bf-input" placeholder="0.00" value={entry} onChange={e => setEntry(e.target.value)} style={{flex:1}} />
                  <button className="st-price-btn" onClick={handleFetchPrice} disabled={loading} title="Получить текущую цену">
                    {loading ? '⟳' : '↓'}
                  </button>
                </div>
                {price && <button className="st-use-price" onClick={fillFromPrice}>Использовать ${price.toLocaleString('en-US', {maximumFractionDigits: 4})}</button>}
              </div>
              <div className="bf-group" style={{flex:1}}>
                <label className="bf-label">Плечо</label>
                <div className="bf-input-row">
                  <input className="bf-input" type="number" min="1" max="100" value={leverage} onChange={e => setLeverage(e.target.value)} style={{borderRadius:'7px 0 0 7px'}} />
                  <span className="bf-unit">x</span>
                </div>
              </div>
            </div>

            <div className="st-row">
              <div className="bf-group" style={{flex:1}}>
                <label className="bf-label">Депозит (USDT)</label>
                <input className="bf-input" type="number" value={deposit} onChange={e => setDeposit(e.target.value)} />
              </div>
              <div className="bf-group" style={{flex:1}}>
                <label className="bf-label">Риск на сделку (%)</label>
                <div className="bf-input-row">
                  <input className="bf-input" type="number" step="0.5" min="0.1" max="10" value={risk} onChange={e => setRisk(e.target.value)} style={{borderRadius:'7px 0 0 7px'}} />
                  <span className="bf-unit">%</span>
                </div>
              </div>
            </div>
          </div>

          <div className="st-card">
            <h3 className="st-card-title">🎯 Уровни выхода</h3>
            <div className="st-levels-grid">
              <div className="bf-group">
                <label className="bf-label" style={{color:'var(--short)'}}>Стоп-лосс (%)</label>
                <div className="bf-input-row">
                  <input className="bf-input" type="number" step="0.1" min="0.1" value={stopPct} onChange={e => setStopPct(e.target.value)} style={{borderRadius:'7px 0 0 7px'}} />
                  <span className="bf-unit">%</span>
                </div>
                {entryPrice > 0 && <span className="st-price-hint neg">${stopPrice.toFixed(4)}</span>}
              </div>
              <div className="bf-group">
                <label className="bf-label" style={{color:'var(--long)'}}>TP1 (%)</label>
                <div className="bf-input-row">
                  <input className="bf-input" type="number" step="0.5" min="0.1" value={tp1Pct} onChange={e => setTp1Pct(e.target.value)} style={{borderRadius:'7px 0 0 7px'}} />
                  <span className="bf-unit">%</span>
                </div>
                {entryPrice > 0 && <span className="st-price-hint pos">${tp1Price.toFixed(4)}</span>}
              </div>
              <div className="bf-group">
                <label className="bf-label" style={{color:'var(--long)'}}>TP2 (%)</label>
                <div className="bf-input-row">
                  <input className="bf-input" type="number" step="0.5" min="0.1" value={tp2Pct} onChange={e => setTp2Pct(e.target.value)} style={{borderRadius:'7px 0 0 7px'}} />
                  <span className="bf-unit">%</span>
                </div>
                {entryPrice > 0 && <span className="st-price-hint pos">${tp2Price.toFixed(4)}</span>}
              </div>
              <div className="bf-group">
                <label className="bf-label" style={{color:'var(--long)'}}>TP3 (%)</label>
                <div className="bf-input-row">
                  <input className="bf-input" type="number" step="0.5" min="0.1" value={tp3Pct} onChange={e => setTp3Pct(e.target.value)} style={{borderRadius:'7px 0 0 7px'}} />
                  <span className="bf-unit">%</span>
                </div>
                {entryPrice > 0 && <span className="st-price-hint pos">${tp3Price.toFixed(4)}</span>}
              </div>
            </div>
          </div>
        </div>

        {/* Right — Results */}
        <div className="st-result-col">
          <div className="st-card result-card">
            <h3 className="st-card-title">💡 Расчёт позиции</h3>

            <div className={`st-direction-badge ${isLong ? 'long' : 'short'}`}>
              {isLong ? '▲ LONG' : '▼ SHORT'} · {pair}
            </div>

            <div className="st-result-rows">
              <ResultRow label="Макс. риск (USDT)" value={`$${riskAmt.toFixed(2)}`} sub={`${risk}% от депозита`} />
              <ResultRow label="Размер позиции" value={positionSizeLev > 0 ? `$${positionSizeLev.toFixed(2)}` : '—'} sub={leverage > 1 ? `с плечом x${leverage}` : 'без плеча'} />
              <ResultRow label="Объём" value={qty > 0 ? `${qty.toFixed(qty < 0.01 ? 6 : 4)} ${pair.split('/')[0]}` : '—'} />
            </div>

            <div className="st-rr-row">
              <div className={`st-rr ${rr1 >= 2 ? 'good' : rr1 >= 1.5 ? 'ok' : 'bad'}`}>
                <div className="st-rr-label">R:R к TP1</div>
                <div className="st-rr-val">1 : {rr1.toFixed(1)}</div>
              </div>
              <div className={`st-rr ${rr2 >= 3 ? 'good' : rr2 >= 2 ? 'ok' : 'bad'}`}>
                <div className="st-rr-label">R:R к TP2</div>
                <div className="st-rr-val">1 : {rr2.toFixed(1)}</div>
              </div>
            </div>
          </div>

          {/* Visual levels */}
          {entryPrice > 0 && (
            <div className="st-card">
              <h3 className="st-card-title">📈 Визуализация уровней</h3>
              <div className="st-visual-levels">
                <LevelBar label="TP3" price={tp3Price} pct={tp3Pct} color="var(--long)" opacity={0.5} />
                <LevelBar label="TP2" price={tp2Price} pct={tp2Pct} color="var(--long)" opacity={0.7} />
                <LevelBar label="TP1" price={tp1Price} pct={tp1Pct} color="var(--long)" opacity={1} />
                <LevelBar label="Вход" price={entryPrice} pct="0" color="var(--accent)" isEntry />
                <LevelBar label="Стоп" price={stopPrice} pct={stopPct} color="var(--short)" isStop />
              </div>
            </div>
          )}

          <div className="st-disclaimer">
            ⚠️ Этот инструмент только для расчётов. Не является финансовым советом. Торгуй осознанно.
          </div>
        </div>
      </div>

      <style>{`
        .st-page { max-width: 100%; }
        .st-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .st-form-col, .st-result-col { display: flex; flex-direction: column; gap: 16px; }
        .st-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); padding: 20px; box-shadow: var(--shadow-card);
        }
        .result-card { border-color: var(--accent-soft); background: var(--surface); }
        .st-card-title { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 16px; }
        .st-row { display: flex; gap: 10px; margin-bottom: 12px; }
        .st-levels-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .st-price-hint { font-size: 11px; font-family: var(--font-mono); font-weight: 600; margin-top: 4px; display: block; }
        .st-price-hint.pos { color: var(--long); } .st-price-hint.neg { color: var(--short); }
        .st-price-btn {
          width: 36px; height: 36px; border: 1px solid var(--border); background: var(--surface-hover);
          color: var(--accent); border-radius: 7px; font-size: 16px; font-weight: 700; flex-shrink: 0;
        }
        .st-use-price {
          border: none; background: transparent; color: var(--accent); font-size: 11px;
          cursor: pointer; text-align: left; padding: 3px 0; font-weight: 600;
        }
        .st-direction-badge {
          text-align: center; padding: 12px; border-radius: 10px; font-size: 18px; font-weight: 800;
          letter-spacing: 0.05em; margin-bottom: 16px; font-family: var(--font-mono);
        }
        .st-direction-badge.long { background: var(--long-soft); color: var(--long); }
        .st-direction-badge.short { background: var(--short-soft); color: var(--short); }
        .st-result-rows { display: flex; flex-direction: column; gap: 0; margin-bottom: 16px; }
        .st-rr-row { display: flex; gap: 10px; }
        .st-rr { flex: 1; padding: 12px; border-radius: 10px; text-align: center; }
        .st-rr.good { background: var(--long-soft); }
        .st-rr.ok { background: var(--amber-soft); }
        .st-rr.bad { background: var(--short-soft); }
        .st-rr-label { font-size: 11px; color: var(--text-secondary); margin-bottom: 4px; }
        .st-rr-val { font-family: var(--font-mono); font-size: 18px; font-weight: 800; color: var(--text); }
        .st-visual-levels { display: flex; flex-direction: column; gap: 6px; }
        .st-disclaimer {
          font-size: 12px; color: var(--text-tertiary); background: var(--surface-hover);
          border: 1px solid var(--border); border-radius: 10px; padding: 12px; line-height: 1.5;
        }
        .bf-group { display: flex; flex-direction: column; gap: 5px; }
        .bf-label { font-size: 11px; color: var(--text-secondary); font-weight: 500; }
        .bf-input { padding: 8px 12px; background: var(--surface-hover); border: 1px solid var(--border); border-radius: 7px; color: var(--text); font-size: 13px; font-family: var(--font-ui); outline: none; width: 100%; }
        .bf-input:focus { border-color: var(--accent); }
        .bf-input-row { display: flex; }
        .bf-input-row .bf-input { border-radius: 7px 0 0 7px; flex: 1; }
        .bf-unit { padding: 8px 10px; background: var(--surface-hover); border: 1px solid var(--border); border-left: none; border-radius: 0 7px 7px 0; font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
        .bf-toggle { display: flex; background: var(--surface-hover); border-radius: 7px; padding: 2px; gap: 2px; }
        .bft { flex: 1; padding: 7px 8px; border: none; background: transparent; color: var(--text-secondary); font-size: 13px; border-radius: 5px; transition: all 0.15s; font-weight: 500; }
        .bft.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-weight: 700; }
        .bft.active.long { color: var(--long); }
        .bft.active.short { color: var(--short); }
        @media (max-width: 768px) { .st-layout { grid-template-columns: 1fr; } .st-levels-grid { grid-template-columns: 1fr 1fr; } }
      `}</style>
    </div>
  )
}

function ResultRow({ label, value, sub }) {
  return (
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 0',borderBottom:'1px solid var(--border)'}}>
      <div>
        <div style={{fontSize:12,color:'var(--text-secondary)'}}>{label}</div>
        {sub && <div style={{fontSize:10,color:'var(--text-tertiary)',marginTop:2}}>{sub}</div>}
      </div>
      <div style={{fontFamily:'var(--font-mono)',fontSize:16,fontWeight:700,color:'var(--text)'}}>{value}</div>
    </div>
  )
}

function LevelBar({ label, price, pct, color, isEntry, isStop }) {
  return (
    <div style={{display:'flex',alignItems:'center',gap:10}}>
      <div style={{width:40,fontSize:10,fontWeight:700,color,textAlign:'right',flexShrink:0}}>{label}</div>
      <div style={{flex:1,height:2,background:isEntry?color:'var(--border)',borderRadius:1,position:'relative'}}>
        <div style={{position:'absolute',right:0,top:-4,width:8,height:8,borderRadius:'50%',background:color,border:'2px solid var(--surface)'}} />
      </div>
      <div style={{fontFamily:'var(--font-mono)',fontSize:11,color,fontWeight:600,width:90,flexShrink:0}}>${parseFloat(price).toFixed(4)}</div>
      {!isEntry && <div style={{fontSize:10,color,width:40,flexShrink:0,textAlign:'right'}}>{isStop ? '-' : '+'}{pct}%</div>}
    </div>
  )
}
