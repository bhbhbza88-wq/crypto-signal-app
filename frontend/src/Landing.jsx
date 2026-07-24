import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts'
import { api } from './api'
import {
  useLivePrices, CountUp, useReveal, resultLabel,
  TG_BOT, TG_RESULTS_CHANNEL, TG_PREMIUM, TG_SUPPORT, TG_SUPPORT_USER, SUPPORT_EMAIL,
  polishHistory, polishStats, buildShowcaseCurve,
} from './shared'
import { useI18n } from './i18n'
import { trackEvent, Goals } from './analytics'

const SCAN_COINS = [
  'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'LINK',
  'DOT', 'NEAR', 'APT', 'ARB', 'OP', 'SUI', 'PEPE', 'WIF',
]

function useLiveStats() {
  const [stats, setStats] = useState(null)
  const [history, setHistory] = useState([])
  useEffect(() => {
    async function load() {
      try {
        const [s, h] = await Promise.all([api.getStats(), api.getHistory(500, 30)])
        setStats(s)
        setHistory(h)
      } catch { /* ignore */ }
    }
    load()
    const id = setInterval(load, 60000)
    return () => clearInterval(id)
  }, [])
  const polished = useMemo(() => polishHistory(history), [history])
  const recent = useMemo(() => polished.slice(0, 8), [polished])
  const curve = useMemo(() => buildShowcaseCurve(history), [history])
  const display = useMemo(() => polishStats(stats, polished), [stats, polished])
  return { stats, recent, curve, display }
}

function LiveScanner({ prices, t }) {
  const [idx, setIdx] = useState(0)
  const [log, setLog] = useState([])
  useEffect(() => {
    const id = setInterval(() => {
      setIdx(i => {
        const next = (i + 1) % SCAN_COINS.length
        const coin = SCAN_COINS[next]
        const actions = [t('land.scan.a1'), t('land.scan.a2'), t('land.scan.a3'), t('land.scan.a4'), t('land.scan.a5')]
        const action = actions[next % actions.length]
        setLog(prev => [`${coin}/USDT · ${action}`, ...prev].slice(0, 5))
        return next
      })
    }, 900)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t])

  const active = SCAN_COINS[idx]
  return (
    <div className="scanner" aria-hidden="true">
      <div className="scanner-top">
        <span className="tl-row" aria-hidden="true"><span className="tl r" /><span className="tl a" /><span className="tl g" /></span>
        <span className="live-pill"><span className="live-dot" /> ONLINE</span>
        <span className="scanner-title">{t('land.scan.widgetTitle')}</span>
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
          <div className="scan-now">{t('land.scan.now')} <b>{active}/USDT</b></div>
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
  const { t, lang, setLang, locales } = useI18n()
  const prices = useLivePrices()
  const { recent, curve, display } = useLiveStats()
  const [openFaq, setOpenFaq] = useState(null)

  const FAQ = useMemo(() => [
    { q: t('land.faq.q1'), a: t('land.faq.a1') },
    { q: t('land.faq.q2'), a: t('land.faq.a2') },
    { q: t('land.faq.q3'), a: t('land.faq.a3') },
    { q: t('land.faq.q4'), a: t('land.faq.a4') },
  ], [t])

  const TIERS = useMemo(() => [
    {
      key: 'free', name: t('land.tier.free.name'), price: '0', unit: t('land.tier.free.unit'),
      features: [t('land.tier.free.f1'), t('land.tier.free.f2'), t('land.tier.free.f3')],
    },
    {
      key: 'premium', name: t('land.tier.premium.name'), price: '29', unit: t('land.tier.premium.unit'),
      features: [t('land.tier.premium.f1'), t('land.tier.premium.f2'), t('land.tier.premium.f3')], popular: true,
    },
    {
      key: 'premium3', name: t('land.tier.premium3.name'), price: '75', unit: t('land.tier.premium3.unit'),
      features: [t('land.tier.premium3.f1'), t('land.tier.premium3.f2'), t('land.tier.premium3.f3')],
    },
    {
      key: 'lifetime', name: t('land.tier.lifetime.name'), price: '299', unit: t('land.tier.lifetime.unit'),
      features: [t('land.tier.lifetime.f1'), t('land.tier.lifetime.f2'), t('land.tier.lifetime.f3')],
    },
  ], [t])
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
      <nav className="navbar glass" aria-label={t('land.nav.aria')}>
        <div className="nav-inner">
          <button type="button" className="nav-logo" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <span className="nav-mark">N</span>
            <span className="nav-word">NOWICKI</span>
          </button>
          <div className={`nav-links ${menuOpen ? 'open' : ''}`}>
            <a href="#signals" onClick={e => { e.preventDefault(); go('#signals') }}>{t('land.nav.signals')}</a>
            <a href="#pricing" onClick={e => { e.preventDefault(); go('#pricing') }}>{t('land.nav.pricing')}</a>
            <a href="#about" onClick={e => { e.preventDefault(); go('#about') }}>{t('land.nav.about')}</a>
            <a href="#support" onClick={e => { e.preventDefault(); go('#support') }}>{t('land.nav.support')}</a>
            <a href={TG_RESULTS_CHANNEL} target="_blank" rel="noopener noreferrer">{t('land.nav.results')}</a>
          </div>
          <div className="nav-right">
            <div className="lang-switch" role="group" aria-label="Language">
              {locales.map((l) => (
                <button
                  key={l.code}
                  type="button"
                  className={`lang-btn ${lang === l.code ? 'active' : ''}`}
                  onClick={() => setLang(l.code)}
                >
                  {l.short}
                </button>
              ))}
            </div>
            <button type="button" className="theme-btn" aria-label={t('land.theme.aria')} onClick={() => setDark(d => !d)}>
              {dark ? '☀' : '☾'}
            </button>
            <button type="button" className="btn-ghost" onClick={() => navigate('/app/overview?auth=login')}>{t('top.login')}</button>
            <button type="button" className="btn-solid" onClick={() => navigate('/app/overview?auth=register')}>{t('land.start')}</button>
            <button type="button" className="burger" aria-label={t('land.menu.aria')} aria-expanded={menuOpen} onClick={() => setMenuOpen(o => !o)}>
              <span /><span /><span />
            </button>
          </div>
        </div>
      </nav>

      <section className="hero">
        <div className="hero-plane" aria-hidden="true" />
        <div className="hero-grid">
          <div className="hero-copy animate-in">
            <span className="eyebrow"><span className="live-dot" /> {t('land.hero.eyebrow')}</span>
            <h1>{t('land.hero.titleLine1')}<br />{t('land.hero.titleLine2')}</h1>
            <p>{t('land.hero.desc')}</p>
            <div className="hero-cta">
              <button type="button" className="btn-solid lg" onClick={() => navigate('/app/overview?auth=register')}>
                {t('land.hero.ctaSignals')}
              </button>
              <button type="button" className="btn-ghost lg" onClick={() => go('#signals')}>
                {t('land.hero.ctaTrack')}
              </button>
            </div>
            <div className="hero-stats">
              <div><CountUp className="hs-num" value={display.winrate} suffix="%" /><span>{t('land.hero.statWinrate')}</span></div>
              <div><CountUp className="hs-num" value={display.total} /><span>{t('land.hero.statTrades')}</span></div>
              <div><span className="hs-num pos">+{display.avgPnl}%</span><span>{t('land.hero.statAvgPnl')}</span></div>
            </div>
          </div>
          <div className="hero-stage animate-in">
            <LiveScanner prices={prices} t={t} />
            <div className="equity-mini">
              <div className="eq-meta">
                <span>{t('land.equity.label')}</span>
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
          <h2 className="sec-title reveal">{t('land.signals.title')}</h2>
          <p className="sec-sub reveal">{t('land.signals.sub')}</p>
          <div className="signal-lock-wrap reveal">
            <div className="signal-rows signal-blur">
              {recent.map((row) => {
                const pos = (row.pnl ?? 0) >= 0
                return (
                  <div key={row.id} className="sig-row" aria-hidden="true">
                    <span className="mono">{row.symbol.replace('/USDT', '')}</span>
                    <span className={`dir ${row.signal === 'LONG' ? 'long' : 'short'}`}>{row.signal}</span>
                    <span className="muted">{resultLabel(t, row.result)}</span>
                    <span className={`mono ${pos ? 'pos' : 'neg'}`}>{pos ? '+' : ''}{row.pnl}%</span>
                  </div>
                )
              })}
              {!recent.length && <div className="muted pad">{t('land.signals.empty')}</div>}
            </div>
            {!!recent.length && (
              <div className="signal-lock">
                <span className="signal-lock-icon">🔒</span>
                <span className="signal-lock-text">{t('land.signals.lockText')}</span>
                <button
                  type="button"
                  className="btn-solid"
                  onClick={() => {
                    trackEvent(Goals.telegramBot, { source: 'landing_signals_lock' })
                    window.open(`${TG_BOT}?start=premium`, '_blank', 'noopener,noreferrer')
                  }}
                >
                  {t('land.signals.unlock')}
                </button>
                <button type="button" className="btn-ghost" onClick={() => navigate('/app/overview?auth=register')}>
                  {t('land.signals.registerCta')}
                </button>
              </div>
            )}
          </div>
        </div>
      </section>

      <section id="about" className="section alt">
        <div className="inner about">
          <div className="reveal">
            <h2 className="sec-title">{t('land.about.title')}</h2>
            <ul className="honest-list">
              <li>{t('land.about.b1')}</li>
              <li>{t('land.about.b2')}</li>
              <li>{t('land.about.b3')}</li>
              <li>{t('land.about.b4')}</li>
            </ul>
          </div>
          <div className="honest-cta reveal">
            <a
              className="btn-solid"
              href={TG_BOT}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => trackEvent(Goals.telegramBot, { source: 'landing_about' })}
            >
              {t('land.about.openBot')}
            </a>
            <a className="btn-ghost" href={TG_RESULTS_CHANNEL} target="_blank" rel="noopener noreferrer">{t('land.about.viewResults')}</a>
          </div>
        </div>
      </section>

      <section id="pricing" className="section">
        <div className="inner">
          <h2 className="sec-title reveal">{t('land.pricing.title')}</h2>
          <p className="sec-sub reveal">{t('land.pricing.sub')}</p>
          <div className="price-grid reveal">
            {TIERS.map(tier => (
              <div key={tier.key} className={`price-card ${tier.popular ? 'popular' : ''}`}>
                {tier.popular && <span className="pop">{t('land.pricing.popular')}</span>}
                <div className="price-name">{tier.name}</div>
                <div className="price-amt">${tier.price}<small>{tier.unit}</small></div>
                <ul>{tier.features.map(f => <li key={f}>{f}</li>)}</ul>
                <button
                  type="button"
                  className="btn-solid"
                  onClick={() => {
                    trackEvent(Goals.pricingClick, { tier: tier.key, source: 'landing' })
                    if (tier.key === 'free') navigate('/app/overview')
                    else {
                      trackEvent(Goals.telegramBot, { source: 'landing_pricing', tier: tier.key })
                      window.open(`${TG_BOT}?start=premium`, '_blank', 'noopener,noreferrer')
                    }
                  }}
                >
                  {tier.key === 'free' ? t('land.tier.free.cta') : t('land.tier.premium.cta')}
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section alt">
        <div className="inner">
          <h2 className="sec-title reveal">{t('land.faq.title')}</h2>
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

      <section id="support" className="section">
        <div className="inner">
          <h2 className="sec-title reveal">{t('land.support.title')}</h2>
          <p className="sec-sub reveal">{t('land.support.sub')}</p>
          <div className="support-grid reveal">
            <a className="support-card" href={TG_SUPPORT} target="_blank" rel="noopener noreferrer">
              <div className="support-label">{t('land.support.tgLabel')}</div>
              <div className="support-value">@{TG_SUPPORT_USER}</div>
              <div className="support-hint">{t('land.support.tgHint')}</div>
            </a>
            <a className="support-card" href={`mailto:${SUPPORT_EMAIL}`}>
              <div className="support-label">{t('land.support.emailLabel')}</div>
              <div className="support-value">{SUPPORT_EMAIL}</div>
              <div className="support-hint">{t('land.support.emailHint')}</div>
            </a>
            <a
              className="support-card"
              href={TG_BOT}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => trackEvent(Goals.telegramBot, { source: 'landing_support' })}
            >
              <div className="support-label">{t('land.support.botLabel')}</div>
              <div className="support-value">{t('land.support.botValue')}</div>
              <div className="support-hint">{t('land.support.botHint')}</div>
            </a>
          </div>
          <p className="support-hours reveal">{t('land.support.hours')}</p>
        </div>
      </section>

      <footer className="footer">
        <div className="inner foot">
          <div>
            <div className="nav-word">NOWICKI</div>
            <p className="muted">{t('land.footer.desc')}</p>
            <p className="muted small" style={{ marginTop: 8 }}>
              {t('land.footer.products')}: Free · Premium $29/mo · Premium 3mo $75 · Lifetime $299
            </p>
          </div>
          <div className="foot-links">
            <a href={TG_RESULTS_CHANNEL} target="_blank" rel="noopener noreferrer">{t('land.footer.results')}</a>
            <a href="#pricing" onClick={e => { e.preventDefault(); go('#pricing') }}>{t('land.footer.premium')}</a>
            <a
              href={TG_BOT}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => trackEvent(Goals.telegramBot, { source: 'landing_footer' })}
            >
              {t('land.footer.bot')}
            </a>
            <a href="#support" onClick={e => { e.preventDefault(); go('#support') }}>{t('land.footer.support')}</a>
            <a href="/support.html">{t('land.footer.contacts')}</a>
            <button type="button" onClick={() => navigate('/app/overview')}>{t('land.footer.platform')}</button>
          </div>
          <div className="muted small">
            <div>{t('land.footer.supportLine')}: <a href={TG_SUPPORT} target="_blank" rel="noopener noreferrer">@{TG_SUPPORT_USER}</a>
              {' · '}<a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a></div>
            <div style={{ marginTop: 6 }}>{t('land.footer.disclaimer', { year: new Date().getFullYear() })}</div>
          </div>
        </div>
      </footer>

      <style>{`
        .lp { min-height: 100vh; background: transparent; color: var(--text); font-family: var(--font-ui); overflow-x: hidden; }
        .reveal { opacity: 0; transform: translateY(18px); transition: opacity .6s ease, transform .6s ease; }
        .reveal.in { opacity: 1; transform: none; }
        .animate-in { animation: fadeIn .5s ease forwards; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%{box-shadow:0 0 0 0 color-mix(in srgb, var(--long) 40%, transparent)} 70%{box-shadow:0 0 0 8px transparent} 100%{box-shadow:0 0 0 0 transparent} }
        .pos { color: var(--long) !important; } .neg { color: var(--short) !important; }
        .mono { font-family: var(--font-mono); }
        .muted { color: var(--text-secondary); } .small { font-size: 12px; } .pad { padding: 24px; }

        .navbar { position: sticky; top: 0; z-index: 50; border-bottom: 1px solid var(--border); }
        .nav-inner { max-width: 1120px; margin: 0 auto; padding: 0 20px; height: 56px; display: flex; align-items: center; gap: 16px; }
        .nav-logo { display: flex; align-items: center; gap: 10px; background: none; border: none; color: inherit; padding: 0; }
        .nav-mark {
          width: 30px; height: 30px; border-radius: 9px; background: var(--accent); color: #fff;
          display: grid; place-items: center; font-family: var(--font-display); font-weight: 700;
          box-shadow: 0 4px 12px color-mix(in srgb, var(--accent) 28%, transparent);
        }
        .nav-word { font-family: var(--font-display); font-weight: 700; letter-spacing: -.02em; font-size: 16px; }
        .nav-links { display: flex; gap: 2px; flex: 1; justify-content: center; }
        .nav-links a { padding: 8px 14px; border-radius: 980px; font-size: 13px; color: var(--text-secondary); font-weight: 550; }
        .nav-links a:hover { color: var(--text); background: var(--surface-hover); }
        .nav-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }
        .lang-switch { display: flex; gap: 2px; padding: 2px; border: 1px solid var(--border); border-radius: 980px; background: var(--surface); }
        .lang-btn { border: none; background: transparent; color: var(--text-tertiary); font-size: 11px; font-weight: 700; padding: 6px 9px; border-radius: 980px; cursor: pointer; letter-spacing: 0.04em; }
        .lang-btn.active { background: var(--accent); color: #fff; }
        .theme-btn { width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--border); background: var(--surface); }
        .burger { display: none; flex-direction: column; gap: 5px; background: none; border: none; padding: 4px; }
        .burger span { width: 20px; height: 2px; background: var(--text); border-radius: 2px; }

        .btn-solid {
          background: var(--accent); color: #fff; border: none; border-radius: 980px; padding: 10px 18px;
          font-weight: 650; font-size: 14px; box-shadow: 0 4px 14px color-mix(in srgb, var(--accent) 28%, transparent);
        }
        .btn-solid.lg { padding: 14px 26px; font-size: 15px; }
        .btn-ghost {
          background: color-mix(in srgb, var(--surface) 70%, transparent); border: 1px solid var(--border); color: var(--text);
          border-radius: 980px; padding: 10px 16px; font-weight: 600; font-size: 14px; text-decoration: none;
          display: inline-flex; align-items: center; backdrop-filter: blur(8px);
        }
        .btn-ghost.lg { padding: 14px 22px; font-size: 15px; }
        .btn-ghost:hover { border-color: color-mix(in srgb, var(--accent) 40%, var(--border)); color: var(--accent); }

        .hero { position: relative; padding: 56px 0 64px; overflow: hidden; }
        .hero-plane { position: absolute; inset: 0; background:
          radial-gradient(ellipse 70% 50% at 85% 15%, color-mix(in srgb, var(--accent) 14%, transparent), transparent 60%),
          radial-gradient(ellipse 50% 40% at 10% 85%, color-mix(in srgb, var(--long) 8%, transparent), transparent 55%);
          pointer-events: none; }
        .hero-grid { position: relative; z-index: 1; max-width: 1120px; margin: 0 auto; padding: 0 20px; display: grid; grid-template-columns: 1.05fr .95fr; gap: 40px; align-items: center; }
        .eyebrow { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; color: var(--accent); margin-bottom: 16px; }
        .live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; }
        .hero-copy h1 { font-family: var(--font-display); font-size: clamp(34px, 5vw, 52px); font-weight: 700; letter-spacing: -.04em; line-height: 1.05; margin: 0 0 16px; }
        .hero-copy p { font-size: 17px; color: var(--text-secondary); line-height: 1.55; max-width: 40ch; margin: 0 0 26px; }
        .hero-cta { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 32px; }
        .hero-stats { display: flex; gap: 32px; flex-wrap: wrap; }
        .hero-stats > div { display: flex; flex-direction: column; gap: 4px; }
        .hs-num { font-family: var(--font-mono); font-size: 26px; font-weight: 650; letter-spacing: -.02em; }
        .hero-stats span:last-child { font-size: 12px; color: var(--text-tertiary); }

        .scanner {
          background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden;
          box-shadow: var(--shadow-lg), var(--inset-highlight); backdrop-filter: saturate(160%) blur(20px);
        }
        .scanner-top {
          display: flex; align-items: center; gap: 10px; padding: 12px 14px;
          border-bottom: 1px solid var(--border); background: color-mix(in srgb, var(--surface-hover) 70%, transparent); flex-wrap: wrap;
        }
        .tl-row { display: flex; gap: 6px; margin-right: 4px; }
        .tl { width: 11px; height: 11px; border-radius: 50%; box-shadow: inset 0 0 0 .5px rgba(0,0,0,.15); }
        .tl.r { background: #ff5f57; } .tl.a { background: #febc2e; } .tl.g { background: #28c840; }
        .live-pill { display: inline-flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 700; color: var(--long); letter-spacing: .08em; }
        .scanner-title { font-family: var(--font-ui); font-size: 12px; font-weight: 600; color: var(--text-secondary); }
        .scanner-tickers { margin-left: auto; font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); }
        .scanner-body { display: grid; grid-template-columns: 1fr 1fr; gap: 0; min-height: 220px; }
        .radar { position: relative; height: 220px; background: color-mix(in srgb, var(--bg) 80%, transparent); }
        .ring { position: absolute; inset: 18px; border: 1px solid var(--border-strong); border-radius: 50%; opacity: .55; }
        .ring.r2 { inset: 42px; } .ring.r3 { inset: 66px; }
        .sweep { position: absolute; inset: 18px; border-radius: 50%; background: conic-gradient(from 0deg, transparent 0deg, var(--accent) 50deg, transparent 90deg); opacity: .22; animation: spin 3s linear infinite; }
        .core {
          position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 52px; height: 52px; border-radius: 50%;
          background: var(--accent); color: #fff; display: grid; place-items: center; font-family: var(--font-mono); font-weight: 700; font-size: 13px;
          box-shadow: 0 6px 18px color-mix(in srgb, var(--accent) 35%, transparent);
        }
        .blip { position: absolute; width: 7px; height: 7px; border-radius: 50%; background: var(--text-tertiary); transform: translate(-50%,-50%); }
        .blip.on { background: var(--long); box-shadow: 0 0 0 4px color-mix(in srgb, var(--long) 25%, transparent); width: 9px; height: 9px; }
        .scan-feed { padding: 16px; border-left: 1px solid var(--border); display: flex; flex-direction: column; gap: 10px; }
        .scan-now { font-size: 13px; font-weight: 600; }
        .scan-now b { font-family: var(--font-mono); color: var(--accent); }
        .scan-feed ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
        .scan-feed li { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); }

        .equity-mini {
          margin-top: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md);
          padding: 12px 14px 0; box-shadow: var(--shadow-card), var(--inset-highlight); backdrop-filter: blur(12px);
        }
        .eq-meta { display: flex; justify-content: space-between; align-items: baseline; font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .05em; }
        .eq-meta strong { font-family: var(--font-mono); font-size: 22px; text-transform: none; letter-spacing: -.02em; }
        .eq-chart { height: 88px; }

        .inner { max-width: 1120px; margin: 0 auto; padding: 0 20px; }
        .section { padding: 72px 0; }
        .section.alt { background: color-mix(in srgb, var(--surface) 55%, transparent); border-block: 1px solid var(--border); backdrop-filter: blur(8px); }
        .sec-title { font-family: var(--font-display); font-size: clamp(26px, 3.5vw, 36px); font-weight: 700; letter-spacing: -.03em; margin: 0 0 10px; }
        .sec-sub { color: var(--text-secondary); max-width: 48ch; margin: 0 0 24px; line-height: 1.55; }

        .signal-lock-wrap { position: relative; }
        .signal-rows {
          display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden;
          background: var(--surface); min-height: 180px; box-shadow: var(--shadow-card), var(--inset-highlight); backdrop-filter: blur(16px);
        }
        .signal-rows.signal-blur { filter: blur(5px); pointer-events: none; user-select: none; }
        .sig-row { display: grid; grid-template-columns: 1fr auto 1fr auto; gap: 12px; align-items: center; padding: 14px 16px; border: none; border-bottom: 1px solid var(--border); background: transparent; color: inherit; text-align: left; font-size: 14px; }
        .sig-row:last-child { border-bottom: none; }
        .sig-row:hover { background: var(--surface-hover); }
        .signal-lock {
          position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px;
          text-align: center; padding: 24px; border-radius: var(--radius-lg);
          background: color-mix(in srgb, var(--bg) 55%, transparent); backdrop-filter: blur(8px);
        }
        .signal-lock-icon { font-size: 22px; opacity: .75; }
        .signal-lock-text { font-size: 14px; font-weight: 650; color: var(--text); max-width: 320px; }
        .dir { font-size: 11px; font-weight: 700; font-family: var(--font-mono); padding: 3px 8px; border-radius: 8px; }
        .dir.long { background: var(--long-soft); color: var(--long); }
        .dir.short { background: var(--short-soft); color: var(--short); }

        .about { display: grid; grid-template-columns: 1.4fr .8fr; gap: 40px; align-items: center; }
        .honest-list { margin: 18px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 14px; }
        .honest-list li { padding-left: 18px; position: relative; color: var(--text-secondary); line-height: 1.5; }
        .honest-list li::before { content: ''; position: absolute; left: 0; top: .55em; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
        .honest-cta { display: flex; flex-direction: column; gap: 10px; }

        .price-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 280px)); gap: 16px; justify-content: center; }
        .price-card {
          position: relative; border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 28px;
          background: var(--surface); display: flex; flex-direction: column; gap: 12px;
          box-shadow: var(--shadow-card), var(--inset-highlight); backdrop-filter: blur(16px);
        }
        .price-card.popular { border-color: color-mix(in srgb, var(--accent) 50%, var(--border)); box-shadow: var(--shadow-lg); }
        .pop { position: absolute; top: -10px; left: 20px; background: var(--accent); color: #fff; font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; padding: 4px 12px; border-radius: 999px; }
        .price-name { font-family: var(--font-display); font-weight: 700; font-size: 18px; letter-spacing: -.02em; }
        .price-amt { font-family: var(--font-mono); font-size: 36px; font-weight: 650; letter-spacing: -.03em; }
        .price-amt small { font-size: 14px; color: var(--text-tertiary); font-weight: 500; margin-left: 4px; }
        .price-card ul { list-style: none; padding: 0; margin: 0 0 8px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
        .price-card li { font-size: 13px; color: var(--text-secondary); }

        .faq { max-width: 720px; }
        .faq-item { border-bottom: 1px solid var(--border); }
        .faq-q { width: 100%; display: flex; justify-content: space-between; gap: 16px; padding: 18px 0; background: none; border: none; color: var(--text); font-size: 15px; font-weight: 600; text-align: left; }
        .faq-a { padding-bottom: 16px; color: var(--text-secondary); font-size: 14px; line-height: 1.6; }

        .support-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; max-width: 900px; }
        .support-card {
          display: block; text-decoration: none; color: inherit;
          border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px;
          background: var(--surface); box-shadow: var(--shadow-card), var(--inset-highlight);
          transition: border-color .2s, transform .2s;
        }
        .support-card:hover { border-color: color-mix(in srgb, var(--accent) 40%, var(--border)); transform: translateY(-2px); }
        .support-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--text-tertiary); font-weight: 700; }
        .support-value { font-size: 18px; font-weight: 700; margin: 8px 0 6px; font-family: var(--font-mono); color: var(--accent); }
        .support-hint { font-size: 13px; color: var(--text-secondary); line-height: 1.45; }
        .support-hours { margin-top: 16px; font-size: 13px; color: var(--text-tertiary); }

        .footer { padding: 48px 0 28px; border-top: 1px solid var(--border); }
        .foot { display: grid; gap: 20px; }
        .foot-links { display: flex; gap: 16px; flex-wrap: wrap; }
        .foot-links a, .foot-links button { background: none; border: none; color: var(--text-secondary); font-size: 14px; padding: 0; }
        .foot-links a:hover, .foot-links button:hover { color: var(--accent); }

        @media (max-width: 900px) {
          .hero-grid, .about, .price-grid, .support-grid { grid-template-columns: 1fr; }
          .scanner-body { grid-template-columns: 1fr; }
          .scan-feed { border-left: none; border-top: 1px solid var(--border); }
        }
        @media (max-width: 768px) {
          .nav-links { display: none; position: absolute; top: 56px; left: 0; right: 0; background: var(--glass); border-bottom: 1px solid var(--border); flex-direction: column; padding: 12px; backdrop-filter: blur(20px); }
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
