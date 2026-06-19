import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

function useLivePrices() {
  const [prices, setPrices] = useState(null)
  useEffect(() => {
    async function fetch_prices() {
      try {
        const [btcRes, ethRes] = await Promise.all([
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT'),
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=ETHUSDT'),
        ])
        const btc = (await btcRes.json())?.result?.list?.[0]
        const eth = (await ethRes.json())?.result?.list?.[0]
        if (btc && eth) setPrices({
          btc: { price: parseFloat(btc.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }), change: (parseFloat(btc.price24hPcnt)*100).toFixed(2), positive: parseFloat(btc.price24hPcnt) >= 0 },
          eth: { price: parseFloat(eth.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }), change: (parseFloat(eth.price24hPcnt)*100).toFixed(2), positive: parseFloat(eth.price24hPcnt) >= 0 },
        })
      } catch {}
    }
    fetch_prices()
    const id = setInterval(fetch_prices, 30000)
    return () => clearInterval(id)
  }, [])
  return prices
}

const FEATURES = [
  { icon: '◈', title: 'Умный сканер', desc: 'Сканирует 32 пары на Bybit каждые 2 минуты по EMA, RSI, ADX и ATR. Находит лучшую точку входа автоматически.' },
  { icon: '✦', title: 'AI-ассистент', desc: 'GPT-4o знает текущие сигналы и рынок. Спроси "почему вошли в сделку?" или "какие риски?" — получи ответ за секунду.' },
  { icon: '⬡', title: 'Анализ рынка', desc: 'Режим BTC, Fear & Greed, BTC доминация, Altcoin Season Index и тепловая карта всех 32 пар в реальном времени.' },
  { icon: '≡', title: 'История сделок', desc: 'Полная история с PnL по дням, винрейтом и разбивкой по TP1/TP2/TP3/Стоп. Полная прозрачность результатов.' },
  { icon: '◉', title: 'Шкала уверенности', desc: 'Каждый сигнал имеет Score от 0 до 20. Видишь % уверенности сразу — входи только в лучшие сетапы.' },
  { icon: '⚡', title: 'Push-уведомления', desc: 'Браузер уведомит тебя о новом сигнале даже если вкладка свёрнута. Не пропусти точку входа.' },
]

const STATS = [
  { value: '32', label: 'Пар на Bybit' },
  { value: '2 мин', label: 'Интервал сканирования' },
  { value: 'GPT-4o', label: 'AI-ассистент' },
  { value: '24/7', label: 'Работа сканера' },
]

const NAV_LINKS = ['Функции', 'Статистика', 'Тарифы', 'О проекте']

export default function Landing() {
  const navigate = useNavigate()
  const prices = useLivePrices()
  const [menuOpen, setMenuOpen] = useState(false)
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('theme')
    if (saved) return saved === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <div className="landing">

      {/* ── NAVBAR ── */}
      <nav className="navbar glass">
        <div className="nav-inner">
          <div className="nav-logo" onClick={() => window.scrollTo(0,0)}>
            <div className="nav-logo-icon">N</div>
            <span className="nav-logo-text gradient-text">NWICKI</span>
          </div>

          <div className={`nav-links ${menuOpen ? 'open' : ''}`}>
            {NAV_LINKS.map(l => (
              <a key={l} className="nav-link" href={`#${l.toLowerCase()}`} onClick={() => setMenuOpen(false)}>{l}</a>
            ))}
          </div>

          <div className="nav-actions">
            <button className="theme-btn" onClick={() => setDark(d => !d)}>{dark ? '☀' : '☾'}</button>
            <button className="btn-ghost" onClick={() => navigate('/app')}>Войти</button>
            <button className="btn-primary" onClick={() => navigate('/app')}>Начать бесплатно</button>
            <button className="burger-btn" onClick={() => setMenuOpen(o => !o)}>
              <span /><span /><span />
            </button>
          </div>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section className="hero">
        {/* Live price ticker */}
        {prices && (
          <div className="price-ticker animate-in">
            <div className="price-chip">
              <span className="price-sym">₿ BTC</span>
              <span className="price-val">${prices.btc.price}</span>
              <span className={`price-chg ${prices.btc.positive ? 'pos' : 'neg'}`}>
                {prices.btc.positive ? '▲' : '▼'} {Math.abs(prices.btc.change)}%
              </span>
            </div>
            <div className="price-divider" />
            <div className="price-chip">
              <span className="price-sym">Ξ ETH</span>
              <span className="price-val">${prices.eth.price}</span>
              <span className={`price-chg ${prices.eth.positive ? 'pos' : 'neg'}`}>
                {prices.eth.positive ? '▲' : '▼'} {Math.abs(prices.eth.change)}%
              </span>
            </div>
            <div className="price-divider" />
            <div className="price-chip">
              <span className="scan-dot-hero" />
              <span style={{ fontSize: 12, color: 'var(--long)' }}>Сканер активен</span>
            </div>
          </div>
        )}

        <div className="hero-badge animate-in">
          <span>✦</span> AI-платформа для крипто-трейдинга
        </div>

        <h1 className="hero-title animate-in">
          Находи лучшие<br />
          <span className="gradient-text">точки входа</span><br />
          автоматически
        </h1>

        <p className="hero-desc animate-in">
          NWICKI сканирует 32 пары на Bybit каждые 2 минуты,<br />
          анализирует EMA, RSI, ADX и ATR — и находит сигналы<br />
          с максимальным Score. AI объясняет каждую сделку.
        </p>

        <div className="hero-actions animate-in">
          <button className="btn-hero-primary" onClick={() => navigate('/app')}>
            Открыть платформу →
          </button>
          <button className="btn-hero-ghost" onClick={() => navigate('/app')}>
            Смотреть демо
          </button>
        </div>

        <div className="hero-note animate-in">
          🔒 Бесплатно · Без регистрации · Работает прямо сейчас
        </div>

        {/* Dashboard preview */}
        <div className="hero-preview animate-in">
          <div className="preview-bar">
            <div className="preview-dots">
              <span /><span /><span />
            </div>
            <span className="preview-url">terrific-expression-production.up.railway.app</span>
          </div>
          <div className="preview-content">
            <div className="preview-sidebar">
              <div className="preview-logo">N</div>
              <div className="preview-nav-items">
                {['Обзор','Рынок','История','AI Чат'].map((l,i) => (
                  <div key={i} className={`preview-nav-item ${i===0?'active':''}`}>{l}</div>
                ))}
              </div>
            </div>
            <div className="preview-main">
              <div className="preview-cards">
                {['₿ BTC $63,074 ▼1.95%', 'Ξ ETH $1,711 ▼1.73%', '😱 Страх: 15'].map((t,i) => (
                  <div key={i} className="preview-card">{t}</div>
                ))}
              </div>
              <div className="preview-stats">
                {['BTC Доминация 55.9%','Altcoin Season 44%','Объём $838B','Капитализация $2.26T'].map((t,i) => (
                  <div key={i} className="preview-stat">{t}</div>
                ))}
              </div>
              <div className="preview-empty">
                🔍 Сканирую рынок каждые 2 минуты...
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── STATS ── */}
      <section className="stats-section" id="статистика">
        <div className="section-inner">
          <div className="stats-grid">
            {STATS.map((s, i) => (
              <div key={i} className="stat-card animate-in">
                <div className="stat-value gradient-text">{s.value}</div>
                <div className="stat-label">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section className="features-section" id="функции">
        <div className="section-inner">
          <div className="section-tag">Возможности</div>
          <h2 className="section-title-big">Всё что нужно<br /><span className="gradient-text">профессиональному трейдеру</span></h2>
          <p className="section-desc">Мы объединили лучшее из TradingView, 3Commas и ChatGPT в одну платформу</p>

          <div className="features-grid">
            {FEATURES.map((f, i) => (
              <div key={i} className="feature-card animate-in" style={{ animationDelay: `${i * 0.08}s` }}>
                <div className="feature-icon">{f.icon}</div>
                <h3 className="feature-title">{f.title}</h3>
                <p className="feature-desc">{f.desc}</p>
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
            <div className="section-tag">Начни прямо сейчас</div>
            <h2 className="cta-title">Готов найти следующий<br /><span className="gradient-text">идеальный вход?</span></h2>
            <p className="cta-desc">Платформа работает 24/7. Сканер уже анализирует рынок.</p>
            <button className="btn-hero-primary" onClick={() => navigate('/app')}>
              Открыть NWICKI →
            </button>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="footer">
        <div className="section-inner">
          <div className="footer-inner">
            <div className="footer-brand">
              <div className="nav-logo">
                <div className="nav-logo-icon">N</div>
                <span className="nav-logo-text gradient-text">NWICKI</span>
              </div>
              <p className="footer-desc">AI-платформа для поиска крипто-сигналов на Bybit</p>
            </div>
            <div className="footer-links">
              <div className="footer-col">
                <span className="footer-col-title">Платформа</span>
                {['Обзор', 'Рынок', 'История', 'AI Чат'].map(l => (
                  <a key={l} className="footer-link" onClick={() => navigate('/app')}>{l}</a>
                ))}
              </div>
              <div className="footer-col">
                <span className="footer-col-title">Функции</span>
                {['Сканер сигналов', 'Анализ рынка', 'AI-ассистент', 'Push-уведомления'].map(l => (
                  <a key={l} className="footer-link">{l}</a>
                ))}
              </div>
            </div>
          </div>
          <div className="footer-bottom">
            <span>© 2026 NWICKI. Не является финансовой рекомендацией.</span>
            <button className="theme-btn" onClick={() => setDark(d => !d)}>{dark ? '☀ Светлая' : '☾ Тёмная'}</button>
          </div>
        </div>
      </footer>

      <style>{`
        .landing {
          min-height: 100vh;
          background: var(--bg);
          color: var(--text);
          font-family: var(--font-ui);
        }

        /* ── NAVBAR ── */
        .navbar {
          position: sticky; top: 0; z-index: 100;
          border-bottom: 1px solid var(--border);
          transition: all 0.3s;
        }
        .nav-inner {
          max-width: 1200px; margin: 0 auto;
          padding: 0 24px;
          display: flex; align-items: center; justify-content: space-between;
          height: 64px; gap: 24px;
        }
        .nav-logo {
          display: flex; align-items: center; gap: 10px; cursor: pointer; flex-shrink: 0;
        }
        .nav-logo-icon {
          width: 34px; height: 34px; border-radius: 9px;
          background: linear-gradient(135deg, var(--accent), var(--purple));
          display: flex; align-items: center; justify-content: center;
          color: #fff; font-size: 18px; font-weight: 900;
          box-shadow: 0 4px 12px rgba(77,140,245,0.35);
        }
        .nav-logo-text { font-size: 18px; font-weight: 900; letter-spacing: 0.06em; }

        .nav-links {
          display: flex; align-items: center; gap: 4px; flex: 1; justify-content: center;
        }
        .nav-link {
          padding: 7px 14px; border-radius: 8px; font-size: 14px; font-weight: 500;
          color: var(--text-secondary); transition: all 0.2s; cursor: pointer;
        }
        .nav-link:hover { background: var(--surface-hover); color: var(--text); }

        .nav-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .theme-btn {
          border: 1px solid var(--border); background: var(--surface);
          color: var(--text-secondary); width: 34px; height: 34px;
          border-radius: 9px; font-size: 15px; transition: all 0.2s;
        }
        .theme-btn:hover { background: var(--surface-hover); color: var(--text); }
        .btn-ghost {
          padding: 8px 16px; border: 1px solid var(--border);
          background: transparent; color: var(--text); font-size: 14px; font-weight: 500;
          border-radius: 9px; transition: all 0.2s;
        }
        .btn-ghost:hover { background: var(--surface-hover); }
        .btn-primary {
          padding: 8px 18px;
          background: linear-gradient(135deg, var(--accent), var(--purple));
          color: #fff; font-size: 14px; font-weight: 600;
          border: none; border-radius: 9px;
          box-shadow: 0 4px 14px rgba(77,140,245,0.35);
          transition: all 0.2s;
        }
        .btn-primary:hover { opacity: 0.88; transform: translateY(-1px); }
        .burger-btn {
          display: none; border: none; background: transparent;
          flex-direction: column; gap: 5px; padding: 4px;
        }
        .burger-btn span { display: block; width: 22px; height: 2px; background: var(--text); border-radius: 2px; }

        /* ── HERO ── */
        .hero {
          max-width: 900px; margin: 0 auto;
          padding: 80px 24px 60px;
          display: flex; flex-direction: column; align-items: center;
          text-align: center; gap: 24px;
        }
        .price-ticker {
          display: flex; align-items: center; gap: 16px;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 50px; padding: 8px 20px;
          box-shadow: var(--shadow-card);
        }
        .price-chip { display: flex; align-items: center; gap: 8px; }
        .price-sym { font-size: 12px; color: var(--text-tertiary); font-weight: 600; }
        .price-val { font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: var(--text); }
        .price-chg { font-family: var(--font-mono); font-size: 12px; font-weight: 600; }
        .price-chg.pos { color: var(--long); }
        .price-chg.neg { color: var(--short); }
        .price-divider { width: 1px; height: 16px; background: var(--border); }
        .scan-dot-hero {
          width: 7px; height: 7px; border-radius: 50%;
          background: var(--long); animation: pulse 2s infinite; display: inline-block;
        }

        .hero-badge {
          display: flex; align-items: center; gap: 6px;
          background: var(--accent-soft); color: var(--accent);
          border: 1px solid var(--accent-soft);
          padding: 6px 16px; border-radius: 50px;
          font-size: 13px; font-weight: 600;
        }
        .hero-title {
          font-size: clamp(36px, 6vw, 68px);
          font-weight: 900; line-height: 1.1;
          letter-spacing: -0.03em; color: var(--text);
        }
        .hero-desc {
          font-size: 16px; color: var(--text-secondary);
          line-height: 1.7; max-width: 560px;
        }
        .hero-actions { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }
        .btn-hero-primary {
          padding: 14px 28px;
          background: linear-gradient(135deg, var(--accent), var(--purple));
          color: #fff; font-size: 15px; font-weight: 700;
          border: none; border-radius: 12px;
          box-shadow: 0 8px 24px rgba(77,140,245,0.4);
          transition: all 0.2s;
        }
        .btn-hero-primary:hover { opacity: 0.88; transform: translateY(-2px); box-shadow: 0 12px 32px rgba(77,140,245,0.5); }
        .btn-hero-ghost {
          padding: 14px 28px; border: 1px solid var(--border);
          background: var(--surface); color: var(--text);
          font-size: 15px; font-weight: 600; border-radius: 12px;
          transition: all 0.2s;
        }
        .btn-hero-ghost:hover { background: var(--surface-hover); transform: translateY(-1px); }
        .hero-note { font-size: 12px; color: var(--text-tertiary); }

        /* ── PREVIEW ── */
        .hero-preview {
          width: 100%; max-width: 820px;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 16px; overflow: hidden;
          box-shadow: var(--shadow-lg);
          margin-top: 8px;
        }
        .preview-bar {
          background: var(--surface-hover); padding: 10px 16px;
          display: flex; align-items: center; gap: 10px;
          border-bottom: 1px solid var(--border);
        }
        .preview-dots { display: flex; gap: 6px; }
        .preview-dots span { width: 10px; height: 10px; border-radius: 50%; background: var(--border-strong); }
        .preview-dots span:first-child { background: var(--short); }
        .preview-dots span:nth-child(2) { background: var(--amber); }
        .preview-dots span:last-child { background: var(--long); }
        .preview-url { font-size: 11px; color: var(--text-tertiary); font-family: var(--font-mono); }
        .preview-content { display: flex; height: 200px; }
        .preview-sidebar {
          width: 80px; background: var(--sidebar-bg);
          border-right: 1px solid var(--border);
          padding: 12px 8px; display: flex; flex-direction: column; gap: 12px;
          align-items: center;
        }
        .preview-logo {
          width: 28px; height: 28px; border-radius: 7px;
          background: linear-gradient(135deg, var(--accent), var(--purple));
          display: flex; align-items: center; justify-content: center;
          color: #fff; font-size: 14px; font-weight: 900;
        }
        .preview-nav-items { display: flex; flex-direction: column; gap: 4px; width: 100%; }
        .preview-nav-item {
          font-size: 9px; color: var(--text-tertiary); padding: 5px 6px;
          border-radius: 5px; text-align: center;
        }
        .preview-nav-item.active { background: var(--sidebar-active); color: var(--sidebar-active-text); font-weight: 600; }
        .preview-main { flex: 1; padding: 12px; display: flex; flex-direction: column; gap: 8px; overflow: hidden; }
        .preview-cards { display: grid; grid-template-columns: repeat(3,1fr); gap: 6px; }
        .preview-card {
          background: var(--surface-hover); border: 1px solid var(--border);
          border-radius: 8px; padding: 8px 10px; font-size: 10px;
          color: var(--text-secondary); font-family: var(--font-mono);
        }
        .preview-stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 6px; }
        .preview-stat {
          background: var(--surface-hover); border: 1px solid var(--border);
          border-radius: 7px; padding: 6px 8px; font-size: 9px; color: var(--text-tertiary);
        }
        .preview-empty {
          background: var(--surface-hover); border: 1px dashed var(--border-strong);
          border-radius: 8px; padding: 12px; font-size: 11px;
          color: var(--text-tertiary); text-align: center; flex: 1;
          display: flex; align-items: center; justify-content: center;
        }

        /* ── SECTIONS ── */
        .section-inner { max-width: 1100px; margin: 0 auto; padding: 0 24px; }
        .section-tag {
          display: inline-block; background: var(--accent-soft); color: var(--accent);
          border: 1px solid var(--accent-soft); padding: 5px 14px;
          border-radius: 50px; font-size: 12px; font-weight: 600; margin-bottom: 16px;
        }
        .section-title-big {
          font-size: clamp(28px, 4vw, 48px); font-weight: 900;
          line-height: 1.15; letter-spacing: -0.02em; color: var(--text);
          margin-bottom: 12px;
        }
        .section-desc { font-size: 16px; color: var(--text-secondary); margin-bottom: 48px; }

        /* ── STATS ── */
        .stats-section { padding: 60px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
        .stats-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 24px; }
        .stat-card {
          text-align: center; padding: 24px;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 16px; box-shadow: var(--shadow-card);
          transition: all 0.2s;
        }
        .stat-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); }
        .stat-value { font-size: 40px; font-weight: 900; font-family: var(--font-mono); line-height: 1; margin-bottom: 8px; }
        .stat-label { font-size: 14px; color: var(--text-secondary); }

        /* ── FEATURES ── */
        .features-section { padding: 80px 0; }
        .features-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 20px; }
        .feature-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 16px; padding: 28px; box-shadow: var(--shadow-card);
          transition: all 0.2s; animation: fadeIn 0.4s ease forwards; opacity: 0;
        }
        .feature-card:hover { border-color: var(--accent); transform: translateY(-3px); box-shadow: var(--shadow-lg); }
        .feature-icon { font-size: 28px; margin-bottom: 14px; }
        .feature-title { font-size: 17px; font-weight: 700; color: var(--text); margin-bottom: 10px; }
        .feature-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; }

        /* ── CTA ── */
        .cta-section { padding: 80px 0; }
        .cta-card {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 24px; padding: 64px 48px; text-align: center;
          box-shadow: var(--shadow-lg); position: relative; overflow: hidden;
        }
        .cta-glow {
          position: absolute; top: -100px; left: 50%; transform: translateX(-50%);
          width: 400px; height: 400px; border-radius: 50%;
          background: radial-gradient(circle, var(--accent-soft) 0%, transparent 70%);
          pointer-events: none;
        }
        .cta-title {
          font-size: clamp(28px, 4vw, 44px); font-weight: 900;
          line-height: 1.15; letter-spacing: -0.02em;
          color: var(--text); margin-bottom: 14px; position: relative;
        }
        .cta-desc { font-size: 16px; color: var(--text-secondary); margin-bottom: 32px; position: relative; }

        /* ── FOOTER ── */
        .footer { border-top: 1px solid var(--border); padding: 48px 0 24px; }
        .footer-inner { display: flex; justify-content: space-between; gap: 48px; flex-wrap: wrap; margin-bottom: 32px; }
        .footer-brand { max-width: 280px; display: flex; flex-direction: column; gap: 12px; }
        .footer-desc { font-size: 13px; color: var(--text-tertiary); line-height: 1.6; }
        .footer-links { display: flex; gap: 48px; }
        .footer-col { display: flex; flex-direction: column; gap: 10px; }
        .footer-col-title { font-size: 12px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
        .footer-link { font-size: 14px; color: var(--text-tertiary); cursor: pointer; transition: color 0.2s; }
        .footer-link:hover { color: var(--text); }
        .footer-bottom {
          display: flex; justify-content: space-between; align-items: center;
          padding-top: 20px; border-top: 1px solid var(--border);
          font-size: 12px; color: var(--text-tertiary);
        }

        /* ── RESPONSIVE ── */
        @media (max-width: 900px) {
          .features-grid { grid-template-columns: repeat(2,1fr); }
          .stats-grid { grid-template-columns: repeat(2,1fr); }
          .nav-links { display: none; }
          .nav-links.open {
            display: flex; flex-direction: column;
            position: absolute; top: 64px; left: 0; right: 0;
            background: var(--sidebar-bg); padding: 16px;
            border-bottom: 1px solid var(--border); z-index: 99;
          }
          .burger-btn { display: flex; }
          .btn-ghost { display: none; }
          .preview-stats { grid-template-columns: repeat(2,1fr); }
        }
        @media (max-width: 600px) {
          .features-grid { grid-template-columns: 1fr; }
          .stats-grid { grid-template-columns: repeat(2,1fr); }
          .hero { padding: 48px 16px 40px; }
          .price-ticker { flex-wrap: wrap; justify-content: center; }
          .cta-card { padding: 40px 24px; }
          .footer-links { flex-direction: column; gap: 24px; }
          .preview-content { height: 160px; }
        }

        @keyframes pulse {
          0%   { box-shadow: 0 0 0 0 rgba(0,229,168,0.4); }
          70%  { box-shadow: 0 0 0 6px rgba(0,229,168,0); }
          100% { box-shadow: 0 0 0 0 rgba(0,229,168,0); }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  )
}
