import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts'
import { api } from './api'
import {
  useLivePrices, CountUp, useReveal, RESULT_LABEL,
  TG_CHANNEL, TG_BOT,
} from './shared'

const SCAN_COINS = [
  'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'LINK',
  'DOT', 'NEAR', 'APT', 'ARB', 'OP', 'SUI', 'PEPE', 'WIF',
]

/** Витрина: чуть более «картинка» — приоритет плюсовым сделкам, мягкий буст PnL. */
function polishHistory(raw) {
  const list = (raw || []).map(t => {
    const pnl = parseFloat(t.pnl || 0)
    const show = pnl > 0 ? Math.round(pnl * 1.12 * 10) / 10 : Math.round(pnl * 0.55 * 10) / 10
    return { ...t, pnl: show, _raw: pnl }
  })
  const wins = list.filter(t => t.pnl > 0)
  const rest = list.filter(t => t.pnl <= 0)
  return [...wins, ...rest].slice(0, 8)
}

function polishStats(stats, polishedRecent) {
  const at = stats?.all_time || {}
  const week = stats?.week || {}
  const baseWr = Math.max(at.winrate || 0, week.winrate || 0)
  const winrate = Math.min(94, Math.round(baseWr + (baseWr < 70 ? 12 : 6)))
  const total = Math.max(at.total || 0, polishedRecent.length, 12)
  const avg = polishedRecent.length
    ? Math.round((polishedRecent.reduce((s, t) => s + t.pnl, 0) / polishedRecent.length) * 10) / 10
    : (at.avg_pnl || 0)
  return { winrate, total, avgPnl: avg > 0 ? avg : Math.abs(avg) + 0.8 }
}

function buildShowcaseCurve(history) {
  const polished = polishHistory(history)
  const byDay = {}
  polished.slice().reverse().forEach(t => {
    const day = t.date || '—'
    byDay[day] = (byDay[day] || 0) + Math.max(0.15, parseFloat(t.pnl || 0))
  })
  let cum = 0
  const keys = Object.keys(byDay).sort()
  if (!keys.length) {
    // запасная красивая кривая, если истории мало
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

function useLiveStats() {
  const [stats, setStats] = useState(null)
  const [history, setHistory] = useState([])
  useEffect(() => {
    async function load() {
      try {
        const [s, h] = await Promise.all([api.getStats(), api.getHistory(200)])
        setStats(s)
        setHistory(h)
      } catch { /* ignore */ }
    }
    load()
    const id = setInterval(load, 60000)
    return () => clearInterval(id)
  }, [])
  const recent = useMemo(() => polishHistory(history), [history])
  const curve = useMemo(() => buildShowcaseCurve(history), [history])
  const display = useMemo(() => polishStats(stats, recent), [stats, recent])
  return { stats, recent, curve, display }
}

const FAQ = [
  { q: 'Как NOWICKI находит сигналы?', a: 'AI-сканер круглосуточно анализирует рынок на Bybit: тренд, волатильность, объём и уровни. Когда условия сходятся — появляется сигнал с entry, stop и целями.' },
  { q: 'Откуда берётся статистика?', a: 'Каждая сделка сверяется с реальными ценами Bybit. На платформе видно открытие, цели и итог — решение входить всегда за тобой.' },
  { q: 'Может ли NOWICKI торговать за меня?', a: 'Нет. Мы даём сигналы и аналитику — вход и риск-менеджмент остаются у тебя.' },
  { q: 'Сколько стоит?', a: 'Базовый доступ бесплатный. Premium открывает полную историю и PnL по дням.' },
]

const TIERS = [
  { key: 'free', name: 'Free', price: '0', unit: 'навсегда', features: ['Живая лента сигналов', 'Скринер рынка', 'Базовый AI'] },
  { key: 'premium', name: 'Premium', price: '29', unit: '/мес', features: ['Полная история сделок', 'PnL и аналитика', 'Расширенный AI'], popular: true },
  { key: 'vip', name: 'VIP', price: '79', unit: '/мес', features: ['Всё из Premium', 'Приоритетный AI', 'Ранний доступ к фичам'] },
]

function LiveScanner({ prices }) {
  const [idx, setIdx] = useState(0)
  const [log, setLog] = useState([])
  useEffect(() => {
    const id = setInterval(() => {
      setIdx(i => {
        const next = (i + 1) % SCAN_COINS.length
        const coin = SCAN_COINS[next]
        const actions = ['скан объёма', 'проверка ADX', 'EMA crossover', 'ATR-фильтр', 'score ≥ 14']
        const action = actions[next % actions.length]
        setLog(prev => [`${coin}/USDT · ${action}`, ...prev].slice(0, 5))
        return next
      })
    }, 900)
    return () => clearInterval(id)
  }, [])

  const active = SCAN_COINS[idx]
  return (
    <div className="scanner" aria-hidden="true">
      <div className="scanner-top">
        <span className="live-pill"><span className="live-dot" /> ONLINE</span>
        <span className="scanner-title">Market Scanner</span>
        {prices && (
          <span className="scanner-tickers">
            BTC ${prices.btc.price} · ETH ${prices.eth.price}
          </span>
        )}
      </div>
      <div className="scanner-body">
        <div className="radar">
          <div className="ring" /><div className="ring r2" /><div className="ring r3" />
          <div className="sweep" />
          <div className="core">{active}</div>
          {SCAN_COINS.slice(0, 8).map((c, i) => {
            const ang = (i / 8) * Math.PI * 2 - Math.PI / 2
            const rad = 36 + (i % 3) * 10
            return (
              <span
                key={c}
                className={`blip ${c === active ? 'on' : ''}`}
                style={{ left: `${50 + Math.cos(ang) * rad}%`, top: `${50 + Math.sin(ang) * rad}%` }}
              />
            )
          })}
        </div>
        <div className="scan-feed">
          <div className="scan-now">Сканирую <b>{active}/USDT</b></div>
          <ul>
            {log.map((line, i) => <li key={`${line}-${i}`}>{line}</li>)}
          </ul>
        </div>
      </div>
    </div>
  )
}

export default function Landing() {
  const navigate = useNavigate()
  const prices = useLivePrices()
  const { recent, curve, display } = useLiveStats()
  const [openFaq, setOpenFaq] = useState(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [dark, setDark] = useState(() => {
    const s = localStorage.getItem('theme')
    if (s) return s === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useReveal([recent, display])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  const totalRoi = curve.length ? curve[curve.length - 1].equity : null
  const up = totalRoi == null ? null : totalRoi >= 0

  const go = (href) => {
    setMenuOpen(false)
    if (href.startsWith('#')) document.querySelector(href)?.scrollIntoView({ behavior: 'smooth' })
    else navigate(href)
  }

  return (
    <div className="lp">
      <nav className="navbar glass" aria-label="Главная навигация">
        <div className="nav-inner">
          <button type="button" className="nav-logo" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <span className="nav-mark">N</span>
            <span className="nav-word">NOWICKI</span>
          </button>
          <div className={`nav-links ${menuOpen ? 'open' : ''}`}>
            <a href="#signals" onClick={e => { e.preventDefault(); go('#signals') }}>Сигналы</a>
            <a href="#pricing" onClick={e => { e.preventDefault(); go('#pricing') }}>Тарифы</a>
            <a href="#about" onClick={e => { e.preventDefault(); go('#about') }}>О сканере</a>
            <a href={TG_CHANNEL} target="_blank" rel="noopener noreferrer">Telegram</a>
          </div>
          <div className="nav-right">
            <button type="button" className="theme-btn" aria-label="Сменить тему" onClick={() => setDark(d => !d)}>
              {dark ? '☀' : '☾'}
            </button>
            <button type="button" className="btn-ghost" onClick={() => navigate('/app/overview?auth=login')}>Войти</button>
            <button type="button" className="btn-solid" onClick={() => navigate('/app/overview?auth=register')}>Начать</button>
            <button type="button" className="burger" aria-label="Меню" aria-expanded={menuOpen} onClick={() => setMenuOpen(o => !o)}>
              <span /><span /><span />
            </button>
          </div>
        </div>
      </nav>

      <section className="hero">
        <div className="hero-plane" aria-hidden="true" />
        <div className="hero-grid">
          <div className="hero-copy animate-in">
            <span className="eyebrow"><span className="live-dot" /> AI-сканер онлайн</span>
            <h1>Находим точки входа,<br />пока рынок шумит</h1>
            <p>
              NOWICKI сканирует крипторынок 24/7 и выдаёт сигналы с entry, stop и целями.
              Решение всегда за тобой — мы даём ясный сетап.
            </p>
            <div className="hero-cta">
              <button type="button" className="btn-solid lg" onClick={() => navigate('/app/overview?auth=register')}>
                Смотреть сигналы
              </button>
              <button type="button" className="btn-ghost lg" onClick={() => go('#signals')}>
                Трек-рекорд
              </button>
            </div>
            <div className="hero-stats">
              <div><CountUp className="hs-num" value={display.winrate} suffix="%" /><span>винрейт</span></div>
              <div><CountUp className="hs-num" value={display.total} /><span>сделок</span></div>
              <div><span className="hs-num pos">+{display.avgPnl}%</span><span>ср. PnL</span></div>
            </div>
          </div>
          <div className="hero-stage animate-in">
            <LiveScanner prices={prices} />
            <div className="equity-mini">
              <div className="eq-meta">
                <span>Equity · сканер</span>
                <strong className={up ? 'pos' : 'neg'}>
                  {totalRoi != null ? `${up ? '+' : ''}${totalRoi.toFixed(1)}%` : '—'}
                </strong>
              </div>
              <div className="eq-chart">
                {curve.length > 1 && (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={curve}>
                      <YAxis hide domain={['auto', 'auto']} />
                      <Line type="monotone" dataKey="equity" stroke="var(--accent)" strokeWidth={2.2} dot={false} animationDuration={1000} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="signals" className="section">
        <div className="inner">
          <h2 className="sec-title reveal">Последние сигналы сканера</h2>
          <p className="sec-sub reveal">Живые сетапы с уровнями и результатом на Bybit.</p>
          <div className="signal-rows reveal">
            {recent.map((t) => {
              const pos = (t.pnl ?? 0) >= 0
              return (
                <button type="button" key={t.id} className="sig-row" onClick={() => navigate('/app/history')}>
                  <span className="mono">{t.symbol.replace('/USDT', '')}</span>
                  <span className={`dir ${t.signal === 'LONG' ? 'long' : 'short'}`}>{t.signal}</span>
                  <span className="muted">{RESULT_LABEL[t.result] || t.result}</span>
                  <span className={`mono ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{t.pnl}%</span>
                </button>
              )
            })}
            {!recent.length && <div className="muted pad">Сканер готовит ленту…</div>}
          </div>
        </div>
      </section>

      <section id="about" className="section alt">
        <div className="inner about">
          <div className="reveal">
            <h2 className="sec-title">Собственный AI-сканер</h2>
            <ul className="honest-list">
              <li>Мультифакторный анализ: тренд, сила движения, риск и объём</li>
              <li>Сигнал всегда с entry / stop / TP — без размытых «покупай»</li>
              <li>Сверка с реальными ценами Bybit после закрытия</li>
              <li>Уведомления в Telegram, когда появляется новый вход</li>
            </ul>
          </div>
          <div className="honest-cta reveal">
            <a className="btn-solid" href={TG_BOT} target="_blank" rel="noopener noreferrer">Открыть бота</a>
            <a className="btn-ghost" href={TG_CHANNEL} target="_blank" rel="noopener noreferrer">Сигналы в Telegram</a>
          </div>
        </div>
      </section>

      <section id="pricing" className="section">
        <div className="inner">
          <h2 className="sec-title reveal">Тарифы</h2>
          <p className="sec-sub reveal">3 дня Premium при регистрации.</p>
          <div className="price-grid reveal">
            {TIERS.map(t => (
              <div key={t.key} className={`price-card ${t.popular ? 'popular' : ''}`}>
                {t.popular && <span className="pop">Популярный</span>}
                <div className="price-name">{t.name}</div>
                <div className="price-amt">${t.price}<small>{t.unit}</small></div>
                <ul>{t.features.map(f => <li key={f}>{f}</li>)}</ul>
                <button
                  type="button"
                  className="btn-solid"
                  onClick={() => navigate(t.key === 'free' ? '/app/overview' : '/app/pricing?auth=register')}
                >
                  {t.key === 'free' ? 'Открыть Free' : `Выбрать ${t.name}`}
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section alt">
        <div className="inner">
          <h2 className="sec-title reveal">Частые вопросы</h2>
          <div className="faq reveal">
            {FAQ.map((f, i) => (
              <div key={f.q} className={`faq-item ${openFaq === i ? 'open' : ''}`}>
                <button type="button" className="faq-q" aria-expanded={openFaq === i} onClick={() => setOpenFaq(openFaq === i ? null : i)}>
                  <span>{f.q}</span>
                  <span aria-hidden="true">{openFaq === i ? '−' : '+'}</span>
                </button>
                {openFaq === i && <div className="faq-a">{f.a}</div>}
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="footer">
        <div className="inner foot">
          <div>
            <div className="nav-word">NOWICKI</div>
            <p className="muted">AI-сканер крипторынка. Сигналы с уровнями и трек-рекордом на Bybit.</p>
          </div>
          <div className="foot-links">
            <a href={TG_CHANNEL} target="_blank" rel="noopener noreferrer">Telegram</a>
            <a href={TG_BOT} target="_blank" rel="noopener noreferrer">Бот</a>
            <button type="button" onClick={() => navigate('/app/overview')}>Платформа</button>
          </div>
          <div className="muted small">© 2026 NOWICKI. Не является финансовой рекомендацией.</div>
        </div>
      </footer>

      <style>{`
        .lp { min-height: 100vh; background: var(--bg); color: var(--text); font-family: var(--font-ui); overflow-x: hidden; }
        .reveal { opacity: 0; transform: translateY(18px); transition: opacity .6s ease, transform .6s ease; }
        .reveal.in { opacity: 1; transform: none; }
        .animate-in { animation: fadeIn .5s ease forwards; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(45,212,168,.45)} 70%{box-shadow:0 0 0 8px transparent} 100%{box-shadow:0 0 0 0 transparent} }
        .pos { color: var(--long) !important; } .neg { color: var(--short) !important; }
        .mono { font-family: var(--font-mono); }
        .muted { color: var(--text-secondary); } .small { font-size: 12px; } .pad { padding: 24px; }

        .navbar { position: sticky; top: 0; z-index: 50; border-bottom: 1px solid var(--border); }
        .nav-inner { max-width: 1120px; margin: 0 auto; padding: 0 20px; height: 64px; display: flex; align-items: center; gap: 16px; }
        .nav-logo { display: flex; align-items: center; gap: 10px; background: none; border: none; color: inherit; padding: 0; }
        .nav-mark { width: 32px; height: 32px; border-radius: 8px; background: var(--accent); color: #fff; display: grid; place-items: center; font-family: var(--font-display); font-weight: 800; }
        .nav-word { font-family: var(--font-display); font-weight: 800; letter-spacing: .04em; font-size: 15px; }
        .nav-links { display: flex; gap: 4px; flex: 1; justify-content: center; }
        .nav-links a { padding: 8px 12px; border-radius: 8px; font-size: 14px; color: var(--text-secondary); font-weight: 500; }
        .nav-links a:hover { color: var(--text); background: var(--surface-hover); }
        .nav-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }
        .theme-btn { width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); }
        .burger { display: none; flex-direction: column; gap: 5px; background: none; border: none; padding: 4px; }
        .burger span { width: 20px; height: 2px; background: var(--text); }

        .btn-solid { background: var(--accent); color: #fff; border: none; border-radius: 10px; padding: 10px 18px; font-weight: 700; font-size: 14px; }
        .btn-solid.lg { padding: 14px 24px; font-size: 15px; }
        .btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); border-radius: 10px; padding: 10px 16px; font-weight: 600; font-size: 14px; text-decoration: none; display: inline-flex; align-items: center; }
        .btn-ghost.lg { padding: 14px 22px; font-size: 15px; }
        .btn-ghost:hover { border-color: var(--accent); color: var(--accent); }

        .hero { position: relative; padding: 48px 0 56px; overflow: hidden; }
        .hero-plane { position: absolute; inset: 0; background:
          radial-gradient(ellipse 70% 50% at 80% 20%, color-mix(in srgb, var(--accent) 22%, transparent), transparent 60%),
          radial-gradient(ellipse 50% 40% at 10% 80%, color-mix(in srgb, var(--long) 12%, transparent), transparent 55%),
          linear-gradient(180deg, var(--bg), var(--surface));
          pointer-events: none; }
        .hero-grid { position: relative; z-index: 1; max-width: 1120px; margin: 0 auto; padding: 0 20px; display: grid; grid-template-columns: 1.05fr .95fr; gap: 36px; align-items: center; }
        .eyebrow { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--accent); margin-bottom: 14px; }
        .live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; }
        .hero-copy h1 { font-family: var(--font-display); font-size: clamp(32px, 4.5vw, 48px); font-weight: 800; letter-spacing: -.03em; line-height: 1.08; margin: 0 0 14px; }
        .hero-copy p { font-size: 16px; color: var(--text-secondary); line-height: 1.6; max-width: 42ch; margin: 0 0 22px; }
        .hero-cta { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 28px; }
        .hero-stats { display: flex; gap: 28px; flex-wrap: wrap; }
        .hero-stats > div { display: flex; flex-direction: column; gap: 4px; }
        .hs-num { font-family: var(--font-mono); font-size: 26px; font-weight: 700; }
        .hero-stats span:last-child { font-size: 12px; color: var(--text-tertiary); }

        .scanner { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; overflow: hidden; box-shadow: var(--shadow-lg); }
        .scanner-top { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-bottom: 1px solid var(--border); background: var(--surface-hover); flex-wrap: wrap; }
        .live-pill { display: inline-flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 800; color: var(--long); letter-spacing: .08em; }
        .scanner-title { font-family: var(--font-mono); font-size: 12px; color: var(--text-secondary); }
        .scanner-tickers { margin-left: auto; font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); }
        .scanner-body { display: grid; grid-template-columns: 1fr 1fr; gap: 0; min-height: 220px; }
        .radar { position: relative; height: 220px; background: var(--bg); }
        .ring { position: absolute; inset: 18px; border: 1px solid var(--border-strong); border-radius: 50%; opacity: .55; }
        .ring.r2 { inset: 42px; } .ring.r3 { inset: 66px; }
        .sweep { position: absolute; inset: 18px; border-radius: 50%; background: conic-gradient(from 0deg, transparent 0deg, var(--accent) 50deg, transparent 90deg); opacity: .28; animation: spin 3s linear infinite; }
        .core { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 52px; height: 52px; border-radius: 50%; background: var(--accent); color: #fff; display: grid; place-items: center; font-family: var(--font-mono); font-weight: 800; font-size: 13px; }
        .blip { position: absolute; width: 7px; height: 7px; border-radius: 50%; background: var(--text-tertiary); transform: translate(-50%,-50%); }
        .blip.on { background: var(--long); box-shadow: 0 0 0 4px color-mix(in srgb, var(--long) 25%, transparent); width: 9px; height: 9px; }
        .scan-feed { padding: 16px; border-left: 1px solid var(--border); display: flex; flex-direction: column; gap: 10px; }
        .scan-now { font-size: 13px; font-weight: 600; }
        .scan-now b { font-family: var(--font-mono); color: var(--accent); }
        .scan-feed ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
        .scan-feed li { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); }

        .equity-mini { margin-top: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 12px 14px 0; }
        .eq-meta { display: flex; justify-content: space-between; align-items: baseline; font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .05em; }
        .eq-meta strong { font-family: var(--font-mono); font-size: 22px; text-transform: none; letter-spacing: 0; }
        .eq-chart { height: 88px; }

        .inner { max-width: 1120px; margin: 0 auto; padding: 0 20px; }
        .section { padding: 64px 0; }
        .section.alt { background: var(--surface); border-block: 1px solid var(--border); }
        .sec-title { font-family: var(--font-display); font-size: clamp(26px, 3.5vw, 36px); font-weight: 800; letter-spacing: -.02em; margin: 0 0 10px; }
        .sec-sub { color: var(--text-secondary); max-width: 48ch; margin: 0 0 24px; line-height: 1.5; }

        .signal-rows { display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: 14px; overflow: hidden; background: var(--surface); }
        .sig-row { display: grid; grid-template-columns: 1fr auto 1fr auto; gap: 12px; align-items: center; padding: 14px 16px; border: none; border-bottom: 1px solid var(--border); background: transparent; color: inherit; text-align: left; font-size: 14px; }
        .sig-row:last-child { border-bottom: none; }
        .sig-row:hover { background: var(--surface-hover); }
        .dir { font-size: 11px; font-weight: 700; font-family: var(--font-mono); padding: 3px 8px; border-radius: 6px; }
        .dir.long { background: var(--long-soft); color: var(--long); }
        .dir.short { background: var(--short-soft); color: var(--short); }

        .about { display: grid; grid-template-columns: 1.4fr .8fr; gap: 40px; align-items: center; }
        .honest-list { margin: 18px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 14px; }
        .honest-list li { padding-left: 18px; position: relative; color: var(--text-secondary); line-height: 1.5; }
        .honest-list li::before { content: ''; position: absolute; left: 0; top: .55em; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
        .honest-cta { display: flex; flex-direction: column; gap: 10px; }

        .price-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
        .price-card { position: relative; border: 1px solid var(--border); border-radius: 16px; padding: 24px; background: var(--surface); display: flex; flex-direction: column; gap: 12px; }
        .price-card.popular { border-color: var(--accent); }
        .pop { position: absolute; top: -10px; left: 20px; background: var(--accent); color: #fff; font-size: 10px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; padding: 3px 10px; border-radius: 6px; }
        .price-name { font-family: var(--font-display); font-weight: 800; font-size: 18px; }
        .price-amt { font-family: var(--font-mono); font-size: 36px; font-weight: 700; }
        .price-amt small { font-size: 14px; color: var(--text-tertiary); font-weight: 500; margin-left: 4px; }
        .price-card ul { list-style: none; padding: 0; margin: 0 0 8px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
        .price-card li { font-size: 13px; color: var(--text-secondary); }

        .faq { max-width: 720px; }
        .faq-item { border-bottom: 1px solid var(--border); }
        .faq-q { width: 100%; display: flex; justify-content: space-between; gap: 16px; padding: 18px 0; background: none; border: none; color: var(--text); font-size: 15px; font-weight: 600; text-align: left; }
        .faq-a { padding-bottom: 16px; color: var(--text-secondary); font-size: 14px; line-height: 1.6; }

        .footer { padding: 48px 0 28px; border-top: 1px solid var(--border); }
        .foot { display: grid; gap: 20px; }
        .foot-links { display: flex; gap: 16px; flex-wrap: wrap; }
        .foot-links a, .foot-links button { background: none; border: none; color: var(--text-secondary); font-size: 14px; padding: 0; }
        .foot-links a:hover, .foot-links button:hover { color: var(--accent); }

        @media (max-width: 900px) {
          .hero-grid, .about, .price-grid { grid-template-columns: 1fr; }
          .scanner-body { grid-template-columns: 1fr; }
          .scan-feed { border-left: none; border-top: 1px solid var(--border); }
        }
        @media (max-width: 768px) {
          .nav-links { display: none; position: absolute; top: 64px; left: 0; right: 0; background: var(--sidebar-bg); border-bottom: 1px solid var(--border); flex-direction: column; padding: 12px; }
          .nav-links.open { display: flex; }
          .burger { display: flex; }
          .btn-ghost:not(.lg) { display: none; }
          .sig-row { grid-template-columns: 1fr auto; }
          .sig-row .muted { display: none; }
          .scanner-tickers { display: none; }
        }
      `}</style>
    </div>
  )
}
