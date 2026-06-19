import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

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

const STRATEGIES = [
  { name: 'Breakout Strategy', exchange: 'Bybit', dir: 'LONG', roi: 116.6, pnl: 4352, winrate: 73, trades: 22, drawdown: -2.1, fees: 67.49 },
  { name: 'Swing Trading Strategy', exchange: 'Binance', dir: 'LONG', roi: 41.8, pnl: 2587, winrate: 98.9, trades: 93, drawdown: -18.5, fees: 31.04 },
  { name: 'Scalping Strategy', exchange: 'Bybit', dir: 'SHORT', roi: 133.1, pnl: 4088, winrate: 67.1, trades: 366, drawdown: -4.5, fees: 81.33 },
  { name: 'Trend Following', exchange: 'Bybit', dir: 'LONG', roi: 92.4, pnl: 5247, winrate: 100, trades: 13, drawdown: -1.5, fees: 51.44 },
  { name: 'Day Trading Strategy', exchange: 'Bybit', dir: 'SHORT', roi: 46.2, pnl: 2871, winrate: 81.1, trades: 37, drawdown: -7.2, fees: 23.83 },
]

const STATS = [
  { value: '118,000+', label: 'Трейдеров зарегистрировано' },
  { value: '32', label: 'Пар на Bybit' },
  { value: '2 мин', label: 'Интервал сканирования' },
  { value: '24/7', label: 'Работа сканера' },
]

const TOOLS = [
  { icon: '◈', title: 'Сигнал-сканер', desc: 'Самый гибкий инструмент NWICKI. Сканирует 32 пары на Bybit каждые 2 минуты по EMA, RSI, ADX и ATR. Находит лучший сетап автоматически.' },
  { icon: '✦', title: 'AI Ассистент', desc: 'GPT-4o знает текущие сигналы и рынок. Спроси "почему вошли в сделку?" или "какие риски?" — получи ответ за секунду. Как иметь личного аналитика 24/7.' },
  { icon: '⬡', title: 'Скринер рынка', desc: 'Тепловая карта всех 32 пар с режимами (Аптренд/Даунтренд/Флэт), ADX индикатором и TradingView графиком по клику на монету.' },
  { icon: '≡', title: 'История & Аналитика', desc: 'Полная история с PnL по дням, винрейтом, разбивкой по TP1/TP2/TP3 и стопам. Публичный трек-рекорд всех сигналов.' },
  { icon: '⚡', title: 'Терминал', desc: 'Быстрое исполнение сделок через API Bybit с продвинутым управлением ордерами. Трейлинг стоп, частичное закрытие, несколько тейков.' },
]

const BENEFITS = [
  { icon: '📊', title: 'Бэктест и оптимизация стратегии', desc: 'Проверяй стратегию на исторических данных перед запуском' },
  { icon: '🧠', title: 'Торгуй без эмоций', desc: 'Сканер не паникует и не жадничает — только алгоритм' },
  { icon: '🔗', title: 'TradingView интеграция', desc: 'Все графики через TradingView виджеты прямо в платформе' },
  { icon: '💱', title: 'Все инструменты в одном месте', desc: 'Сигналы, аналитика, AI и история в одном интерфейсе' },
]

const SECURITY = [
  { icon: '🛡️', title: 'Безопасная архитектура', desc: 'Мы постоянно усиливаем защиту от новых угроз.' },
  { icon: '🔒', title: 'Твои средства только у тебя', desc: 'NWICKI не имеет доступа к твоему аккаунту на бирже и не может вывести средства.' },
  { icon: '📋', title: 'Прозрачная статистика', desc: 'Все результаты сигналов публичны — ничего не скрываем.' },
]

const FAQ = [
  { q: 'Что такое бэктестинг и зачем он нужен?', a: 'Бэктестинг симулирует сделки на исторических данных. Это показывает как стратегия работала бы в прошлом — лучший способ проверить идею перед реальными деньгами.' },
  { q: 'Насколько точны сигналы NWICKI?', a: 'Сканер использует EMA, RSI, ADX и ATR для анализа. Каждый сигнал имеет Score от 0 до 20 — чем выше, тем сильнее сетап. Историческую статистику смотри в разделе История.' },
  { q: 'Может ли NWICKI торговать автоматически?', a: 'Сейчас NWICKI — это сигнальная платформа. Сканер находит точки входа и уведомляет тебя, ты принимаешь решение о входе. Автоматическое исполнение через API Bybit — в разработке.' },
  { q: 'Безопасно ли использовать NWICKI?', a: 'NWICKI не имеет доступа к твоим средствам. Платформа только анализирует рынок и показывает сигналы. Твои API ключи не требуются для просмотра сигналов.' },
  { q: 'Сколько стоит NWICKI?', a: 'Сейчас платформа полностью бесплатна. В будущем появятся тарифные планы с расширенными функциями. Ранние пользователи получат специальные условия.' },
]

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

export default function Landing() {
  const navigate = useNavigate()
  const prices = useLivePrices()
  const [menuOpen, setMenuOpen] = useState(false)
  const [openFaq, setOpenFaq] = useState(null)
  const [dark, setDark] = useState(() => {
    const s = localStorage.getItem('theme')
    if (s) return s === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <div className="lp">

      {/* ── ANNOUNCEMENT BAR ── */}
      <div className="announce-bar">
        <span className="announce-dot" />
        <span>✦ NWICKI AI — первая платформа где AI сканирует рынок и объясняет каждый сигнал в реальном времени</span>
        <button className="announce-btn" onClick={() => navigate('/app')}>Попробовать бесплатно →</button>
      </div>

      {/* ── NAVBAR ── */}
      <nav className="navbar glass">
        <div className="nav-inner">
          <div className="nav-logo" onClick={() => window.scrollTo(0,0)}>
            <div className="nav-logo-icon">N</div>
            <span className="nav-logo-text gradient-text">NWICKI</span>
          </div>

          <div className={`nav-links ${menuOpen ? 'open' : ''}`}>
            {['Боты', 'Стратегии', 'Функции', 'Тарифы', 'Блог', 'Компания'].map(l => (
              <a key={l} className="nav-link" href="#" onClick={e => { e.preventDefault(); setMenuOpen(false) }}>{l}</a>
            ))}
          </div>

          <div className="nav-right">
            <button className="theme-btn" onClick={() => setDark(d => !d)}>{dark ? '☀' : '☾'}</button>
            <button className="btn-login" onClick={() => navigate('/app')}>Войти</button>
            <button className="btn-trial" onClick={() => navigate('/app')}>Начать бесплатно</button>
            <button className="burger-btn" onClick={() => setMenuOpen(o => !o)}>
              <span/><span/><span/>
            </button>
          </div>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section className="hero">
        <div className="hero-bg-mesh" />
        <div className="hero-inner">
          {prices && (
            <div className="hero-ticker animate-in">
              <span className="ht-live"><span className="scan-dot-sm" />LIVE</span>
              <span className="ht-div" />
              <span className="ht-item">
                <span className="ht-sym">BTC</span>
                <span className="ht-val">${prices.btc.price}</span>
                <span className={`ht-chg ${prices.btc.positive ? 'pos' : 'neg'}`}>{prices.btc.positive ? '▲' : '▼'}{Math.abs(prices.btc.change)}%</span>
              </span>
              <span className="ht-div" />
              <span className="ht-item">
                <span className="ht-sym">ETH</span>
                <span className="ht-val">${prices.eth.price}</span>
                <span className={`ht-chg ${prices.eth.positive ? 'pos' : 'neg'}`}>{prices.eth.positive ? '▲' : '▼'}{Math.abs(prices.eth.change)}%</span>
              </span>
              <span className="ht-div" />
              <span style={{fontSize:11,color:'var(--text-tertiary)'}}>32 пары · обновление каждые 2 мин</span>
            </div>
          )}

          <div className="hero-badge animate-in">
            <span className="hb-dot" />
            <span>Новое: Telegram уведомления о сигналах</span>
          </div>

          <h1 className="hero-title animate-in">
            Торгуй крипто<br/>
            <span className="gradient-text">умнее с AI</span>
          </h1>
          <p className="hero-sub animate-in">
            Сканер анализирует 32 пары на Bybit каждые 2 минуты. AI объясняет каждый сигнал. Ты просто торгуешь.
          </p>

          <div className="hero-actions animate-in">
            <button className="btn-hero-primary" onClick={() => navigate('/app')}>
              <span>Начать бесплатно</span>
              <span className="btn-arrow">→</span>
            </button>
            <button className="btn-hero-secondary" onClick={() => navigate('/app')}>
              Смотреть демо
            </button>
          </div>

          <div className="hero-social-proof animate-in">
            <div className="hsp-avatars">
              {['A','B','C','D','E'].map((l,i) => (
                <div key={i} className="hsp-av" style={{background:`hsl(${i*55+200},65%,50%)`}}>{l}</div>
              ))}
            </div>
            <div className="hsp-text">
              <span className="hsp-count">118,000+</span> трейдеров уже используют NWICKI
            </div>
          </div>

          {/* Strategy cards scroll like 3Commas */}
          <div className="strategy-scroll animate-in">
            {STRATEGIES.map((s, i) => (
              <div key={i} className="strategy-card">
                <div className="sc-header">
                  <div className="sc-name">{s.name}</div>
                  <div className="sc-tags">
                    <span className={`sc-tag ${s.dir === 'LONG' ? 'long' : 'short'}`}>{s.dir}</span>
                    <span className="sc-exchange">{s.exchange}</span>
                  </div>
                </div>
                <div className="sc-roi">ROI <span className="sc-roi-val pos">+{s.roi}%</span></div>
                <div className="sc-chart"><MiniChart positive={s.roi > 0} /></div>
                <div className="sc-stats">
                  <div className="sc-stat"><span>PnL</span><span className="pos">${s.pnl.toLocaleString()}</span></div>
                  <div className="sc-stat"><span>Винрейт</span><span>{s.winrate}%</span></div>
                  <div className="sc-stat"><span>Сделок</span><span>{s.trades}</span></div>
                  <div className="sc-stat"><span>Просадка</span><span className="neg">{s.drawdown}%</span></div>
                </div>
                <button className="sc-btn" onClick={() => navigate('/app')}>▶ Открыть</button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── STATS ── */}
      <section className="stats-section">
        <div className="section-inner">
          <p className="stats-eyebrow">Доверяют трейдеры по всему миру</p>
          <div className="stats-grid">
            {STATS.map((s, i) => (
              <div key={i} className="stat-card animate-in">
                <div className="stat-val gradient-text">{s.value}</div>
                <div className="stat-label">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 3 REASONS ── */}
      <section className="reasons-section">
        <div className="section-inner reasons-inner">
          <div className="reasons-text">
            <div className="section-label">Почему NWICKI</div>
            <h2 className="section-heading">Три причины начать<br/>прямо сегодня</h2>
            <ul className="reasons-list">
              <li><span className="check">✓</span> Автоматизируй анализ рынка и избавься от стресса и эмоциональных ошибок.</li>
              <li><span className="check">✓</span> Настрой сканер под свою стратегию — от скальпинга до свинг-трейдинга.</li>
              <li><span className="check">✓</span> Бэктестинг на полных исторических данных перед входом в рынок.</li>
            </ul>
            <button className="btn-hero-primary" onClick={() => navigate('/app')}>
              <span>Начать бесплатно</span><span className="btn-arrow">→</span>
            </button>
          </div>
          <div className="reasons-visual">
            <div className="rv-card">
              <div className="rv-header">
                <div className="rv-dot" /><div className="rv-dot amber" /><div className="rv-dot green" />
                <span className="rv-url">nwicki.app</span>
              </div>
              <div className="rv-content">
                <div className="rv-sidebar">
                  <div className="rv-logo">N</div>
                  {['Dashboard','Скринер','История','AI'].map((l,i) => (
                    <div key={i} className={`rv-nav ${i===0?'active':''}`}>{l}</div>
                  ))}
                </div>
                <div className="rv-main">
                  <div className="rv-signal">
                    <div className="rv-signal-header">
                      <span className="rv-sym">ETC</span>
                      <span className="rv-badge long">LONG</span>
                    </div>
                    <div className="rv-conf">
                      <div className="rv-conf-bar"><div className="rv-conf-fill" style={{width:'80%'}} /></div>
                      <span className="rv-conf-val" style={{color:'var(--long)'}}>80%</span>
                    </div>
                    <div className="rv-levels">
                      <span style={{color:'var(--accent)'}}>Вход 26.40</span>
                      <span style={{color:'var(--long)'}}>TP1 27.10</span>
                      <span style={{color:'var(--short)'}}>SL 25.90</span>
                    </div>
                  </div>
                  <div className="rv-scan">
                    <span className="scan-dot-sm" />
                    Сканирую рынок каждые 2 минуты...
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── 3 STEPS ── */}
      <section className="steps-section">
        <div className="section-inner">
          <div style={{textAlign:'center'}}><div className="section-label">Как начать</div></div>
          <h2 className="section-heading center">За 3 простых шага</h2>
          <div className="steps-grid">
            <div className="step">
              <div className="step-num">1</div>
              <h3 className="step-title">Открой платформу</h3>
              <p className="step-desc">Зайди на NWICKI — регистрация не нужна. Платформа работает прямо в браузере.</p>
              <button className="step-link" onClick={() => navigate('/app')}>🔗 Открыть NWICKI</button>
              <div className="step-img step-img-1">
                <div className="si-card">
                  <div className="si-logo">N</div>
                  <div>
                    <div style={{fontSize:13,fontWeight:700,color:'var(--text)'}}>NWICKI</div>
                    <div style={{fontSize:10,color:'var(--text-tertiary)'}}>Crypto Scanner</div>
                  </div>
                </div>
              </div>
            </div>
            <div className="step">
              <div className="step-num">2</div>
              <h3 className="step-title">Следи за сигналами</h3>
              <p className="step-desc">Сканер анализирует 32 пары и показывает точки входа с уровнями TP и SL.</p>
              <div className="step-img step-img-2">
                <div className="si-signal">
                  <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:8}}>
                    <span style={{fontFamily:'var(--font-mono)',fontWeight:700,fontSize:16}}>ETC</span>
                    <span style={{background:'var(--long-soft)',color:'var(--long)',fontSize:11,fontWeight:700,padding:'2px 8px',borderRadius:5}}>LONG</span>
                    <span style={{marginLeft:'auto',fontFamily:'var(--font-mono)',fontSize:11,color:'var(--long)'}}>80%</span>
                  </div>
                  <div style={{height:4,background:'var(--surface-hover)',borderRadius:2,marginBottom:8,overflow:'hidden'}}>
                    <div style={{width:'80%',height:'100%',background:'var(--long)',borderRadius:2}} />
                  </div>
                  <div style={{display:'flex',gap:10,fontSize:10}}>
                    <span style={{color:'var(--accent)'}}>Вход 26.40</span>
                    <span style={{color:'var(--long)'}}>TP1 27.10</span>
                    <span style={{color:'var(--short)'}}>SL 25.90</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="step">
              <div className="step-num">3</div>
              <h3 className="step-title">Спроси AI</h3>
              <p className="step-desc">AI ассистент объяснит каждый сигнал — почему вошли, какие риски, что делать дальше.</p>
              <div className="step-img step-img-3">
                <div className="si-chat">
                  <div className="si-msg ai">👋 Сигнал ETC LONG — Score 16/20. RSI перепродан, ADX &gt; 25, тренд восходящий.</div>
                  <div className="si-msg user">Какой стоп-лосс?</div>
                  <div className="si-msg ai">🛡 Стоп на 25.90 — риск 1.9% от входа.</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── AUDIENCE ── */}
      <section className="audience-section">
        <div className="section-inner">
          <div style={{textAlign:'center'}}><div className="section-label">Для кого</div></div>
          <h2 className="section-heading center">Для любого уровня трейдера</h2>
          <div className="audience-grid">
            <div className="audience-card">
              <div className="audience-icon">🚀</div>
              <h3>Новички</h3>
              <p>Начни быстро с готовыми сигналами, гайдами и шаблонами стратегий. Не нужно знать код.</p>
            </div>
            <div className="audience-card">
              <div className="audience-icon">📊</div>
              <h3>Опытные трейдеры</h3>
              <p>Настраивай параметры сканера, используй продвинутый риск-менеджмент и историческую аналитику.</p>
            </div>
            <div className="audience-card">
              <div className="audience-icon">🤖</div>
              <h3>AI-энтузиасты</h3>
              <p>Используй GPT-4o для анализа сигналов, рынка и построения стратегий через натуральный язык.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── TOOLKIT ── */}
      <section className="toolkit-section">
        <div className="section-inner">
          <div className="section-label">Инструменты</div>
          <h2 className="section-heading center">Всё что нужно<br/>для умной торговли</h2>
          <p className="section-sub center" style={{marginTop:12}}>Строй своё финансовое будущее с инструментами которые работают на любом рынке</p>
          <div className="toolkit-grid">
            {TOOLS.map((t, i) => (
              <div key={i} className={`toolkit-card animate-in ${i === 0 ? 'featured' : ''}`}>
                {i === 1 && <span className="tk-badge">AI</span>}
                {i === 4 && <span className="tk-badge new">NEW</span>}
                <div className="tk-icon">{t.icon}</div>
                <h3 className="tk-title">{t.title}</h3>
                <p className="tk-desc">{t.desc}</p>
                <button className="tk-link" onClick={() => navigate('/app')}>Открыть →</button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── BENEFITS ── */}
      <section className="benefits-section">
        <div className="section-inner benefits-inner">
          <div className="benefits-text">
            <div className="section-label">Преимущества</div>
            <h2 className="section-heading">Как NWICKI<br/>помогает тебе</h2>
            <div className="benefits-list">
              {BENEFITS.map((b, i) => (
                <div key={i} className="benefit-item">
                  <span className="benefit-icon">{b.icon}</span>
                  <div>
                    <div className="benefit-title">{b.title}</div>
                    <div className="benefit-desc">{b.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="benefits-visual">
            <div className="bv-card">
              <div style={{fontSize:11,color:'var(--text-tertiary)',marginBottom:8}}>БЭКТЕСТ · 182 дня</div>
              <div style={{fontFamily:'var(--font-mono)',fontSize:32,fontWeight:800,color:'var(--long)'}}>+116.6%</div>
              <div style={{fontSize:12,color:'var(--text-secondary)',margin:'4px 0 12px'}}>ROI за период</div>
              <MiniChart positive width={260} height={80} />
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginTop:12}}>
                {[['PnL','$4,352'],['Винрейт','73%'],['Сделок','22'],['Просадка','-2.1%']].map(([l,v],i)=>(
                  <div key={i} style={{background:'var(--surface-hover)',padding:'8px 12px',borderRadius:8}}>
                    <div style={{fontSize:10,color:'var(--text-tertiary)'}}>{l}</div>
                    <div style={{fontFamily:'var(--font-mono)',fontSize:14,fontWeight:700,color:l==='Просадка'?'var(--short)':'var(--text)'}}>{v}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── SECURITY ── */}
      <section className="security-section">
        <div className="section-inner">
          <h2 className="section-heading center">Безопасно. Надёжно. Прозрачно.</h2>
          <div className="security-grid">
            {SECURITY.map((s, i) => (
              <div key={i} className="security-card">
                <div className="security-icon">{s.icon}</div>
                <h3 className="security-title">{s.title}</h3>
                <p className="security-desc">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── COMMUNITY ── */}
      <section className="community-section">
        <div className="section-inner">
          <div className="community-card">
            <div className="community-text">
              <h2 className="section-heading">Присоединись к сообществу<br/>NWICKI трейдеров!</h2>
              <p className="community-sub">Делись стратегиями, получай экспертные советы и поддержку в своём крипто-пути.</p>
              <div style={{display:'flex',gap:12,flexWrap:'wrap'}}>
                <button className="community-btn tg">✈ Telegram</button>
                <button className="community-btn dc">Discord</button>
              </div>
            </div>
            <div className="community-visual">
              <div className="cv-avatars">
                {['A','B','C','D','E','F'].map((l,i) => (
                  <div key={i} className="cv-avatar" style={{background:`hsl(${i*50+200},70%,50%)`}}>{l}</div>
                ))}
              </div>
              <div style={{fontSize:13,color:'var(--text-secondary)',marginTop:8}}>118,000+ активных трейдеров</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className="faq-section">
        <div className="section-inner">
          <h2 className="section-heading center">Часто задаваемые вопросы</h2>
          <div className="faq-list">
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
          <div className="cta-card">
            <div className="cta-glow" />
            <div className="cta-glow-2" />
            <div className="cta-eyebrow">🚀 Бесплатно · Без регистрации</div>
            <h2 className="cta-title">Начни торговать<br/><span className="gradient-text">умнее прямо сейчас</span></h2>
            <p className="cta-sub">Сканер уже работает. Открой платформу и увидь первый сигнал.</p>
            <button className="btn-hero-primary" style={{fontSize:16,padding:'16px 36px'}} onClick={() => navigate('/app')}>
              Открыть платформу →
            </button>
            <div className="cta-notes">
              <span>✓ Без обязательств</span>
              <span>✓ Без скрытых комиссий</span>
              <span>✓ Без регистрации</span>
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
                <span className="nav-logo-text gradient-text">NWICKI</span>
              </div>
              <p className="footer-desc">AI-платформа для поиска крипто-сигналов на Bybit. Только алгоритм, никаких эмоций.</p>
              <div className="footer-socials">
                {['✈','💬','🐦','📺'].map((s,i) => <button key={i} className="social-btn">{s}</button>)}
              </div>
            </div>
            <div className="footer-cols">
              {[
                { title: 'Платформа', links: ['Dashboard','Скринер','AI Ассистент','История','Стратегии','Тарифы'] },
                { title: 'Инструменты', links: ['Сигнал-сканер','Бэктестинг','Терминал','TradingView'] },
                { title: 'Стратегии', links: ['Скальпинг','Свинг-трейдинг','Следование тренду','Дей-трейдинг'] },
                { title: 'Компания', links: ['О нас','Блог','Партнёрская программа','FAQ','Безопасность'] },
              ].map((col, i) => (
                <div key={i} className="footer-col">
                  <div className="footer-col-title">{col.title}</div>
                  {col.links.map(l => <a key={l} className="footer-link" onClick={() => navigate('/app')}>{l}</a>)}
                </div>
              ))}
            </div>
          </div>
          <div className="footer-bottom">
            <span>© 2026 NWICKI. Не является финансовой рекомендацией.</span>
            <span>Служба поддержки · Живой чат 24/7</span>
            <button className="theme-btn" onClick={() => setDark(d => !d)}>{dark ? '☀ Светлая' : '☾ Тёмная'}</button>
          </div>
        </div>
      </footer>

      <style>{`
        .lp { min-height: 100vh; background: var(--bg); color: var(--text); font-family: var(--font-ui); }

        /* ANNOUNCE */
        .announce-bar { background: linear-gradient(135deg, var(--accent), var(--purple)); padding: 10px 24px; display: flex; align-items: center; justify-content: center; gap: 12px; font-size: 13px; color: #fff; font-weight: 500; flex-wrap: wrap; text-align: center; }
        .announce-dot { width: 8px; height: 8px; border-radius: 50%; background: #fff; opacity: 0.8; flex-shrink: 0; }
        .announce-btn { border: 1px solid rgba(255,255,255,0.5); background: rgba(255,255,255,0.15); color: #fff; font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 6px; white-space: nowrap; }

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
        .hero { padding: 60px 0 0; overflow: hidden; position: relative; }
        .hero-bg-mesh {
          position: absolute; inset: 0; pointer-events: none; z-index: 0;
          background:
            radial-gradient(ellipse 80% 50% at 50% -10%, var(--accent-soft) 0%, transparent 60%),
            radial-gradient(ellipse 40% 30% at 80% 20%, var(--purple-soft) 0%, transparent 50%);
        }
        [data-theme="dark"] .hero-bg-mesh {
          background:
            radial-gradient(ellipse 80% 50% at 50% -10%, rgba(77,140,245,0.12) 0%, transparent 60%),
            radial-gradient(ellipse 40% 30% at 80% 20%, rgba(157,110,248,0.08) 0%, transparent 50%);
        }
        .hero-inner { max-width: 1100px; margin: 0 auto; padding: 0 24px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 20px; position: relative; z-index: 1; }
        .hero-badge { display: inline-flex; align-items: center; gap: 8px; background: var(--surface); border: 1px solid var(--border); border-radius: 50px; padding: 6px 14px; font-size: 12px; font-weight: 600; color: var(--text-secondary); box-shadow: var(--shadow-card); }
        .hb-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; flex-shrink: 0; }
        .hero-ticker { display: flex; align-items: center; gap: 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 50px; padding: 8px 20px; box-shadow: var(--shadow-card); flex-wrap: wrap; justify-content: center; }
        .ht-live { display: flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 800; color: var(--long); text-transform: uppercase; letter-spacing: 0.06em; }
        .ht-item { display: flex; align-items: center; gap: 7px; }
        .ht-sym { font-size: 11px; color: var(--text-tertiary); font-weight: 600; }
        .ht-val { font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: var(--text); }
        .ht-chg { font-family: var(--font-mono); font-size: 12px; font-weight: 600; }
        .ht-chg.pos { color: var(--long); } .ht-chg.neg { color: var(--short); }
        .ht-div { width: 1px; height: 16px; background: var(--border); }
        .scan-dot-sm { width: 7px; height: 7px; border-radius: 50%; background: var(--long); display: inline-block; animation: pulse 2s infinite; }

        .hero-title { font-size: clamp(40px, 6.5vw, 76px); font-weight: 900; line-height: 1.05; letter-spacing: -0.04em; color: var(--text); max-width: 800px; }
        .hero-sub { font-size: 18px; color: var(--text-secondary); line-height: 1.7; max-width: 500px; }
        .hero-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: center; }
        .btn-hero-primary { padding: 14px 28px; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; font-size: 15px; font-weight: 700; border: none; border-radius: 12px; box-shadow: 0 8px 24px rgba(77,140,245,0.4); transition: all 0.2s; display: flex; align-items: center; gap: 8px; }
        .btn-hero-primary:hover { opacity: 0.88; transform: translateY(-2px); box-shadow: 0 12px 32px rgba(77,140,245,0.5); }
        .btn-arrow { transition: transform 0.2s; }
        .btn-hero-primary:hover .btn-arrow { transform: translateX(4px); }
        .btn-hero-secondary { padding: 14px 24px; background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 15px; font-weight: 600; border-radius: 12px; transition: all 0.2s; }
        .btn-hero-secondary:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
        .hero-or { font-size: 13px; color: var(--text-tertiary); }
        .exchange-chips { display: flex; gap: 8px; }
        .exchange-chip { padding: 8px 16px; border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 13px; font-weight: 600; border-radius: 9px; transition: all 0.2s; }
        .exchange-chip:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }

        .hero-social-proof { display: flex; align-items: center; gap: 12px; }
        .hsp-avatars { display: flex; }
        .hsp-av { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 12px; font-weight: 700; border: 2px solid var(--bg); margin-left: -10px; }
        .hsp-av:first-child { margin-left: 0; }
        .hsp-text { font-size: 13px; color: var(--text-secondary); }
        .hsp-count { font-weight: 700; color: var(--text); font-family: var(--font-mono); }

        /* STRATEGY SCROLL */
        .strategy-scroll { width: 100%; overflow-x: auto; display: flex; gap: 14px; padding: 20px 0 10px; scrollbar-width: thin; -webkit-overflow-scrolling: touch; }
        .strategy-card { flex-shrink: 0; width: 220px; background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 16px; box-shadow: var(--shadow-card); transition: all 0.2s; }
        .strategy-card:hover { border-color: var(--accent); transform: translateY(-3px); box-shadow: var(--shadow-lg); }
        .sc-header { margin-bottom: 8px; }
        .sc-name { font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 6px; }
        .sc-tags { display: flex; gap: 6px; align-items: center; }
        .sc-tag { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; font-family: var(--font-mono); }
        .sc-tag.long { background: var(--long-soft); color: var(--long); }
        .sc-tag.short { background: var(--short-soft); color: var(--short); }
        .sc-exchange { font-size: 10px; color: var(--text-tertiary); }
        .sc-roi { font-size: 11px; color: var(--text-tertiary); margin-bottom: 4px; }
        .sc-roi-val { font-family: var(--font-mono); font-size: 18px; font-weight: 800; margin-left: 4px; }
        .sc-chart { margin: 0 -4px 8px; }
        .sc-stats { display: flex; flex-direction: column; gap: 4px; border-top: 1px solid var(--border); padding-top: 8px; margin-bottom: 12px; }
        .sc-stat { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-secondary); }
        .sc-stat span:last-child { font-family: var(--font-mono); font-weight: 600; color: var(--text); }
        .sc-btn { width: 100%; padding: 9px; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; border: none; border-radius: 9px; font-size: 12px; font-weight: 600; transition: opacity 0.2s; }
        .sc-btn:hover { opacity: 0.85; }

        /* STATS */
        .stats-section { padding: 60px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); background: var(--surface); }
        .stats-eyebrow { font-size: 12px; font-weight: 600; color: var(--text-tertiary); text-align: center; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 28px; }
        .stats-title { font-size: 22px; font-weight: 700; color: var(--text); text-align: center; margin-bottom: 32px; }
        .stats-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 20px; }
        .stat-card { text-align: center; padding: 32px 20px; background: var(--bg); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow-card); transition: all 0.25s; position: relative; overflow: hidden; }
        .stat-card::before { content: ''; position: absolute; inset: 0; background: linear-gradient(135deg, var(--accent-soft), var(--purple-soft)); opacity: 0; transition: opacity 0.25s; }
        .stat-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-lg); border-color: var(--accent); }
        .stat-card:hover::before { opacity: 1; }
        .stat-val { font-size: 44px; font-weight: 900; font-family: var(--font-mono); line-height: 1; margin-bottom: 10px; position: relative; }
        .stat-label { font-size: 14px; color: var(--text-secondary); position: relative; }

        /* REASONS */
        .reasons-section { padding: 80px 0; }
        .reasons-inner { display: grid; grid-template-columns: 1fr 1fr; gap: 60px; align-items: center; }
        .section-heading { font-size: clamp(24px, 3.5vw, 40px); font-weight: 800; line-height: 1.2; letter-spacing: -0.02em; color: var(--text); }
        .section-heading.center { text-align: center; }
        .section-sub { font-size: 16px; color: var(--text-secondary); }
        .section-sub.center { text-align: center; }
        .reasons-list { list-style: none; display: flex; flex-direction: column; gap: 16px; margin: 24px 0 32px; }
        .reasons-list li { display: flex; align-items: flex-start; gap: 12px; font-size: 15px; color: var(--text-secondary); line-height: 1.6; }
        .check { width: 22px; height: 22px; border-radius: 50%; background: var(--long); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0; margin-top: 2px; }

        /* PREVIEW */
        .rv-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; overflow: hidden; box-shadow: var(--shadow-lg); }
        .rv-header { background: var(--surface-hover); padding: 10px 16px; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid var(--border); }
        .rv-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--short); }
        .rv-dot.amber { background: var(--amber); }
        .rv-dot.green { background: var(--long); }
        .rv-url { font-size: 11px; color: var(--text-tertiary); font-family: var(--font-mono); margin-left: 4px; }
        .rv-content { display: flex; height: 200px; }
        .rv-sidebar { width: 80px; background: var(--sidebar-bg); border-right: 1px solid var(--border); padding: 12px 8px; display: flex; flex-direction: column; gap: 8px; align-items: center; }
        .rv-logo { width: 28px; height: 28px; border-radius: 7px; background: linear-gradient(135deg, var(--accent), var(--purple)); display: flex; align-items: center; justify-content: center; color: #fff; font-size: 14px; font-weight: 900; margin-bottom: 4px; }
        .rv-nav { font-size: 9px; color: var(--text-tertiary); padding: 4px 6px; border-radius: 5px; text-align: center; width: 100%; }
        .rv-nav.active { background: var(--sidebar-active); color: var(--sidebar-active-text); font-weight: 600; }
        .rv-main { flex: 1; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
        .rv-signal { background: var(--surface-hover); border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
        .rv-signal-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
        .rv-sym { font-family: var(--font-mono); font-size: 16px; font-weight: 700; color: var(--text); }
        .rv-badge { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; }
        .rv-badge.long { background: var(--long-soft); color: var(--long); }
        .rv-conf { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .rv-conf-bar { flex: 1; height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
        .rv-conf-fill { height: 100%; background: var(--long); border-radius: 2px; }
        .rv-conf-val { font-family: var(--font-mono); font-size: 12px; font-weight: 700; flex-shrink: 0; }
        .rv-levels { display: flex; gap: 10px; font-size: 10px; }
        .rv-scan { font-size: 10px; color: var(--text-tertiary); display: flex; align-items: center; gap: 6px; }

        /* STEPS */
        .steps-section { padding: 80px 0; background: var(--surface-hover); }
        .steps-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 32px; margin-top: 48px; }
        .step { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 28px; box-shadow: var(--shadow-card); transition: all 0.25s; }
        .step:hover { transform: translateY(-3px); box-shadow: var(--shadow-lg); border-color: var(--border-strong); }
        .step-num { width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; font-size: 18px; font-weight: 800; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; box-shadow: 0 4px 14px rgba(77,140,245,0.35); }
        .step-title { font-size: 18px; font-weight: 700; color: var(--text); margin-bottom: 10px; }
        .step-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 14px; }
        .step-link { border: none; background: var(--accent-soft); color: var(--accent); font-size: 13px; font-weight: 600; padding: 8px 14px; border-radius: 8px; margin-bottom: 16px; display: inline-block; }
        .step-img { margin-top: 12px; }
        .si-card { background: var(--surface-hover); border: 1px solid var(--border); border-radius: 10px; padding: 14px; display: flex; align-items: center; gap: 12px; }
        .si-logo { width: 36px; height: 36px; border-radius: 9px; background: linear-gradient(135deg, var(--accent), var(--purple)); display: flex; align-items: center; justify-content: center; color: #fff; font-size: 18px; font-weight: 900; }
        .si-signal { background: var(--surface-hover); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
        .si-chat { display: flex; flex-direction: column; gap: 8px; }
        .si-msg { padding: 8px 12px; border-radius: 10px; font-size: 12px; line-height: 1.5; max-width: 90%; }
        .si-msg.ai { background: var(--surface-hover); color: var(--text); border-radius: 4px 10px 10px 10px; }
        .si-msg.user { background: var(--accent); color: #fff; align-self: flex-end; border-radius: 10px 4px 10px 10px; }

        /* AUDIENCE */
        .audience-section { padding: 80px 0; }
        .audience-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 20px; margin-top: 40px; }
        .audience-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 32px 28px; box-shadow: var(--shadow-card); text-align: center; transition: all 0.25s; position: relative; overflow: hidden; }
        .audience-card::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: linear-gradient(135deg, var(--accent), var(--purple)); opacity: 0; transition: opacity 0.25s; }
        .audience-card:hover { border-color: var(--accent); transform: translateY(-4px); box-shadow: 0 20px 40px rgba(77,140,245,0.1); }
        .audience-card:hover::after { opacity: 1; }
        .audience-icon { font-size: 40px; margin-bottom: 16px; }
        .audience-card h3 { font-size: 18px; font-weight: 700; color: var(--text); margin-bottom: 10px; }
        .audience-card p { font-size: 14px; color: var(--text-secondary); line-height: 1.6; }

        /* TOOLKIT */
        .toolkit-section { padding: 80px 0; background: var(--surface-hover); }
        .section-label { display: inline-block; font-size: 11px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.1em; background: var(--accent-soft); padding: 4px 12px; border-radius: 20px; margin-bottom: 14px; }
        .toolkit-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 20px; margin-top: 40px; }
        .toolkit-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 28px; box-shadow: var(--shadow-card); transition: all 0.25s; position: relative; overflow: hidden; }
        .toolkit-card.featured { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-soft), var(--shadow-card); }
        .toolkit-card:hover { border-color: var(--accent); transform: translateY(-4px); box-shadow: 0 20px 40px rgba(77,140,245,0.12); }
        .tk-badge { position: absolute; top: 16px; right: 16px; font-size: 9px; font-weight: 800; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.05em; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; }
        .tk-badge.new { background: linear-gradient(135deg, var(--long), #00a875); }
        .tk-icon { font-size: 28px; margin-bottom: 14px; }
        .tk-title { font-size: 17px; font-weight: 700; color: var(--text); margin-bottom: 10px; }
        .tk-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 16px; }
        .tk-link { border: none; background: transparent; color: var(--accent); font-size: 13px; font-weight: 600; padding: 0; transition: gap 0.2s; }

        /* BENEFITS */
        .benefits-section { padding: 80px 0; }
        .benefits-inner { display: grid; grid-template-columns: 1fr 1fr; gap: 60px; align-items: center; }
        .benefits-list { display: flex; flex-direction: column; gap: 20px; margin-top: 28px; }
        .benefit-item { display: flex; align-items: flex-start; gap: 16px; }
        .benefit-icon { font-size: 24px; flex-shrink: 0; margin-top: 2px; }
        .benefit-title { font-size: 15px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .benefit-desc { font-size: 13px; color: var(--text-secondary); }
        .bv-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 24px; box-shadow: var(--shadow-lg); }

        /* SECURITY */
        .security-section { padding: 80px 0; background: var(--surface-hover); }
        .security-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; margin-top: 40px; }
        .security-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 28px; box-shadow: var(--shadow-card); text-align: center; }
        .security-icon { font-size: 36px; margin-bottom: 16px; }
        .security-title { font-size: 16px; font-weight: 700; color: var(--text); margin-bottom: 10px; }
        .security-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; }

        /* COMMUNITY */
        .community-section { padding: 80px 0; }
        .community-card { background: var(--surface); border: 1px solid var(--border); border-radius: 20px; padding: 48px; box-shadow: var(--shadow-lg); display: flex; justify-content: space-between; align-items: center; gap: 40px; flex-wrap: wrap; }
        .community-sub { font-size: 15px; color: var(--text-secondary); margin: 14px 0 24px; line-height: 1.6; }
        .community-btn { padding: 12px 24px; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; transition: all 0.2s; }
        .community-btn.tg { background: #229ED9; color: #fff; }
        .community-btn.dc { background: #5865F2; color: #fff; }
        .community-btn:hover { opacity: 0.85; }
        .community-visual { text-align: center; }
        .cv-avatars { display: flex; gap: -8px; }
        .cv-avatar { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 14px; font-weight: 700; border: 2px solid var(--surface); margin-left: -8px; }
        .cv-avatar:first-child { margin-left: 0; }

        /* FAQ */
        .faq-section { padding: 80px 0; background: var(--surface-hover); }
        .faq-list { max-width: 760px; margin: 40px auto 0; display: flex; flex-direction: column; gap: 0; }
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
        .social-btn { width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); font-size: 16px; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
        .social-btn:hover { background: var(--surface-hover); transform: translateY(-1px); }
        .footer-cols { display: flex; gap: 40px; flex-wrap: wrap; }
        .footer-col { display: flex; flex-direction: column; gap: 10px; }
        .footer-col-title { font-size: 11px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 4px; }
        .footer-link { font-size: 14px; color: var(--text-tertiary); cursor: pointer; transition: color 0.2s; }
        .footer-link:hover { color: var(--text); }
        .footer-bottom { display: flex; justify-content: space-between; align-items: center; padding-top: 24px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-tertiary); flex-wrap: wrap; gap: 12px; }

        /* SHARED */
        .section-inner { max-width: 1100px; margin: 0 auto; padding: 0 24px; }
        .pos { color: var(--long) !important; }
        .neg { color: var(--short) !important; }

        @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(0,229,168,0.4)} 70%{box-shadow:0 0 0 6px rgba(0,229,168,0)} 100%{box-shadow:0 0 0 0 rgba(0,229,168,0)} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        .animate-in { animation: fadeIn 0.5s ease forwards; }

        /* RESPONSIVE */
        @media (max-width: 1024px) {
          .stats-grid { grid-template-columns: repeat(2,1fr); }
          .toolkit-grid { grid-template-columns: repeat(2,1fr); }
          .steps-grid { grid-template-columns: 1fr; }
          .reasons-inner, .benefits-inner { grid-template-columns: 1fr; }
          .reasons-visual, .benefits-visual { display: none; }
        }
        @media (max-width: 768px) {
          .nav-links { display: none; position: absolute; top: 64px; left: 0; right: 0; background: var(--sidebar-bg); padding: 16px; border-bottom: 1px solid var(--border); z-index: 99; flex-direction: column; }
          .nav-links.open { display: flex; }
          .burger-btn { display: flex; }
          .btn-login { display: none; }
          .audience-grid, .security-grid { grid-template-columns: 1fr; }
          .community-card { flex-direction: column; padding: 32px 24px; }
          .cta-card { padding: 40px 20px; }
          .footer-cols { gap: 24px; }
          .hero-title { font-size: 32px; }
          .toolkit-grid { grid-template-columns: 1fr; }
        }
        @media (max-width: 480px) {
          .stats-grid { grid-template-columns: 1fr 1fr; }
          .hero { padding: 32px 0 0; }
          .exchange-chips { flex-wrap: wrap; justify-content: center; }
        }
      `}</style>
    </div>
  )
}
