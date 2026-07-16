import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts'
import { api } from './api'
import {
  useLivePrices, CountUp, useReveal, RESULT_LABEL,
  TG_CHANNEL, TG_BOT,
} from './shared'

function useLiveStats() {
  const [stats, setStats] = useState(null)
  const [curve, setCurve] = useState([])
  const [recent, setRecent] = useState([])
  useEffect(() => {
    async function load() {
      try {
        const [s, h] = await Promise.all([api.getStats(), api.getHistory(200)])
        setStats(s)
        setRecent(h.slice(0, 8))
        const byDay = {}
        h.slice().reverse().forEach(t => {
          const day = t.date || '—'
          byDay[day] = (byDay[day] || 0) + parseFloat(t.pnl || 0)
        })
        let cum = 0
        setCurve(Object.keys(byDay).sort().map(day => {
          cum += byDay[day]
          return { date: day, equity: cum }
        }))
      } catch { /* ignore */ }
    }
    load()
    const id = setInterval(load, 60000)
    return () => clearInterval(id)
  }, [])
  return { stats, curve, recent }
}

const FAQ = [
  { q: 'Как вы находите сигналы?', a: 'Слушаем сигнальные Telegram-каналы через AI — распознаём текст и картинки, достаём entry/stop/TP и публикуем на сайте и в нашем канале.' },
  { q: 'Насколько точны сигналы?', a: 'Мы не улучшаем то, что публикует канал — только извлекаем уровни и сверяем результат с ценами Bybit. Если канал закрыл сделку — статус обновится автоматически.' },
  { q: 'Может ли NOWICKI торговать автоматически?', a: 'Нет. NOWICKI только показывает сигналы и уведомляет — решение и вход всегда твои.' },
  { q: 'Сколько стоит?', a: 'Базовый доступ бесплатный. Premium открывает полную историю и PnL по дням — см. тарифы ниже.' },
]

const TIERS = [
  { key: 'free', name: 'Free', price: '0', unit: 'навсегда', features: ['Живая лента сигналов', 'Винрейт открыт всем', 'Скринер рынка'] },
  { key: 'premium', name: 'Premium', price: '29', unit: '/мес', features: ['Полная история сделок', 'PnL по дням', 'Расширенный AI'], popular: true },
  { key: 'vip', name: 'VIP', price: '79', unit: '/мес', features: ['Всё из Premium', 'Приоритетный AI', 'Закрытый канал — скоро'] },
]

export default function Landing() {
  const navigate = useNavigate()
  const prices = useLivePrices()
  const { stats, curve, recent } = useLiveStats()
  const [openFaq, setOpenFaq] = useState(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [dark, setDark] = useState(() => {
    const s = localStorage.getItem('theme')
    if (s) return s === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useReveal([stats, recent])

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
            <a href="#honest" onClick={e => { e.preventDefault(); go('#honest') }}>Честность</a>
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

      {/* Hero: brand + one line + one CTA + live equity as visual plane */}
      <section className="hero">
        <div className="hero-plane" aria-hidden="true" />
        <div className="hero-inner">
          <p className="brand-hero animate-in">NOWICKI</p>
          <h1 className="hero-line animate-in">Сигналы из Telegram — с честным трек-рекордом</h1>
          <p className="hero-sub animate-in">
            AI достаёт entry / stop / TP из каналов и сверяет результат с Bybit. Без обещаний «иксов».
          </p>
          <div className="hero-cta animate-in">
            <button type="button" className="btn-solid lg" onClick={() => navigate('/app/overview?auth=register')}>
              Открыть платформу
            </button>
            <a className="btn-ghost lg" href={TG_CHANNEL} target="_blank" rel="noopener noreferrer">
              Наш канал
            </a>
          </div>
          {prices && (
            <div className="hero-tickers animate-in" aria-live="polite">
              <span>BTC <b>${prices.btc.price}</b> <i className={prices.btc.positive ? 'pos' : 'neg'}>{prices.btc.change}%</i></span>
              <span>ETH <b>${prices.eth.price}</b> <i className={prices.eth.positive ? 'pos' : 'neg'}>{prices.eth.change}%</i></span>
            </div>
          )}
        </div>
        <div className="hero-visual animate-in">
          <div className="equity-plane">
            <div className="eq-meta">
              <span>Суммарный PnL · живые данные</span>
              <strong className={up == null ? '' : up ? 'pos' : 'neg'}>
                {totalRoi != null ? `${up ? '+' : ''}${totalRoi.toFixed(1)}%` : '—'}
              </strong>
            </div>
            <div className="eq-chart">
              {curve.length > 1 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={curve}>
                    <YAxis hide domain={['auto', 'auto']} />
                    <Line type="monotone" dataKey="equity" stroke="var(--accent)" strokeWidth={2.5} dot={false} animationDuration={1200} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="eq-empty">Накопление данных…</div>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="trust-band">
        <div className="inner band">
          <div className="band-item reveal">
            <CountUp className="band-num" value={stats?.all_time?.winrate ?? '—'} suffix={stats ? '%' : ''} />
            <span>Винрейт</span>
          </div>
          <div className="band-item reveal">
            <CountUp className="band-num" value={stats?.all_time?.total ?? '—'} />
            <span>Сделок закрыто</span>
          </div>
          <div className="band-item reveal">
            <span className="band-num">24/7</span>
            <span>Мониторинг каналов</span>
          </div>
          <div className="band-item reveal">
            <span className="band-num">Bybit</span>
            <span>Реальные цены</span>
          </div>
        </div>
      </section>

      <section id="signals" className="section">
        <div className="inner">
          <h2 className="sec-title reveal">Последние сигналы</h2>
          <p className="sec-sub reveal">Реальные входы и выходы. Ничего не подправлено задним числом.</p>
          <div className="signal-rows reveal">
            {(recent || []).map((t) => {
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
            {!recent.length && <div className="muted pad">Загрузка…</div>}
          </div>
          <button type="button" className="btn-ghost" style={{ marginTop: 20 }} onClick={() => navigate('/app/overview')}>
            Смотреть на платформе →
          </button>
        </div>
      </section>

      <section id="honest" className="section alt">
        <div className="inner honest">
          <div className="reveal">
            <h2 className="sec-title">Честность вместо «иксов»</h2>
            <ul className="honest-list">
              <li>Живой винрейт открыт всем — не только удачные сделки</li>
              <li>Метрики как есть, без приукрашивания</li>
              <li>Нет доступа к твоим средствам — только сигналы</li>
              <li>Закрытие каналом обновляется автоматически</li>
            </ul>
          </div>
          <div className="honest-cta reveal">
            <a className="btn-solid" href={TG_BOT} target="_blank" rel="noopener noreferrer">Telegram-бот</a>
            <a className="btn-ghost" href={TG_CHANNEL} target="_blank" rel="noopener noreferrer">Канал с сигналами</a>
          </div>
        </div>
      </section>

      <section id="pricing" className="section">
        <div className="inner">
          <h2 className="sec-title reveal">Тарифы</h2>
          <p className="sec-sub reveal">3 дня Premium при регистрации. Оплата подключается отдельно — сейчас можно протестировать доступ.</p>
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
                <button
                  type="button"
                  className="faq-q"
                  aria-expanded={openFaq === i}
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                >
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
            <p className="muted">Ретрансляция сигналов из Telegram с честной статистикой на Bybit.</p>
          </div>
          <div className="foot-links">
            <a href={TG_CHANNEL} target="_blank" rel="noopener noreferrer">Канал</a>
            <a href={TG_BOT} target="_blank" rel="noopener noreferrer">Бот</a>
            <button type="button" onClick={() => navigate('/app/overview')}>Платформа</button>
          </div>
          <div className="muted small">© 2026 NOWICKI. Не является финансовой рекомендацией.</div>
        </div>
      </footer>

      <style>{`
        .lp { min-height: 100vh; background: var(--bg); color: var(--text); font-family: var(--font-ui); overflow-x: hidden; }
        .reveal { opacity: 0; transform: translateY(20px); transition: opacity .65s ease, transform .65s ease; }
        .reveal.in { opacity: 1; transform: none; }
        .animate-in { animation: fadeIn .55s ease forwards; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
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
        .btn-solid:hover { filter: brightness(1.05); }
        .btn-solid.lg { padding: 14px 26px; font-size: 15px; }
        .btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); border-radius: 10px; padding: 10px 16px; font-weight: 600; font-size: 14px; text-decoration: none; display: inline-flex; align-items: center; }
        .btn-ghost.lg { padding: 14px 22px; font-size: 15px; }
        .btn-ghost:hover { border-color: var(--accent); color: var(--accent); }

        .hero { position: relative; min-height: min(92vh, 860px); display: flex; flex-direction: column; justify-content: flex-end; padding: 48px 0 0; overflow: hidden; }
        .hero-plane { position: absolute; inset: 0; background:
          radial-gradient(ellipse 90% 60% at 50% -10%, color-mix(in srgb, var(--accent) 28%, transparent), transparent 55%),
          linear-gradient(180deg, var(--bg) 0%, var(--surface) 100%);
          pointer-events: none; }
        .hero-inner { position: relative; z-index: 1; max-width: 1120px; width: 100%; margin: 0 auto; padding: 0 20px 28px; }
        .brand-hero { font-family: var(--font-display); font-size: clamp(56px, 14vw, 128px); font-weight: 800; letter-spacing: -.04em; line-height: .9; color: var(--text); margin: 0 0 18px; }
        .hero-line { font-family: var(--font-display); font-size: clamp(22px, 3.2vw, 34px); font-weight: 700; letter-spacing: -.02em; max-width: 18ch; line-height: 1.15; margin: 0 0 12px; }
        .hero-sub { font-size: 17px; color: var(--text-secondary); max-width: 42ch; line-height: 1.55; margin: 0 0 22px; }
        .hero-cta { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; }
        .hero-tickers { display: flex; gap: 18px; font-family: var(--font-mono); font-size: 12px; color: var(--text-tertiary); }
        .hero-tickers b { color: var(--text); } .hero-tickers i { font-style: normal; font-weight: 600; }
        .hero-visual { position: relative; z-index: 1; width: 100%; }
        .equity-plane { max-width: 1120px; margin: 0 auto; padding: 0 20px 0; }
        .equity-plane .eq-meta { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; padding: 0 4px 8px; font-size: 12px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .06em; }
        .equity-plane .eq-meta strong { font-family: var(--font-mono); font-size: 28px; letter-spacing: 0; text-transform: none; }
        .eq-chart { height: clamp(160px, 28vh, 260px); border-top: 1px solid var(--border); background: linear-gradient(180deg, transparent, color-mix(in srgb, var(--accent) 6%, transparent)); }
        .eq-empty { height: 100%; display: grid; place-items: center; color: var(--text-tertiary); font-size: 13px; }

        .trust-band { border-block: 1px solid var(--border); background: var(--surface); }
        .inner { max-width: 1120px; margin: 0 auto; padding: 0 20px; }
        .band { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 36px 20px; }
        .band-item { display: flex; flex-direction: column; gap: 6px; }
        .band-item span:last-child { font-size: 13px; color: var(--text-secondary); }
        .band-num { font-family: var(--font-mono); font-size: 32px; font-weight: 700; color: var(--text); }

        .section { padding: 72px 0; }
        .section.alt { background: var(--surface); border-block: 1px solid var(--border); }
        .sec-title { font-family: var(--font-display); font-size: clamp(28px, 4vw, 40px); font-weight: 800; letter-spacing: -.02em; margin: 0 0 10px; }
        .sec-sub { color: var(--text-secondary); max-width: 48ch; margin: 0 0 28px; line-height: 1.5; }

        .signal-rows { display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: 14px; overflow: hidden; background: var(--surface); }
        .sig-row { display: grid; grid-template-columns: 1fr auto 1fr auto; gap: 12px; align-items: center; padding: 14px 16px; border: none; border-bottom: 1px solid var(--border); background: transparent; color: inherit; text-align: left; font-size: 14px; }
        .sig-row:last-child { border-bottom: none; }
        .sig-row:hover { background: var(--surface-hover); }
        .dir { font-size: 11px; font-weight: 700; font-family: var(--font-mono); padding: 3px 8px; border-radius: 6px; }
        .dir.long { background: var(--long-soft); color: var(--long); }
        .dir.short { background: var(--short-soft); color: var(--short); }

        .honest { display: grid; grid-template-columns: 1.4fr .8fr; gap: 40px; align-items: center; }
        .honest-list { margin: 20px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 14px; }
        .honest-list li { padding-left: 18px; position: relative; color: var(--text-secondary); line-height: 1.5; }
        .honest-list li::before { content: ''; position: absolute; left: 0; top: .55em; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
        .honest-cta { display: flex; flex-direction: column; gap: 10px; }

        .price-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 8px; }
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
          .band { grid-template-columns: 1fr 1fr; }
          .price-grid { grid-template-columns: 1fr; }
          .honest { grid-template-columns: 1fr; }
        }
        @media (max-width: 768px) {
          .nav-links { display: none; position: absolute; top: 64px; left: 0; right: 0; background: var(--sidebar-bg); border-bottom: 1px solid var(--border); flex-direction: column; padding: 12px; }
          .nav-links.open { display: flex; }
          .burger { display: flex; }
          .btn-ghost:not(.lg) { display: none; }
          .sig-row { grid-template-columns: 1fr auto; gap: 8px; }
          .sig-row .muted { display: none; }
          .brand-hero { font-size: 56px; }
        }
      `}</style>
    </div>
  )
}
