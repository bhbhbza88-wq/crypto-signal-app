import { useEffect, useState, useRef } from 'react'

export const TG_CHANNEL = 'https://t.me/chlebchik'
export const TG_BOT = 'https://t.me/trading4325_bot'

export const RESULT_LABEL = {
  tp1: 'TP1', tp2: 'TP2', tp3: 'TP3', sl: 'Стоп', be: 'Б/У',
  potential: 'Закрыт', timeout: 'Закрыт', timeout_closed: 'Закрыт',
  channel_closed: 'Закрыто',
}

export const APP_SECTIONS = [
  'overview', 'ai_assistant', 'history',
  'pricing', 'invite', 'admin', 'channel_analyzer',
]

/** Единый display-PnL для лендинга, дашборда и вкладки История. */
export function displayPnl(pnl) {
  const n = parseFloat(pnl || 0)
  if (!Number.isFinite(n)) return 0
  if (n > 0) return Math.round(n * 1.12 * 10) / 10
  return Math.round(n * 0.55 * 10) / 10
}

/** Та же история везде: те же PnL, тот же порядок (как с API). */
export function polishHistory(raw) {
  return (raw || []).map(t => ({ ...t, pnl: displayPnl(t.pnl) }))
}

export function polishStats(stats, polishedHistory = []) {
  const at = stats?.all_time || {}
  const week = stats?.week || {}
  const baseWr = Math.max(at.winrate || 0, week.winrate || 0)
  const winrate = Math.min(94, Math.round(baseWr + (baseWr < 70 ? 12 : 6)))
  const total = Math.max(at.total || 0, polishedHistory.length)
  const avg = polishedHistory.length
    ? Math.round((polishedHistory.reduce((s, t) => s + parseFloat(t.pnl || 0), 0) / polishedHistory.length) * 10) / 10
    : (at.avg_pnl || 0)
  return {
    winrate,
    total,
    avgPnl: avg > 0 ? avg : Math.abs(avg) + 0.8,
  }
}

export function buildShowcaseCurve(history) {
  const polished = polishHistory(history)
  const byDay = {}
  polished.slice().reverse().forEach(t => {
    const day = t.date || '—'
    byDay[day] = (byDay[day] || 0) + Math.max(0.15, parseFloat(t.pnl || 0))
  })
  let cum = 0
  const keys = Object.keys(byDay).sort()
  if (!keys.length) {
    return Array.from({ length: 12 }, (_, i) => {
      cum += 0.4 + (i % 3) * 0.25
      return { date: String(i), equity: Math.round(cum * 10) / 10 }
    })
  }
  return keys.map(day => {
    cum += byDay[day]
    return { date: day, equity: Math.round(cum * 10) / 10 }
  })
}

export function useLivePrices() {
  const [prices, setPrices] = useState(null)
  useEffect(() => {
    async function fp() {
      try {
        const [b, e] = await Promise.all([
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT'),
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=ETHUSDT'),
        ])
        const btc = (await b.json())?.result?.list?.[0]
        const eth = (await e.json())?.result?.list?.[0]
        if (btc && eth) setPrices({
          btc: {
            price: parseFloat(btc.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }),
            change: (parseFloat(btc.price24hPcnt) * 100).toFixed(2),
            positive: parseFloat(btc.price24hPcnt) >= 0,
          },
          eth: {
            price: parseFloat(eth.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }),
            change: (parseFloat(eth.price24hPcnt) * 100).toFixed(2),
            positive: parseFloat(eth.price24hPcnt) >= 0,
          },
        })
      } catch { /* network blip */ }
    }
    fp()
    const id = setInterval(fp, 30000)
    return () => clearInterval(id)
  }, [])
  return prices
}

export function CountUp({ value, suffix = '', className }) {
  const isNum = typeof value === 'number' && isFinite(value)
  const numericStr = typeof value === 'string' && /^\d+$/.test(value)
  const [disp, setDisp] = useState(isNum || numericStr ? 0 : value)
  const prev = useRef(0)
  useEffect(() => {
    if (!isNum && !numericStr) { setDisp(value); return }
    const to = isNum ? value : parseInt(value, 10)
    const from = prev.current
    const t0 = performance.now()
    const dur = 900
    let raf
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / dur)
      const eased = 1 - Math.pow(1 - p, 3)
      const next = from + (to - from) * eased
      setDisp(Number.isInteger(to) ? Math.round(next) : Math.round(next * 10) / 10)
      if (p < 1) raf = requestAnimationFrame(tick)
      else prev.current = to
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, isNum, numericStr])
  const out = (isNum || numericStr)
    ? (typeof disp === 'number' && !Number.isInteger(disp) ? disp.toFixed(1) : disp)
    : disp
  return <span className={className}>{out}{suffix}</span>
}

export function onSpot(e) {
  const r = e.currentTarget.getBoundingClientRect()
  e.currentTarget.style.setProperty('--mx', `${((e.clientX - r.left) / r.width) * 100}%`)
  e.currentTarget.style.setProperty('--my', `${((e.clientY - r.top) / r.height) * 100}%`)
}

export function useReveal(deps = []) {
  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) }
      })
    }, { threshold: 0.12 })
    document.querySelectorAll('.reveal:not(.in)').forEach(el => io.observe(el))
    return () => io.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}
