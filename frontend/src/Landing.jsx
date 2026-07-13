import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts'
import { api } from './api'

/* ─────────────────────────── DATA HOOKS ─────────────────────────── */
// Реальные цифры вместо "бумажных стратегий": винрейт/PnL из /api/stats,
// кумулятивный PnL по дням и последние сигналы — из /api/history (то же,
// что показывает дашборд, никаких отдельных "витринных" данных для лендинга).
function useLiveStats() {
  const [stats, setStats] = useState(null)
  const [curve, setCurve] = useState([])
  const [recent, setRecent] = useState([])
  useEffect(() => {
    async function load() {
      try {
        const [s, h] = await Promise.all([api.getStats(), api.getHistory(200)])
        setStats(s)
        setRecent(h.slice(0, 6))
        const byDay = {}
        h.slice().reverse().forEach(t => {
          const day = t.date || '—'
          byDay[day] = (byDay[day] || 0) + parseFloat(t.pnl || 0)
        })
        let cum = 0
        setCurve(Object.keys(byDay).sort().map(day => { cum += byDay[day]; return { date: day, equity: cum } }))
      } catch {}
    }
    load(); const id = setInterval(load, 60000); return () => clearInterval(id)
  }, [])
  return { stats, curve, recent }
}

const RESULT_LABEL = { tp1: 'TP1', tp2: 'TP2', tp3: 'TP3', sl: 'Стоп', be: 'Б/У', potential: 'Закрыт', timeout: 'Закрыт', timeout_closed: 'Закрыт', channel_closed: 'Закрыт каналом' }

const CHART_PERIODS = [
  { key: 'week', label: '7д', days: 7 },
  { key: 'month', label: '30д', days: 30 },
  { key: 'all', label: 'Всё время', days: null },
]

function filterCurveByPeriod(curve, days) {
  if (!days) return curve
  const cutoff = new Date(Date.now() - days * 86400000)
  const filtered = curve.filter(c => new Date(c.date) >= cutoff)
  return filtered.length > 1 ? filtered : curve.slice(-2)
}

function useLivePrices() {
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
          btc: { price: parseFloat(btc.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }), change: (parseFloat(btc.price24hPcnt)*100).toFixed(2), positive: parseFloat(btc.price24hPcnt) >= 0 },
          eth: { price: parseFloat(eth.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }), change: (parseFloat(eth.price24hPcnt)*100).toFixed(2), positive: parseFloat(eth.price24hPcnt) >= 0 },
        })
      } catch {}
    }
    fp(); const id = setInterval(fp, 30000); return () => clearInterval(id)
  }, [])
  return prices
}

/* Scroll-reveal: добавляет .in элементам с классом .reveal при появлении */
function useReveal(deps = []) {
  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) } })
    }, { threshold: 0.12 })
    document.querySelectorAll('.reveal:not(.in)').forEach(el => io.observe(el))
    return () => io.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}

/* Анимация числа при попадании в зону видимости */
function CountUp({ value, className }) {
  const numeric = /^\d+$/.test(value)
  const ref = useRef(null)
  const [disp, setDisp] = useState(numeric ? '0' : value)
  useEffect(() => {
    if (!numeric) { setDisp(value); return }
    const target = parseInt(value, 10)
    let done = false
    const io = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && !done) {
        done = true
        const dur = 1300, t0 = performance.now()
        const tick = (t) => {
          const p = Math.min(1, (t - t0) / dur)
          const eased = 1 - Math.pow(1 - p, 3)
          setDisp(String(Math.round(target * eased)))
          if (p < 1) requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      }
    }, { threshold: 0.6 })
    if (ref.current) io.observe(ref.current)
    return () => io.disconnect()
  }, [value, numeric])
  return <span ref={ref} className={className}>{disp}</span>
}

/* Курсор-spotlight на карточке */
function onSpot(e) {
  const r = e.currentTarget.getBoundingClientRect()
  e.currentTarget.style.setProperty('--mx', `${((e.clientX - r.left) / r.width) * 100}%`)
  e.currentTarget.style.setProperty('--my', `${((e.clientY - r.top) / r.height) * 100}%`)
}

/* ─────────────────────────── STATIC CONTENT ─────────────────────────── */
// Реальные цифры вместо статики — если данные ещё не загрузились, показываем
// «—», а не нарисованные placeholder-числа.
function buildStats(stats) {
  const at = stats?.all_time
  return [
    { value: at ? String(at.winrate ?? 0) : '—', suffix: at ? '%' : '', label: 'Винрейт за всё время' },
    { value: at ? String(at.total ?? 0) : '—', label: 'Сделок закрыто' },
    { value: '32', label: 'Пар в скринере' },
    { value: '24/7', label: 'Мониторинг каналов' },
  ]
}

const EXCHANGES = [
  { name: 'Bybit', active: true },
  { name: 'Binance', active: false },
  { name: 'OKX', active: false },
  { name: 'KuCoin', active: false },
  { name: 'Bitget', active: false },
]

// Возможности (Toolkit + Benefits, отобрано сильнейшее)
const FEATURES = [
  { icon: '📡', title: 'Ретрансляция сигналов', desc: 'Слушаем проверенные Telegram-каналы — как только выходит пост (текст или картинка), AI достаёт entry/stop/TP и публикует на сайте. Сердце платформы.', wide: true },
  { icon: '✦', title: 'AI Ассистент', desc: 'AI знает текущие сигналы и рынок. Спроси «почему открыли?» — получи ответ за секунду.', badge: 'AI' },
  { icon: '⬡', title: 'Скринер рынка', desc: 'Тепловая карта 32 пар с режимами и ADX. TradingView-график по клику.' },
  { icon: '≡', title: 'История & аналитика', desc: 'Винрейт открыт всем. PnL по дням, каждая сделка и разбивка TP/SL — на Premium.' },
  { icon: '🤖', title: 'Свой Telegram-бот', desc: 'Каждое открытие и закрытие сделки дублируется в наш канал — не нужно держать сайт открытым.' },
  { icon: '⚡', title: 'Smart Trade калькулятор', desc: 'Размер позиции, риск и R:R по TP-уровням — посчитай сделку до входа.', badge: 'NEW' },
]

// Почему мы честнее (Reasons + Security, слитые в один блок доверия)
const HONEST = [
  'Живой винрейт открыт всем — реальный трек-рекорд, а не красивые скриншоты.',
  'Метрики (винрейт, PnL) показываем как есть, без приукрашивания.',
  'NOWICKI не имеет доступа к твоим средствам — мы только показываем сигналы, вход и решение всегда за тобой.',
  'Если канал сам закрывает сделку — статус на сайте обновляется автоматически, без ручных правок задним числом.',
]

const FAQ = [
  { q: 'Как вы находите сигналы?', a: 'Слушаем сигнальные Telegram-каналы через AI — распознаём и текст, и картинки, достаём entry/stop/TP и публикуем на сайте и в нашем канале без ручной модерации.' },
  { q: 'Насколько точны сигналы?', a: 'Мы не меняем и не улучшаем то, что публикует канал — только извлекаем уровни и сверяем результат с реальными ценами Bybit. Если канал сам закрыл сделку — статус обновится автоматически.' },
  { q: 'Может ли NOWICKI торговать автоматически?', a: 'Нет — NOWICKI только показывает сигналы и уведомляет тебя, решение и вход всегда твои. Автоисполнение не планируется.' },
  { q: 'Безопасно ли использовать NOWICKI?', a: 'NOWICKI не имеет доступа к твоим средствам. Для просмотра сигналов API-ключи не нужны.' },
  { q: 'Сколько стоит NOWICKI?', a: 'Базовый доступ (обзор рынка, скринер, лента сигналов, винрейт) бесплатный навсегда. Premium открывает полную историю сделок и PnL по дням — смотри раздел Тарифы.' },
]

const SCAN_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'LINK']

function MiniChart({ positive, width = 160, height = 60 }) {
  const pts = positive
    ? "0,55 25,48 50,40 75,28 100,18 125,10 160,5"
    : "0,5 35,12 70,22 95,32 120,42 145,50 160,55"
  const color = positive ? '#00e5a8' : '#ff4f60'
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <defs>
        <linearGradient id={`lg${positive ? 'p' : 'n'}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <polygon points={`0,55 ${pts} ${width},55`} fill={`url(#lg${positive ? 'p' : 'n'})`}/>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round"/>
    </svg>
  )
}

/* Живой showcase — центр сцены: индикатор мониторинга каналов + реальная кривая PnL */
function LiveShowcase({ prices, curve, visibleCurve, totalRoi, chartPeriod, setChartPeriod, navigate }) {
  const [scanIdx, setScanIdx] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setScanIdx(i => (i + 1) % SCAN_COINS.length), 1100)
    return () => clearInterval(id)
  }, [])
  const up = totalRoi == null ? null : totalRoi >= 0
  return (
    <div className="showcase reveal">
      <div className="sh-chrome">
        <span className="sh-dot r" /><span className="sh-dot a" /><span className="sh-dot g" />
        <span className="sh-url">nowicki.trade/app</span>
        <span className="sh-live"><span className="scan-dot-sm" />LIVE</span>
        {prices && (
          <span className="sh-prices">
            <span>BTC <b>${prices.btc.price}</b> <i className={prices.btc.positive ? 'pos' : 'neg'}>{prices.btc.positive ? '▲' : '▼'}{Math.abs(prices.btc.change)}%</i></span>
            <span>ETH <b>${prices.eth.price}</b> <i className={prices.eth.positive ? 'pos' : 'neg'}>{prices.eth.positive ? '▲' : '▼'}{Math.abs(prices.eth.change)}%</i></span>
          </span>
        )}
      </div>

      <div className="sh-body">
        {/* Радар-сканер */}
        <div className="sh-scanner">
          <div className="radar">
            <div className="radar-ring" />
            <div className="radar-ring r2" />
            <div className="radar-ring r3" />
            <div className="radar-sweep" />
            <div className="radar-core">{SCAN_COINS[scanIdx]}</div>
            {SCAN_COINS.map((c, i) => {
              const ang = (i / SCAN_COINS.length) * Math.PI * 2
              const rad = 38 + (i % 3) * 14
              const x = 50 + Math.cos(ang) * rad
              const y = 50 + Math.sin(ang) * rad
              return <span key={c} className={`radar-blip ${i === scanIdx ? 'on' : ''}`} style={{ left: `${x}%`, top: `${y}%` }} />
            })}
          </div>
          <div className="sh-scan-text">
            <div className="sh-scan-now"><span className="scan-dot-sm" />Отслеживаю <b>{SCAN_COINS[scanIdx]}/USDT</b></div>
            <div className="sh-scan-sub">Каналы · AI-разбор текста и картинок · публикуем сразу</div>
          </div>
        </div>

        {/* Реальная кривая PnL по всем сигналам */}
        <div className="sh-equity">
          <div className="sh-eq-top">
            <span className="sh-eq-label">Все сигналы · реальные данные</span>
            <div className="bv-period-switch">
              {CHART_PERIODS.map(p => (
                <button key={p.key} className={`bv-period-btn ${chartPeriod === p.key ? 'active' : ''}`} onClick={() => setChartPeriod(p.key)}>{p.label}</button>
              ))}
            </div>
          </div>
          <div className="sh-eq-roi" style={{ color: up == null ? 'var(--text-tertiary)' : up ? 'var(--long)' : 'var(--short)' }}>
            {totalRoi != null ? `${up ? '+' : ''}${totalRoi.toFixed(1)}%` : '—'}
          </div>
          <div className="sh-eq-cap">суммарный PnL, % (все закрытые сделки)</div>
          <div className="sh-eq-chart">
            {visibleCurve.length > 1 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={visibleCurve}>
                  <YAxis hide domain={['auto', 'auto']} />
                  <Line type="monotone" dataKey="equity" stroke={up ? 'var(--long)' : 'var(--short)'} strokeWidth={2.5} dot={false} animationDuration={1400} />
                </LineChart>
              </ResponsiveContainer>
            ) : <div className="sh-eq-empty">Накопление данных...</div>}
          </div>
          <button className="sh-eq-btn" onClick={() => navigate('/app')}>Открыть дашборд →</button>
        </div>
      </div>
    </div>
  )
}

/* ─────────────────────────── PAGE ─────────────────────────── */
export default function Landing() {
  const navigate = useNavigate()
  const prices = useLivePrices()
  const { stats, curve, recent } = useLiveStats()
  const STATS = buildStats(stats)
  const [chartPeriod, setChartPeriod] = useState('all')
  const periodDays = CHART_PERIODS.find(p => p.key === chartPeriod)?.days
  const visibleCurve = filterCurveByPeriod(curve, periodDays)
  // curve — кумулятивный PnL (%) по ВСЕЙ истории; чтобы получить изменение
  // только за выбранный период, вычитаем значение на точке ПЕРЕД началом
  // видимого окна (а не делим, это не мультипликативный equity).
  const cutIdx = curve.length - visibleCurve.length
  const baseline = cutIdx > 0 ? curve[cutIdx - 1].equity : 0
  const totalRoi = visibleCurve.length ? (visibleCurve[visibleCurve.length - 1].equity - baseline) : null
  const [menuOpen, setMenuOpen] = useState(false)
  const [openFaq, setOpenFaq] = useState(null)
  const [dark, setDark] = useState(() => {
    const s = localStorage.getItem('theme')
    if (s) return s === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useReveal([stats])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  const NAV = [
    { label: 'Сигналы', href: '#signals' },
    { label: 'Возможности', href: '#features' },
    { label: 'Честность', href: '#honest' },
    { label: 'Тарифы', href: '#faq' },
  ]
  const goAnchor = (e, href) => {
    e.preventDefault(); setMenuOpen(false)
    document.querySelector(href)?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <div className="lp">

      {/* ── ANNOUNCEMENT BAR — информационная полоса, без CTA (кнопки есть в навбаре и hero) ── */}
      <div className="announce-bar">
        <span className="announce-dot" />
        <span>✦ NOWICKI — AI разбирает сигналы из каналов и объясняет каждый в реальном времени</span>
      </div>

      {/* ── NAVBAR ── */}
      <nav className="navbar glass">
        <div className="nav-inner">
          <div className="nav-logo" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <div className="nav-logo-icon">N</div>
            <span className="nav-logo-text gradient-text">NOWICKI</span>
          </div>

          <div className={`nav-links ${menuOpen ? 'open' : ''}`}>
            {NAV.map(l => (
              <a key={l.label} className="nav-link" href={l.href} onClick={e => goAnchor(e, l.href)}>{l.label}</a>
            ))}
          </div>

          <div className="nav-right">
            <button className="theme-btn" onClick={() => setDark(d => !d)}>{dark ? '☀' : '☾'}</button>
            <button className="btn-login" onClick={() => navigate('/app?auth=login')}>Войти</button>
            <button className="btn-trial" onClick={() => navigate('/app?auth=register')}>Начать бесплатно</button>
            <button className="burger-btn" onClick={() => setMenuOpen(o => !o)}>
              <span/><span/><span/>
            </button>
          </div>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section className="hero">
        <div className="aurora">
          <span className="aurora-blob b1" />
          <span className="aurora-blob b2" />
          <span className="aurora-blob b3" />
        </div>
        <div className="hero-grid-overlay" />
        <div className="hero-inner">
          <div className="hero-badge animate-in">
            <span className="hb-dot" />
            <span>Новое: AI-ассистент объясняет каждый сигнал</span>
          </div>

          <h1 className="hero-title animate-in">
            Сигналы из каналов,<br/>
            <span className="gradient-text">которым можно верить</span>
          </h1>
          <p className="hero-sub animate-in">
            Собираем сигналы из проверенных Telegram-каналов, AI достаёт entry/stop/TP и сверяет результат с реальными ценами Bybit. Винрейт и PnL — как есть, без обещаний «иксов».
          </p>

          <div className="hero-actions animate-in">
            <button className="btn-hero-primary" onClick={() => navigate('/app?auth=register')}>
              <span>Начать бесплатно</span>
              <span className="btn-arrow">→</span>
            </button>
            <button className="btn-hero-secondary" onClick={() => document.querySelector('#signals')?.scrollIntoView({ behavior: 'smooth' })}>
              Смотреть сигналы
            </button>
          </div>

          <div className="hero-social-proof animate-in">
            <span className="hb-dot" />
            <div className="hsp-text">
              Живой винрейт открыт всем — <span className="hsp-link" onClick={() => navigate('/app')}>смотри трек-рекорд →</span>
            </div>
          </div>

          <LiveShowcase
            prices={prices} curve={curve} visibleCurve={visibleCurve} totalRoi={totalRoi}
            chartPeriod={chartPeriod} setChartPeriod={setChartPeriod} navigate={navigate}
          />
        </div>
      </section>

      {/* ── STATS + EXCHANGES (trust band) ── */}
      <section className="stats-section">
        <div className="section-inner">
          <div className="stats-grid">
            {STATS.map((s, i) => (
              <div key={i} className="stat-card reveal" style={{ transitionDelay: `${i * 80}ms` }}>
                <div className="stat-val gradient-text"><CountUp value={s.value} />{s.suffix || ''}</div>
                <div className="stat-label">{s.label}</div>
              </div>
            ))}
          </div>
          <div className="exchanges-row reveal">
            <span className="exchanges-eyebrow">Биржи:</span>
            {EXCHANGES.map((e, i) => (
              <div key={i} className={`exchange-badge ${e.active ? 'active' : 'soon'}`}>
                <span>{e.name}</span>
                {!e.active && <span className="exchange-soon-tag">скоро</span>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── SIGNALS (real data) ── */}
      <section id="signals" className="strategies-section">
        <div className="section-inner">
          <div className="sec-head reveal">
            <div className="section-label">Живая лента</div>
            <h2 className="section-heading center">Последние сигналы — реальные результаты</h2>
            <p className="section-sub center">Каждый сигнал — реальная сделка с реальным входом и выходом на Bybit. Ничего не нарисовано и не подправлено задним числом.</p>
          </div>
          <div className="strategy-scroll reveal">
            {(recent || []).map((t, i) => {
              const pos = (t.pnl ?? 0) >= 0
              return (
                <div key={t.id ?? i} className="strategy-card spot" onMouseMove={onSpot}>
                  <div className="sc-header">
                    <div className="sc-name">{t.symbol.replace('/USDT', '')}</div>
                    <div className="sc-tags"><span className="sc-exchange">{t.signal}</span></div>
                  </div>
                  <div className="sc-roi">PnL <span className={`sc-roi-val ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{t.pnl}%</span></div>
                  <div className="sc-chart"><MiniChart positive={pos} /></div>
                  <div className="sc-stats">
                    <div className="sc-stat"><span>Результат</span><span>{RESULT_LABEL[t.result] || t.result}</span></div>
                    <div className="sc-stat"><span>Вход</span><span>{t.entry}</span></div>
                    <div className="sc-stat"><span>Дата</span><span style={{fontSize:10}}>{t.date}</span></div>
                  </div>
                  <button className="sc-btn" onClick={() => navigate('/app')}>▶ Открыть</button>
                </div>
              )
            })}
            {!recent.length && <div className="strategy-card" style={{display:'flex',alignItems:'center',justifyContent:'center',color:'var(--text-tertiary)',fontSize:13}}>Загрузка...</div>}
          </div>
        </div>
      </section>

      {/* ── FEATURES (bento) ── */}
      <section id="features" className="features-section">
        <div className="section-inner">
          <div className="sec-head reveal">
            <div className="section-label">Возможности</div>
            <h2 className="section-heading center">Всё для умной торговли<br/>в одном интерфейсе</h2>
          </div>
          <div className="bento reveal">
            {FEATURES.map((f, i) => (
              <div key={i} className={`bento-card spot ${f.wide ? 'wide' : ''}`} onMouseMove={onSpot}>
                {f.badge && <span className={`bento-badge ${f.badge === 'NEW' ? 'new' : ''}`}>{f.badge}</span>}
                <div className="bento-icon">{f.icon}</div>
                <h3 className="bento-title">{f.title}</h3>
                <p className="bento-desc">{f.desc}</p>
                <button className="bento-link" onClick={() => navigate('/app')}>Открыть →</button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── HONEST (Reasons + Security merged) ── */}
      <section id="honest" className="honest-section">
        <div className="section-inner honest-inner">
          <div className="honest-text reveal">
            <div className="section-label">Почему NOWICKI</div>
            <h2 className="section-heading">Честность вместо<br/>обещаний «иксов»</h2>
            <p className="section-sub" style={{ margin: '14px 0 24px' }}>
              Большинство сигнальных сервисов скрывают реальную доходность. Мы делаем наоборот — показываем всё как есть.
            </p>
            <ul className="honest-list">
              {HONEST.map((h, i) => <li key={i}><span className="check">✓</span> {h}</li>)}
            </ul>
            <button className="btn-hero-primary" onClick={() => navigate('/app')}>
              <span>Открыть трек-рекорд</span><span className="btn-arrow">→</span>
            </button>
          </div>
          <div className="honest-visual reveal">
            <div className="bv-card spot" onMouseMove={onSpot}>
              <div className="bv-top">
                <span className="bv-eyebrow">ВСЕ СИГНАЛЫ · РЕАЛЬНЫЕ ДАННЫЕ</span>
                <div className="bv-period-switch">
                  {CHART_PERIODS.map(p => (
                    <button key={p.key} className={`bv-period-btn ${chartPeriod === p.key ? 'active' : ''}`} onClick={() => setChartPeriod(p.key)}>{p.label}</button>
                  ))}
                </div>
              </div>
              <div className="bv-roi" style={{ color: totalRoi == null ? 'var(--text-tertiary)' : totalRoi >= 0 ? 'var(--long)' : 'var(--short)' }}>
                {totalRoi != null ? `${totalRoi >= 0 ? '+' : ''}${totalRoi.toFixed(1)}%` : '—'}
              </div>
              <div className="bv-cap">Суммарный PnL, % (все закрытые сделки)</div>
              {visibleCurve.length > 1 ? (
                <div style={{ width: '100%', height: 90 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={visibleCurve}>
                      <YAxis hide domain={['auto', 'auto']} />
                      <Line type="monotone" dataKey="equity" stroke={totalRoi >= 0 ? 'var(--long)' : 'var(--short)'} strokeWidth={2.5} dot={false} animationDuration={1400} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : <div style={{ fontSize: 12, color: 'var(--text-tertiary)', height: 90, display: 'flex', alignItems: 'center' }}>Накопление данных...</div>}
              <div className="bv-mini-grid">
                {[['Источник','Telegram-каналы'],['Мониторинг','24/7'],['Сделок', String(stats?.all_time?.total ?? '—')],['Винрейт', stats?.all_time?.winrate != null ? `${stats.all_time.winrate}%` : '—']].map(([l,v],i)=>(
                  <div key={i} className="bv-mini">
                    <div className="bv-mini-l">{l}</div>
                    <div className="bv-mini-v">{v}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── STEPS ── */}
      <section className="steps-section">
        <div className="section-inner">
          <div className="sec-head reveal"><div className="section-label">Как начать</div><h2 className="section-heading center">За 3 простых шага</h2></div>
          <div className="steps-grid">
            {[
              { n: 1, t: 'Открой платформу', d: 'Зайди на NOWICKI — работает прямо в браузере, регистрация для просмотра не нужна.' },
              { n: 2, t: 'Следи за сигналами', d: 'Канал публикует вход — AI достаёт entry/stop/TP и показывает на сайте и в Telegram.' },
              { n: 3, t: 'Спроси AI', d: 'AI объяснит каждый сигнал — почему вошли, какие риски, что делать дальше.' },
            ].map((s, i) => (
              <div key={i} className="step reveal spot" onMouseMove={onSpot} style={{ transitionDelay: `${i * 90}ms` }}>
                <div className="step-num">{s.n}</div>
                <h3 className="step-title">{s.t}</h3>
                <p className="step-desc">{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── COMMUNITY ── */}
      <section className="community-section">
        <div className="section-inner">
          <div className="community-card reveal">
            <div className="community-text">
              <h2 className="section-heading">Присоединяйся к сообществу<br/>NOWICKI</h2>
              <p className="community-sub">Сигналы, разборы стратегий и поддержка — в Telegram и Discord.</p>
              <div style={{display:'flex',gap:12,flexWrap:'wrap',alignItems:'center'}}>
                <button className="community-btn tg" disabled style={{opacity:0.55,cursor:'default'}}>✈ Telegram</button>
                <button className="community-btn dc" disabled style={{opacity:0.55,cursor:'default'}}>Discord</button>
                <span style={{fontSize:11,fontWeight:700,letterSpacing:'0.08em',color:'var(--text-tertiary)',border:'1px solid var(--border)',borderRadius:20,padding:'4px 10px'}}>СКОРО</span>
              </div>
            </div>
            <div className="community-visual">
              <div className="cv-pulse"><span /><span /><span /></div>
              <div style={{fontSize:13,color:'var(--text-secondary)',marginTop:12}}>Каналы сообщества запускаются</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section id="faq" className="faq-section">
        <div className="section-inner">
          <div className="sec-head reveal"><h2 className="section-heading center">Частые вопросы</h2></div>
          <div className="faq-list reveal">
            {FAQ.map((f, i) => (
              <div key={i} className={`faq-item ${openFaq === i ? 'open' : ''}`}>
                <button className="faq-q" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
                  <span>{f.q}</span>
                  <span className="faq-arrow">{openFaq === i ? '▲' : '▼'}</span>
                </button>
                {openFaq === i && <div className="faq-a">{f.a}</div>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="cta-section">
        <div className="section-inner">
          <div className="cta-card reveal">
            <div className="cta-glow" />
            <div className="cta-glow-2" />
            <div className="cta-eyebrow">🚀 Бесплатно · Без регистрации</div>
            <h2 className="cta-title">Начни торговать<br/><span className="gradient-text">умнее прямо сейчас</span></h2>
            <p className="cta-sub">Каналы уже публикуют сигналы. Открой платформу и посмотри последний.</p>
            <button className="btn-hero-primary" style={{fontSize:16,padding:'16px 36px'}} onClick={() => navigate('/app')}>
              Открыть платформу →
            </button>
            <div className="cta-notes">
              <span>✓ Без обязательств</span>
              <span>✓ Без скрытых комиссий</span>
              <span>✓ Прозрачная статистика</span>
              <span>✓ Работает 24/7</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="footer">
        <div className="section-inner">
          <div className="footer-top">
            <div className="footer-brand">
              <div className="nav-logo" style={{marginBottom:12}}>
                <div className="nav-logo-icon">N</div>
                <span className="nav-logo-text gradient-text">NOWICKI</span>
              </div>
              <p className="footer-desc">AI-платформа для поиска крипто-сигналов на Bybit. Только алгоритм, никаких эмоций.</p>
              <div className="footer-socials">
                {['✈','💬','🐦','📺'].map((s,i) => <button key={i} className="social-btn">{s}</button>)}
              </div>
            </div>
            <div className="footer-cols">
              {[
                { title: 'Платформа', links: [['Сигналы','#signals'],['Возможности','#features'],['Честность','#honest'],['FAQ','#faq']] },
                { title: 'Продукт', links: [['Открыть приложение','app'],['Тарифы','app'],['История','app'],['AI Ассистент','app']] },
                { title: 'Компания', links: [['О нас','app'],['Безопасность','#honest'],['Поддержка','app']] },
              ].map((col, i) => (
                <div key={i} className="footer-col">
                  <div className="footer-col-title">{col.title}</div>
                  {col.links.map(([label, target]) => (
                    <a key={label} className="footer-link" onClick={() => target === 'app' ? navigate('/app') : document.querySelector(target)?.scrollIntoView({ behavior: 'smooth' })}>{label}</a>
                  ))}
                </div>
              ))}
            </div>
          </div>
          <div className="footer-bottom">
            <span>© 2026 NOWICKI. Не является финансовой рекомендацией.</span>
            <span>Поддержка · Живой чат 24/7</span>
            <button className="theme-btn" onClick={() => setDark(d => !d)}>{dark ? '☀ Светлая' : '☾ Тёмная'}</button>
          </div>
        </div>
      </footer>

      <style>{`
        .lp { min-height: 100vh; background: var(--bg); color: var(--text); font-family: var(--font-ui); overflow-x: hidden; }

        /* REVEAL */
        .reveal { opacity: 0; transform: translateY(26px); transition: opacity 0.7s cubic-bezier(.2,.7,.2,1), transform 0.7s cubic-bezier(.2,.7,.2,1); }
        .reveal.in { opacity: 1; transform: none; }

        /* SPOTLIGHT */
        .spot { position: relative; }
        .spot::after { content: ''; position: absolute; inset: 0; border-radius: inherit; background: radial-gradient(420px circle at var(--mx,50%) var(--my,50%), var(--accent-soft), transparent 55%); opacity: 0; transition: opacity 0.35s; pointer-events: none; z-index: 0; }
        .spot:hover::after { opacity: 1; }
        .spot > * { position: relative; z-index: 1; }

        /* ANNOUNCE */
        .announce-bar { background: linear-gradient(135deg, var(--accent), var(--purple)); padding: 10px 24px; display: flex; align-items: center; justify-content: center; gap: 12px; font-size: 13px; color: #fff; font-weight: 500; flex-wrap: wrap; text-align: center; }
        .announce-dot { width: 8px; height: 8px; border-radius: 50%; background: #fff; opacity: 0.8; flex-shrink: 0; animation: pulse 2s infinite; }

        /* NAVBAR */
        .navbar { position: sticky; top: 0; z-index: 100; border-bottom: 1px solid var(--border); }
        .nav-inner { max-width: 1200px; margin: 0 auto; padding: 0 24px; display: flex; align-items: center; height: 64px; gap: 24px; }
        .nav-logo { display: flex; align-items: center; gap: 10px; cursor: pointer; flex-shrink: 0; }
        .nav-logo-icon { width: 34px; height: 34px; border-radius: 9px; background: linear-gradient(135deg, var(--accent), var(--purple)); display: flex; align-items: center; justify-content: center; color: #fff; font-size: 18px; font-weight: 900; box-shadow: 0 3px 10px rgba(77,140,245,0.35); }
        .nav-logo-text { font-size: 17px; font-weight: 900; letter-spacing: 0.06em; }
        .nav-links { display: flex; align-items: center; gap: 2px; flex: 1; justify-content: center; }
        .nav-link { padding: 7px 12px; border-radius: 8px; font-size: 14px; font-weight: 500; color: var(--text-secondary); transition: all 0.2s; cursor: pointer; }
        .nav-link:hover { background: var(--surface-hover); color: var(--text); }
        .nav-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .theme-btn { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); width: 34px; height: 34px; border-radius: 9px; font-size: 15px; }
        .btn-login { padding: 8px 16px; border: 1px solid var(--border); background: transparent; color: var(--text); font-size: 14px; font-weight: 500; border-radius: 9px; transition: all 0.2s; }
        .btn-login:hover { background: var(--surface-hover); }
        .btn-trial { padding: 8px 18px; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; font-size: 14px; font-weight: 600; border: none; border-radius: 9px; box-shadow: 0 4px 14px rgba(77,140,245,0.35); transition: all 0.2s; white-space: nowrap; }
        .btn-trial:hover { opacity: 0.88; transform: translateY(-1px); }
        .burger-btn { display: none; border: none; background: transparent; flex-direction: column; gap: 5px; padding: 4px; }
        .burger-btn span { display: block; width: 22px; height: 2px; background: var(--text); border-radius: 2px; }

        /* HERO */
        .hero { padding: 72px 0 80px; overflow: hidden; position: relative; }
        .aurora { position: absolute; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
        .aurora-blob { position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.55; will-change: transform; }
        .aurora-blob.b1 { width: 520px; height: 520px; top: -160px; left: 50%; margin-left: -380px; background: radial-gradient(circle, var(--accent) 0%, transparent 70%); animation: floatA 18s ease-in-out infinite; }
        .aurora-blob.b2 { width: 460px; height: 460px; top: -120px; right: 8%; background: radial-gradient(circle, var(--purple) 0%, transparent 70%); animation: floatB 22s ease-in-out infinite; }
        .aurora-blob.b3 { width: 380px; height: 380px; top: 180px; left: 6%; background: radial-gradient(circle, var(--long) 0%, transparent 70%); opacity: 0.3; animation: floatA 26s ease-in-out infinite reverse; }
        [data-theme="dark"] .aurora-blob { opacity: 0.22; }
        [data-theme="dark"] .aurora-blob.b3 { opacity: 0.14; }
        .hero-grid-overlay { position: absolute; inset: 0; z-index: 0; pointer-events: none; background-image: linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px); background-size: 48px 48px; mask-image: radial-gradient(ellipse 70% 50% at 50% 0%, #000 0%, transparent 70%); -webkit-mask-image: radial-gradient(ellipse 70% 50% at 50% 0%, #000 0%, transparent 70%); opacity: 0.4; }
        .hero-inner { max-width: 1100px; margin: 0 auto; padding: 0 24px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 20px; position: relative; z-index: 1; }
        .hero-badge { display: inline-flex; align-items: center; gap: 8px; background: var(--surface); border: 1px solid var(--border); border-radius: 50px; padding: 6px 14px; font-size: 12px; font-weight: 600; color: var(--text-secondary); box-shadow: var(--shadow-card); }
        .hb-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; flex-shrink: 0; }
        .scan-dot-sm { width: 7px; height: 7px; border-radius: 50%; background: var(--long); display: inline-block; animation: pulse 2s infinite; }

        .hero-title { font-size: clamp(42px, 7vw, 82px); font-weight: 900; line-height: 1.03; letter-spacing: -0.045em; color: var(--text); max-width: 900px; }
        .hero-sub { font-size: 18px; color: var(--text-secondary); line-height: 1.7; max-width: 620px; }
        .hero-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: center; }
        .btn-hero-primary { padding: 14px 28px; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; font-size: 15px; font-weight: 700; border: none; border-radius: 12px; box-shadow: 0 8px 24px rgba(77,140,245,0.4); transition: all 0.2s; display: inline-flex; align-items: center; gap: 8px; }
        .btn-hero-primary:hover { opacity: 0.92; transform: translateY(-2px); box-shadow: 0 12px 32px rgba(77,140,245,0.5); }
        .btn-arrow { transition: transform 0.2s; }
        .btn-hero-primary:hover .btn-arrow { transform: translateX(4px); }
        .btn-hero-secondary { padding: 14px 24px; background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 15px; font-weight: 600; border-radius: 12px; transition: all 0.2s; }
        .btn-hero-secondary:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
        .hero-social-proof { display: flex; align-items: center; gap: 8px; }
        .hsp-text { font-size: 13px; color: var(--text-secondary); }
        .hsp-link { font-weight: 700; color: var(--accent); cursor: pointer; }
        .hsp-link:hover { text-decoration: underline; }

        /* LIVE SHOWCASE */
        .showcase { width: 100%; max-width: 920px; margin-top: 28px; background: var(--surface); border: 1px solid var(--border); border-radius: 18px; box-shadow: var(--shadow-lg); overflow: hidden; }
        .sh-chrome { display: flex; align-items: center; gap: 8px; padding: 11px 16px; background: var(--surface-hover); border-bottom: 1px solid var(--border); }
        .sh-dot { width: 10px; height: 10px; border-radius: 50%; }
        .sh-dot.r { background: var(--short); } .sh-dot.a { background: var(--amber); } .sh-dot.g { background: var(--long); }
        .sh-url { font-size: 11px; color: var(--text-tertiary); font-family: var(--font-mono); margin-left: 6px; }
        .sh-live { display: flex; align-items: center; gap: 5px; font-size: 9px; font-weight: 800; color: var(--long); text-transform: uppercase; letter-spacing: 0.06em; margin-left: auto; }
        .sh-prices { display: flex; gap: 14px; font-size: 11px; color: var(--text-tertiary); font-family: var(--font-mono); }
        .sh-prices b { color: var(--text); font-weight: 700; }
        .sh-prices i { font-style: normal; font-weight: 600; }
        .sh-prices .pos { color: var(--long); } .sh-prices .neg { color: var(--short); }
        .sh-body { display: grid; grid-template-columns: 1fr 1.2fr; gap: 0; }
        .sh-scanner { padding: 28px 24px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px; border-right: 1px solid var(--border); background: var(--bg); }
        .radar { position: relative; width: 170px; height: 170px; }
        .radar-ring { position: absolute; inset: 0; border: 1px solid var(--border-strong); border-radius: 50%; opacity: 0.6; }
        .radar-ring.r2 { inset: 28px; } .radar-ring.r3 { inset: 56px; }
        .radar-sweep { position: absolute; inset: 0; border-radius: 50%; background: conic-gradient(from 0deg, transparent 0deg, var(--accent) 55deg, transparent 90deg); animation: spin 3.2s linear infinite; opacity: 0.35; }
        .radar-core { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 54px; height: 54px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; display: flex; align-items: center; justify-content: center; font-family: var(--font-mono); font-size: 13px; font-weight: 800; box-shadow: 0 4px 16px rgba(77,140,245,0.5); }
        .radar-blip { position: absolute; width: 7px; height: 7px; border-radius: 50%; background: var(--text-tertiary); transform: translate(-50%,-50%); transition: all 0.4s; }
        .radar-blip.on { background: var(--long); box-shadow: 0 0 0 4px rgba(0,229,168,0.25); width: 9px; height: 9px; }
        .sh-scan-text { text-align: center; }
        .sh-scan-now { font-size: 13px; color: var(--text); font-weight: 600; display: flex; align-items: center; gap: 7px; justify-content: center; }
        .sh-scan-now b { font-family: var(--font-mono); color: var(--accent); }
        .sh-scan-sub { font-size: 10px; color: var(--text-tertiary); margin-top: 6px; letter-spacing: 0.02em; }
        .sh-equity { padding: 22px 24px; display: flex; flex-direction: column; }
        .sh-eq-top { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 6px; }
        .sh-eq-label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
        .sh-eq-roi { font-family: var(--font-mono); font-size: 38px; font-weight: 800; line-height: 1; }
        .sh-eq-cap { font-size: 12px; color: var(--text-secondary); margin: 4px 0 10px; }
        .sh-eq-chart { width: 100%; height: 92px; }
        .sh-eq-empty { font-size: 12px; color: var(--text-tertiary); height: 92px; display: flex; align-items: center; }
        .sh-eq-btn { margin-top: 14px; align-self: flex-start; padding: 9px 16px; background: var(--accent-soft); color: var(--accent); border: none; border-radius: 9px; font-size: 13px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
        .sh-eq-btn:hover { background: var(--accent); color: #fff; }
        .bv-period-switch { display: flex; gap: 2px; background: var(--surface-hover); border-radius: 7px; padding: 2px; }
        .bv-period-btn { border: none; background: transparent; color: var(--text-tertiary); font-size: 10px; font-weight: 600; padding: 4px 8px; border-radius: 5px; cursor: pointer; }
        .bv-period-btn.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }

        /* SHARED HEAD */
        .section-inner { max-width: 1100px; margin: 0 auto; padding: 0 24px; }
        .sec-head { text-align: center; margin-bottom: 8px; }
        .section-label { display: inline-block; font-size: 11px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.1em; background: var(--accent-soft); padding: 4px 12px; border-radius: 20px; margin-bottom: 14px; }
        .section-heading { font-size: clamp(26px, 3.6vw, 42px); font-weight: 800; line-height: 1.18; letter-spacing: -0.02em; color: var(--text); }
        .section-heading.center { text-align: center; }
        .section-sub { font-size: 16px; color: var(--text-secondary); line-height: 1.6; }
        .section-sub.center { text-align: center; max-width: 620px; margin: 12px auto 0; }
        .pos { color: var(--long) !important; } .neg { color: var(--short) !important; }

        /* STATS */
        .stats-section { padding: 56px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); background: var(--surface); }
        .stats-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 18px; }
        .stat-card { text-align: center; padding: 30px 18px; background: var(--bg); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow-card); transition: transform 0.25s, box-shadow 0.25s, border-color 0.25s, opacity 0.7s; }
        .stat-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-lg); border-color: var(--accent); }
        .stat-val { font-size: 44px; font-weight: 900; font-family: var(--font-mono); line-height: 1; margin-bottom: 10px; }
        .stat-label { font-size: 13px; color: var(--text-secondary); }
        .exchanges-row { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; align-items: center; margin-top: 28px; }
        .exchanges-eyebrow { font-size: 12px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.08em; margin-right: 4px; }
        .exchange-badge { display: flex; align-items: center; gap: 8px; padding: 9px 18px; border-radius: 10px; border: 1px solid var(--border); font-size: 13px; font-weight: 700; }
        .exchange-badge.active { background: var(--bg); color: var(--text); box-shadow: var(--shadow-card); }
        .exchange-badge.soon { background: transparent; color: var(--text-tertiary); opacity: 0.55; }
        .exchange-soon-tag { font-size: 9px; font-weight: 700; text-transform: uppercase; background: var(--surface-hover); color: var(--text-tertiary); padding: 2px 6px; border-radius: 4px; }

        /* STRATEGIES */
        .strategies-section { padding: 80px 0; }
        .strategy-scroll { width: 100%; overflow-x: auto; display: flex; gap: 16px; padding: 32px 0 12px; scrollbar-width: thin; -webkit-overflow-scrolling: touch; }
        .strategy-card { flex-shrink: 0; width: 240px; background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 18px; box-shadow: var(--shadow-card); transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s; }
        .strategy-card:hover { border-color: var(--accent); transform: translateY(-4px); box-shadow: var(--shadow-lg); }
        .sc-header { margin-bottom: 8px; }
        .sc-name { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 6px; }
        .sc-tags { display: flex; gap: 6px; align-items: center; }
        .sc-exchange { font-size: 10px; color: var(--text-tertiary); background: var(--surface-hover); padding: 2px 8px; border-radius: 5px; }
        .sc-roi { font-size: 11px; color: var(--text-tertiary); margin-bottom: 4px; }
        .sc-roi-val { font-family: var(--font-mono); font-size: 20px; font-weight: 800; margin-left: 4px; }
        .sc-chart { margin: 0 -4px 8px; }
        .sc-stats { display: flex; flex-direction: column; gap: 5px; border-top: 1px solid var(--border); padding-top: 10px; margin-bottom: 12px; }
        .sc-stat { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-secondary); }
        .sc-stat span:last-child { font-family: var(--font-mono); font-weight: 600; color: var(--text); }
        .sc-btn { width: 100%; padding: 10px; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; border: none; border-radius: 9px; font-size: 12px; font-weight: 600; cursor: pointer; transition: opacity 0.2s; }
        .sc-btn:hover { opacity: 0.85; }

        /* FEATURES BENTO */
        .features-section { padding: 80px 0; background: var(--surface-hover); }
        .bento { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 40px; }
        .bento-card { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 28px; box-shadow: var(--shadow-card); transition: transform 0.25s, box-shadow 0.25s, border-color 0.25s, opacity 0.7s; overflow: hidden; }
        .bento-card.wide { grid-column: span 2; display: flex; flex-direction: column; justify-content: center; background: linear-gradient(135deg, var(--surface), var(--accent-soft)); }
        .bento-card:hover { border-color: var(--accent); transform: translateY(-4px); box-shadow: 0 20px 40px rgba(77,140,245,0.12); }
        .bento-badge { position: absolute; top: 16px; right: 16px; z-index: 2; font-size: 9px; font-weight: 800; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.05em; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; }
        .bento-badge.new { background: linear-gradient(135deg, var(--long), #00a875); }
        .bento-icon { font-size: 30px; margin-bottom: 14px; }
        .bento-card.wide .bento-icon { font-size: 40px; }
        .bento-title { font-size: 17px; font-weight: 700; color: var(--text); margin-bottom: 10px; }
        .bento-card.wide .bento-title { font-size: 24px; }
        .bento-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 16px; }
        .bento-link { border: none; background: transparent; color: var(--accent); font-size: 13px; font-weight: 700; padding: 0; cursor: pointer; }

        /* HONEST */
        .honest-section { padding: 80px 0; }
        .honest-inner { display: grid; grid-template-columns: 1fr 1fr; gap: 60px; align-items: center; }
        .honest-list { list-style: none; display: flex; flex-direction: column; gap: 16px; margin: 0 0 32px; }
        .honest-list li { display: flex; align-items: flex-start; gap: 12px; font-size: 15px; color: var(--text-secondary); line-height: 1.55; }
        .check { width: 22px; height: 22px; border-radius: 50%; background: var(--long); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0; margin-top: 1px; }
        .bv-card { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 24px; box-shadow: var(--shadow-lg); }
        .bv-top { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 8px; }
        .bv-eyebrow { font-size: 11px; color: var(--text-tertiary); letter-spacing: 0.03em; }
        .bv-roi { font-family: var(--font-mono); font-size: 36px; font-weight: 800; line-height: 1; }
        .bv-cap { font-size: 12px; color: var(--text-secondary); margin: 4px 0 12px; }
        .bv-mini-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }
        .bv-mini { background: var(--surface-hover); padding: 8px 12px; border-radius: 8px; }
        .bv-mini-l { font-size: 10px; color: var(--text-tertiary); }
        .bv-mini-v { font-family: var(--font-mono); font-size: 14px; font-weight: 700; color: var(--text); }

        /* STEPS */
        .steps-section { padding: 80px 0; background: var(--surface-hover); }
        .steps-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; margin-top: 44px; }
        .step { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 30px; box-shadow: var(--shadow-card); transition: transform 0.25s, box-shadow 0.25s, border-color 0.25s, opacity 0.7s; }
        .step:hover { transform: translateY(-4px); box-shadow: var(--shadow-lg); border-color: var(--accent); }
        .step-num { width: 42px; height: 42px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; font-size: 18px; font-weight: 800; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; box-shadow: 0 4px 14px rgba(77,140,245,0.35); }
        .step-title { font-size: 18px; font-weight: 700; color: var(--text); margin-bottom: 10px; }
        .step-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; }

        /* COMMUNITY */
        .community-section { padding: 80px 0; }
        .community-card { background: var(--surface); border: 1px solid var(--border); border-radius: 20px; padding: 48px; box-shadow: var(--shadow-lg); display: flex; justify-content: space-between; align-items: center; gap: 40px; flex-wrap: wrap; }
        .community-sub { font-size: 15px; color: var(--text-secondary); margin: 14px 0 24px; line-height: 1.6; }
        .community-btn { padding: 12px 24px; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer; transition: opacity 0.2s; }
        .community-btn.tg { background: #229ED9; color: #fff; }
        .community-btn.dc { background: #5865F2; color: #fff; }
        .community-btn:hover { opacity: 0.85; }
        .community-visual { text-align: center; }
        .cv-pulse { position: relative; width: 80px; height: 80px; margin: 0 auto; }
        .cv-pulse span { position: absolute; inset: 0; margin: auto; width: 18px; height: 18px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--purple)); }
        .cv-pulse span:nth-child(2) { width: 100%; height: 100%; background: var(--accent); opacity: 0.15; animation: ripple 2.2s ease-out infinite; }
        .cv-pulse span:nth-child(3) { width: 100%; height: 100%; background: var(--purple); opacity: 0.12; animation: ripple 2.2s ease-out infinite 1.1s; }

        /* FAQ */
        .faq-section { padding: 80px 0; background: var(--surface-hover); }
        .faq-list { max-width: 760px; margin: 36px auto 0; }
        .faq-item { border-bottom: 1px solid var(--border); }
        .faq-q { width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 20px 0; background: transparent; border: none; color: var(--text); font-size: 15px; font-weight: 600; text-align: left; cursor: pointer; transition: color 0.2s; }
        .faq-q:hover { color: var(--accent); }
        .faq-arrow { font-size: 12px; color: var(--text-tertiary); flex-shrink: 0; }
        .faq-a { font-size: 14px; color: var(--text-secondary); line-height: 1.7; padding-bottom: 20px; }

        /* CTA */
        .cta-section { padding: 80px 0; }
        .cta-card { background: var(--surface); border: 1px solid var(--border); border-radius: 24px; padding: 80px 48px; text-align: center; box-shadow: var(--shadow-lg); position: relative; overflow: hidden; }
        .cta-glow { position: absolute; top: -120px; left: 50%; transform: translateX(-50%); width: 600px; height: 500px; background: radial-gradient(circle, var(--accent-soft) 0%, transparent 65%); pointer-events: none; }
        .cta-glow-2 { position: absolute; bottom: -80px; right: -80px; width: 400px; height: 400px; background: radial-gradient(circle, var(--purple-soft) 0%, transparent 65%); pointer-events: none; }
        .cta-eyebrow { display: inline-block; font-size: 12px; font-weight: 600; color: var(--accent); background: var(--accent-soft); padding: 6px 16px; border-radius: 20px; margin-bottom: 20px; position: relative; }
        .cta-title { font-size: clamp(28px, 4.5vw, 52px); font-weight: 900; line-height: 1.1; letter-spacing: -0.025em; color: var(--text); margin-bottom: 16px; position: relative; }
        .cta-sub { font-size: 17px; color: var(--text-secondary); margin-bottom: 36px; position: relative; }
        .cta-notes { display: flex; justify-content: center; gap: 24px; margin-top: 20px; font-size: 13px; color: var(--text-tertiary); flex-wrap: wrap; position: relative; }

        /* FOOTER */
        .footer { border-top: 1px solid var(--border); padding: 56px 0 24px; }
        .footer-top { display: flex; justify-content: space-between; gap: 48px; flex-wrap: wrap; margin-bottom: 40px; }
        .footer-brand { max-width: 260px; }
        .footer-desc { font-size: 13px; color: var(--text-tertiary); line-height: 1.6; margin: 12px 0 16px; }
        .footer-socials { display: flex; gap: 8px; }
        .social-btn { width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); font-size: 16px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.2s; }
        .social-btn:hover { background: var(--surface-hover); transform: translateY(-1px); }
        .footer-cols { display: flex; gap: 40px; flex-wrap: wrap; }
        .footer-col { display: flex; flex-direction: column; gap: 10px; }
        .footer-col-title { font-size: 11px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 4px; }
        .footer-link { font-size: 14px; color: var(--text-tertiary); cursor: pointer; transition: color 0.2s; }
        .footer-link:hover { color: var(--text); }
        .footer-bottom { display: flex; justify-content: space-between; align-items: center; padding-top: 24px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-tertiary); flex-wrap: wrap; gap: 12px; }

        /* KEYFRAMES */
        @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(0,229,168,0.4)} 70%{box-shadow:0 0 0 6px rgba(0,229,168,0)} 100%{box-shadow:0 0 0 0 rgba(0,229,168,0)} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes floatA { 0%,100%{ transform: translate(0,0) scale(1); } 50%{ transform: translate(40px,30px) scale(1.1); } }
        @keyframes floatB { 0%,100%{ transform: translate(0,0) scale(1); } 50%{ transform: translate(-50px,40px) scale(1.08); } }
        @keyframes ripple { 0%{ transform: scale(0.4); opacity: 0.4; } 100%{ transform: scale(1.4); opacity: 0; } }
        .animate-in { animation: fadeIn 0.55s ease forwards; }

        /* RESPONSIVE */
        @media (max-width: 1024px) {
          .stats-grid { grid-template-columns: repeat(2,1fr); }
          .bento { grid-template-columns: repeat(2,1fr); }
          .bento-card.wide { grid-column: span 2; }
          .steps-grid { grid-template-columns: 1fr; }
          .honest-inner { grid-template-columns: 1fr; gap: 40px; }
        }
        @media (max-width: 768px) {
          .nav-links { display: none; position: absolute; top: 64px; left: 0; right: 0; background: var(--sidebar-bg); padding: 16px; border-bottom: 1px solid var(--border); z-index: 99; flex-direction: column; }
          .nav-links.open { display: flex; }
          .burger-btn { display: flex; }
          .btn-login { display: none; }
          /* Навбар должен целиком помещаться в экран — бургер был на x=383 при ширине 375 */
          .nav-inner { padding: 0 14px; gap: 10px; }
          .nav-right { margin-left: auto; gap: 6px; }
          .btn-trial { padding: 7px 12px; font-size: 13px; }
          .announce-bar { padding: 8px 12px; font-size: 12px; gap: 8px; }
          .hero-inner, .section-inner { padding: 0 16px; }
          .hero-sub { font-size: 15px; }
          .stat-val { font-size: 32px; }
          .sh-body { grid-template-columns: 1fr; }
          .sh-scanner { border-right: none; border-bottom: 1px solid var(--border); }
          .sh-prices { display: none; }
          .bento { grid-template-columns: 1fr; }
          .bento-card.wide { grid-column: span 1; }
          .community-card { flex-direction: column; padding: 32px 24px; }
          .cta-card { padding: 48px 22px; }
          .footer-cols { gap: 24px; }
        }
        @media (max-width: 480px) {
          .stats-grid { grid-template-columns: 1fr 1fr; }
          .hero { padding: 40px 0 56px; }
          .theme-btn { display: none; }
          .hero-title { font-size: 34px; }
          .hero-actions { flex-direction: column; width: 100%; }
          .hero-actions .btn-hero-primary, .hero-actions .btn-hero-secondary { width: 100%; justify-content: center; text-align: center; }
          .nav-logo-text { font-size: 15px; }
        }
      `}</style>
    </div>
  )
}
