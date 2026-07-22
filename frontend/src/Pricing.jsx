import { useState, useMemo, useEffect } from 'react'
import { TG_RESULTS_CHANNEL, TG_PREMIUM, TG_SUPPORT, TG_SUPPORT_USER, SUPPORT_EMAIL } from './shared'
import { api } from './api'
import { useI18n } from './i18n'
import { trackEvent, Goals } from './analytics'

const PREMIUM_BOT = TG_PREMIUM

export default function Pricing({ user, onNeedAuth }) {
  const { t } = useI18n()
  const [period, setPeriod] = useState('month')
  const [openFaq, setOpenFaq] = useState(null)
  const [tgBusy, setTgBusy] = useState(false)
  const [tgError, setTgError] = useState(null)
  const [payBusy, setPayBusy] = useState(false)
  const [payError, setPayError] = useState(null)
  const [heleketEnabled, setHeleketEnabled] = useState(false)
  const [heleketPlans, setHeleketPlans] = useState(null)
  const [heleketTestMode, setHeleketTestMode] = useState(false)
  const [paidNotice, setPaidNotice] = useState(false)

  useEffect(() => {
    api.paymentsConfig()
      .then((c) => {
        setHeleketEnabled(!!c.heleket)
        setHeleketPlans(c.heleket_plans || null)
        setHeleketTestMode(!!c.heleket_test_mode)
      })
      .catch(() => setHeleketEnabled(false))
    const qs = new URLSearchParams(window.location.search)
    if (qs.get('paid') === '1') setPaidNotice(true)
  }, [])

  const PERIODS = useMemo(() => [
    { key: 'month', label: t('price.period.month'), mult: 1, discount: 0 },
    { key: '3mo', label: t('price.period.3mo'), mult: 3, discount: 0.14 },
    { key: 'lifetime', label: t('price.period.lifetime'), mult: null, discount: 0 },
  ], [t])

  // features: строка — уже работает; { label, soon: true } — честно помечаем «СКОРО»
  const TIERS = useMemo(() => [
    {
      key: 'free', name: t('price.tier.free.name'), price: 0, lifetime: 0,
      features: [t('price.tier.free.f1'), t('price.tier.free.f2'), t('price.tier.free.f3')],
      cta: t('price.tier.free.cta'), accent: 'var(--text-tertiary)',
    },
    {
      key: 'premium', name: t('price.tier.premium.name'), price: 29, lifetime: 299,
      features: [
        t('price.tier.premium.f1'),
        t('price.tier.premium.f2'),
        t('price.tier.premium.f3'),
        t('price.tier.premium.f4'),
        { label: t('price.tier.premium.f5'), soon: true },
      ],
      cta: t('price.tier.premium.cta'), accent: 'var(--accent)', popular: true,
    },
  ], [t])

  const FAQ = useMemo(() => [
    { q: t('price.faq.q1'), a: t('price.faq.a1') },
    { q: t('price.faq.q2'), a: t('price.faq.a2') },
    { q: t('price.faq.q3'), a: t('price.faq.a3') },
    { q: t('price.faq.q4'), a: t('price.faq.a4') },
    { q: t('price.faq.q5'), a: t('price.faq.a5') },
  ], [t])

  const hasPremium = user && (user.tier === 'premium' || user.tier === 'vip')

  async function connectTelegram() {
    setTgBusy(true); setTgError(null)
    try {
      const r = await api.telegramLinkToken()
      window.open(r.bot_url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setTgError(err.message)
    } finally {
      setTgBusy(false)
    }
  }

  function priceFor(tier) {
    if (tier.key === 'free') return { amount: 0, suffix: t('price.forever') }
    if (heleketPlans && tier.key === 'premium') {
      const raw = period === 'lifetime' ? heleketPlans.lifetime : heleketPlans[period] ?? heleketPlans.month
      const amount = Math.round(Number(raw) || 0)
      const suffix = period === 'lifetime'
        ? t('price.lifetimeSuffix')
        : period === 'month'
          ? t('price.perMonth')
          : t('price.perMonths', { n: PERIODS.find(p => p.key === period)?.mult ?? 1 })
      return { amount, suffix }
    }
    if (period === 'lifetime') return { amount: tier.lifetime, suffix: t('price.lifetimeSuffix') }
    const p = PERIODS.find(p => p.key === period)
    const total = Math.round(tier.price * p.mult * (1 - p.discount))
    return { amount: total, suffix: period === 'month' ? t('price.perMonth') : t('price.perMonths', { n: p.mult }) }
  }

  function choose(tier) {
    if (tier === 'free') return
    trackEvent(Goals.pricingClick, { tier, period, source: 'app_pricing' })
    if (heleketEnabled) {
      if (!user) {
        onNeedAuth?.()
        setPayError(t('price.loginRequired'))
        return
      }
      startHeleketPayment()
      return
    }
    trackEvent(Goals.telegramBot, { source: 'app_pricing', tier })
    window.open(PREMIUM_BOT, '_blank', 'noopener,noreferrer')
  }

  async function startHeleketPayment() {
    setPayBusy(true)
    setPayError(null)
    try {
      const r = await api.createHeleketPayment(period)
      if (r.pay_url) window.location.href = r.pay_url
      else setPayError(t('price.payError'))
    } catch (err) {
      setPayError(err.message || t('price.payError'))
    } finally {
      setPayBusy(false)
    }
  }

  return (
    <div className="pr-page animate-in">
      <div className="page-header" style={{ marginBottom: 8 }}>
        <h1 className="page-title">{t('price.title')}</h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          {t('price.subtitle')}
        </p>
      </div>

      <div className="pr-banner">
        {t('price.banner')}
        {' '}
        <a href={TG_RESULTS_CHANNEL} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit', fontWeight: 700 }}>
          {t('price.bannerLink')}
        </a>
      </div>

      {paidNotice && (
        <div className="pr-banner" style={{ borderColor: 'var(--long)', color: 'var(--text)' }}>
          {t('price.paidNotice')}
        </div>
      )}

      {heleketTestMode && (
        <div className="pr-banner" style={{ borderColor: 'var(--long)' }}>
          {t('price.testMode')}
        </div>
      )}

      {payError && <div className="adm-msg-err" style={{ marginBottom: 12 }}>{payError}</div>}

      {user && (
        <div className="pr-tg-connect">
          <div>
            <div className="pr-tg-title">
              {hasPremium ? t('price.tg.premiumTitle') : t('price.tg.connectTitle')}
            </div>
            <div className="pr-tg-hint">
              {hasPremium ? t('price.tg.premiumHint') : t('price.tg.connectHint')}
            </div>
            {tgError && <div className="adm-msg-err" style={{ marginTop: 6 }}>{tgError}</div>}
          </div>
          <button className="pr-tg-btn" onClick={connectTelegram} disabled={tgBusy}>
            {tgBusy ? '...' : t('price.tg.btn')}
          </button>
        </div>
      )}

      <div className="pr-period-switch">
        {PERIODS.map(p => (
          <button key={p.key} className={`pr-period-btn ${period === p.key ? 'active' : ''}`} onClick={() => setPeriod(p.key)}>
            {p.label}{p.discount > 0 && <span className="pr-period-off">-{Math.round(p.discount * 100)}%</span>}
          </button>
        ))}
      </div>

      <div className="pr-grid">
        {TIERS.map(tier => {
          const current = (user?.base_tier ?? user?.tier) === tier.key || (tier.key === 'premium' && (user?.tier === 'premium' || user?.tier === 'vip'))
          const { amount, suffix } = priceFor(tier)
          return (
            <div key={tier.key} className={`pr-card ${tier.popular ? 'popular' : ''}`} style={{ borderColor: current ? tier.accent : undefined }}>
              {tier.popular && <div className="pr-badge">{t('price.popular')}</div>}
              <div className="pr-name" style={{ color: tier.accent }}>{tier.name}</div>
              <div className="pr-price">${amount}<span>{suffix}</span></div>
              <ul className="pr-features">
                {tier.features.map((f, i) => {
                  const label = typeof f === 'string' ? f : f.label
                  const soon = typeof f === 'object' && f.soon
                  return (
                    <li key={i} style={soon ? { opacity: 0.65 } : undefined}>
                      {soon ? '◷' : '✓'} {label}
                      {soon && <span className="pr-soon">{t('price.soon')}</span>}
                    </li>
                  )
                })}
              </ul>
              <button
                className="pr-cta"
                style={{ background: current ? 'var(--surface-2)' : tier.accent, color: current ? 'var(--text-secondary)' : '#fff' }}
                disabled={current || tier.key === 'free' || payBusy}
                onClick={() => choose(tier.key)}
              >
                {payBusy ? '...' : current ? t('price.yourPlan') : (heleketEnabled ? t('price.tier.premium.ctaPay') : tier.cta)}
              </button>
            </div>
          )
        })}
      </div>

      <div className="pr-exchange-note">{t('price.exchangeNotePrefix')} <strong>Bybit</strong> {t('price.exchangeNoteSuffix')}</div>

      <div className="pr-support">
        <div className="pr-support-title">{t('price.supportTitle')}</div>
        <div className="pr-support-body">
          {t('price.supportBody')}{' '}
          <a href={TG_SUPPORT} target="_blank" rel="noopener noreferrer">@{TG_SUPPORT_USER}</a>
          {' · '}
          <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
          {' · '}
          <a href="/support.html">{t('price.supportPage')}</a>
        </div>
      </div>

      <h2 className="pr-faq-title">{t('price.faqTitle')}</h2>
      <div className="pr-faq-list">
        {FAQ.map((f, i) => (
          <div key={i} className={`pr-faq-item ${openFaq === i ? 'open' : ''}`}>
            <button className="pr-faq-q" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
              <span>{f.q}</span>
              <span className="pr-faq-arrow">{openFaq === i ? '▲' : '▼'}</span>
            </button>
            {openFaq === i && <div className="pr-faq-a">{f.a}</div>}
          </div>
        ))}
      </div>

      <style>{`
        .pr-banner { background: var(--accent-soft); border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border)); border-radius: var(--radius-md); padding: 10px 14px; font-size: 12px; color: var(--text-secondary); margin-bottom: 14px; }
        .pr-tg-connect { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 14px 16px; margin-bottom: 18px; box-shadow: var(--shadow-card), var(--inset-highlight); backdrop-filter: blur(12px); }
        .pr-tg-title { font-size: 14px; font-weight: 650; color: var(--text); }
        .pr-tg-hint { font-size: 12px; color: var(--text-secondary); margin-top: 4px; max-width: 480px; }
        .pr-tg-btn { flex-shrink: 0; border: none; border-radius: 980px; padding: 10px 18px; font-size: 13px; font-weight: 650; cursor: pointer; background: var(--accent); color: #fff; box-shadow: 0 4px 12px color-mix(in srgb, var(--accent) 28%, transparent); }
        .pr-tg-btn:disabled { opacity: 0.6; cursor: default; box-shadow: none; }
        .pr-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; max-width: 640px; }
        .pr-card { position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 28px; box-shadow: var(--shadow-card), var(--inset-highlight); backdrop-filter: blur(16px); display: flex; flex-direction: column; transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s; }
        .pr-card:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--accent) 35%, var(--border)); box-shadow: var(--shadow-lg); }
        .pr-card.popular { box-shadow: var(--shadow-lg); border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); }
        .pr-badge { position: absolute; top: -10px; left: 24px; background: var(--accent); color: #fff; font-size: 10px; font-weight: 700; padding: 4px 12px; border-radius: 999px; text-transform: uppercase; letter-spacing: 0.06em; }
        .pr-name { font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; font-family: var(--font-display); }
        .pr-price { font-size: 34px; font-weight: 700; font-family: var(--font-mono); color: var(--text); margin: 8px 0 16px; letter-spacing: -0.03em; }
        .pr-price span { font-size: 14px; color: var(--text-tertiary); font-weight: 400; }
        .pr-features { list-style: none; display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; flex: 1; }
        .pr-features li { font-size: 13px; color: var(--text-secondary); }
        .pr-soon { font-size: 9px; font-weight: 700; letter-spacing: 0.08em; color: var(--text-tertiary); border: 1px solid var(--border); border-radius: 8px; padding: 1px 6px; margin-left: 6px; vertical-align: 1px; }
        .pr-cta { border: none; border-radius: 980px; padding: 12px; font-size: 14px; font-weight: 650; cursor: pointer; }
        .pr-cta:disabled { cursor: default; }

        .pr-period-switch { display: inline-flex; gap: 2px; background: var(--surface-2); border-radius: 980px; padding: 3px; margin-bottom: 18px; }
        .pr-period-btn { border: none; background: transparent; color: var(--text-secondary); font-size: 13px; font-weight: 600; padding: 8px 16px; border-radius: 980px; display: flex; align-items: center; gap: 6px; }
        .pr-period-btn.active { background: var(--surface-solid); color: var(--text); box-shadow: var(--shadow-card); }
        .pr-period-off { font-size: 10px; color: var(--long); font-weight: 700; }

        .pr-exchange-note { text-align: center; font-size: 12px; color: var(--text-tertiary); margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border); }
        .pr-support { max-width: 640px; margin: 20px auto 0; padding: 14px 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
        .pr-support-title { font-size: 14px; font-weight: 650; margin-bottom: 6px; }
        .pr-support-body { font-size: 13px; color: var(--text-secondary); line-height: 1.5; }
        .pr-support-body a { color: var(--accent); }

        .pr-faq-title { font-size: 20px; font-weight: 700; color: var(--text); margin: 40px 0 8px; text-align: center; font-family: var(--font-display); letter-spacing: -0.02em; }
        .pr-faq-list { max-width: 700px; margin: 16px auto 0; }
        .pr-faq-item { border-bottom: 1px solid var(--border); }
        .pr-faq-q { width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 16px 0; background: transparent; border: none; color: var(--text); font-size: 14px; font-weight: 600; text-align: left; cursor: pointer; }
        .pr-faq-q:hover { color: var(--accent); }
        .pr-faq-arrow { font-size: 11px; color: var(--text-tertiary); flex-shrink: 0; }
        .pr-faq-a { font-size: 13px; color: var(--text-secondary); line-height: 1.6; padding-bottom: 16px; }
      `}</style>
    </div>
  )
}
