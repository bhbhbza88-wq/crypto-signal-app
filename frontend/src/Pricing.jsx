import { useState, useMemo, useEffect } from 'react'
import { TG_RESULTS_CHANNEL, TG_PREMIUM, TG_SUPPORT, TG_SUPPORT_USER, SUPPORT_EMAIL } from './shared'
import { api } from './api'
import { useI18n } from './i18n'
import { trackEvent, Goals } from './analytics'

const PREMIUM_BOT = TG_PREMIUM

function CheckIcon({ soon }) {
  if (soon) {
    return (
      <span className="pr-check soon" aria-hidden>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.4" />
          <path d="M7 4.2v3.2M7 9.6h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      </span>
    )
  }
  return (
    <span className="pr-check" aria-hidden>
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M3.2 7.2 5.8 9.8l5-5.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  )
}

export default function Pricing({ user, onNeedAuth, onUserUpdate }) {
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
  const [syncStatus, setSyncStatus] = useState(null) // checking | unlocked | waiting

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

  // After Heleket redirect (?paid=1): poll sync so Premium unlocks even if webhook was delayed/failed
  useEffect(() => {
    if (!paidNotice || !user) return
    if (user.tier === 'premium' || user.tier === 'vip') {
      setSyncStatus('unlocked')
      return
    }
    let cancelled = false
    let attempts = 0
    setSyncStatus('checking')

    async function tick() {
      if (cancelled) return
      attempts += 1
      try {
        const r = await api.syncHeleketPayment()
        if (r?.user) onUserUpdate?.(r.user)
        const tier = r?.user?.tier || r?.tier
        if (tier === 'premium' || tier === 'vip' || r?.granted) {
          if (!cancelled) setSyncStatus('unlocked')
          return
        }
      } catch {
        /* keep polling */
      }
      if (cancelled) return
      if (attempts >= 12) {
        setSyncStatus('waiting')
        return
      }
      setTimeout(tick, attempts < 4 ? 2000 : 4000)
    }
    tick()
    return () => { cancelled = true }
  }, [paidNotice, user?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const PERIODS = useMemo(() => [
    { key: 'month', label: t('price.period.month'), mult: 1, discount: 0 },
    { key: '3mo', label: t('price.period.3mo'), mult: 3, discount: 0.14 },
    { key: 'lifetime', label: t('price.period.lifetime'), mult: null, discount: 0 },
  ], [t])

  const TIERS = useMemo(() => [
    {
      key: 'free', name: t('price.tier.free.name'), price: 0, lifetime: 0,
      features: [t('price.tier.free.f1'), t('price.tier.free.f2'), t('price.tier.free.f3')],
      cta: t('price.tier.free.cta'),
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
      cta: t('price.tier.premium.cta'), popular: true,
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
    <div className="pr-page">
      <header className="pr-hero">
        <p className="pr-eyebrow">{t('price.eyebrow')}</p>
        <h1 className="pr-title">{t('price.title')}</h1>
        <p className="pr-sub">{t('price.subtitle')}</p>
        <a className="pr-results" href={TG_RESULTS_CHANNEL} target="_blank" rel="noopener noreferrer">
          {t('price.bannerLink')}
          <span aria-hidden>→</span>
        </a>
      </header>

      {paidNotice && (
        <div className={`pr-notice ${syncStatus === 'unlocked' ? 'ok' : ''}`} role="status">
          {syncStatus === 'unlocked'
            ? t('price.paidUnlocked')
            : syncStatus === 'checking'
              ? t('price.paidChecking')
              : t('price.paidNotice')}
        </div>
      )}

      {heleketTestMode && (
        <div className="pr-notice warn" role="status">{t('price.testMode')}</div>
      )}

      {payError && <div className="pr-notice err" role="alert">{payError}</div>}

      {hasPremium && (
        <div className="pr-active">
          <div className="pr-active-dot" aria-hidden />
          <div className="pr-active-copy">
            <div className="pr-active-title">{t('price.activeTitle')}</div>
            <div className="pr-active-hint">{t('price.activeHint')}</div>
          </div>
        </div>
      )}

      {user && (
        <div className="pr-tg">
          <div className="pr-tg-copy">
            <div className="pr-tg-title">
              {hasPremium ? t('price.tg.premiumTitle') : t('price.tg.connectTitle')}
            </div>
            <div className="pr-tg-hint">
              {hasPremium ? t('price.tg.premiumHint') : t('price.tg.connectHint')}
            </div>
            {tgError && <div className="pr-notice err" style={{ marginTop: 10, marginBottom: 0 }}>{tgError}</div>}
          </div>
          <button type="button" className="pr-tg-btn" onClick={connectTelegram} disabled={tgBusy}>
            {tgBusy ? '…' : t('price.tg.btn')}
          </button>
        </div>
      )}

      <div className="pr-period" role="tablist" aria-label={t('price.title')}>
        {PERIODS.map(p => (
          <button
            key={p.key}
            type="button"
            role="tab"
            aria-selected={period === p.key}
            className={`pr-period-btn ${period === p.key ? 'active' : ''}`}
            onClick={() => setPeriod(p.key)}
          >
            {p.label}
            {p.discount > 0 && <span className="pr-period-off">−{Math.round(p.discount * 100)}%</span>}
          </button>
        ))}
      </div>

      <div className="pr-grid">
        {TIERS.map((tier, idx) => {
          const current = (user?.base_tier ?? user?.tier) === tier.key
            || (tier.key === 'premium' && (user?.tier === 'premium' || user?.tier === 'vip'))
          const { amount, suffix } = priceFor(tier)
          const ctaLabel = current
            ? t('price.yourPlan')
            : (heleketEnabled && tier.key === 'premium' ? t('price.tier.premium.ctaPay') : tier.cta)

          return (
            <article
              key={tier.key}
              className={[
                'pr-card',
                tier.popular ? 'popular' : '',
                current ? 'current' : '',
                tier.key === 'premium' && hasPremium ? 'active-plan' : '',
              ].filter(Boolean).join(' ')}
              style={{ animationDelay: `${0.08 + idx * 0.08}s` }}
            >
              {tier.popular && !current && (
                <div className="pr-badge">{t('price.popular')}</div>
              )}
              {current && (
                <div className="pr-badge current">{t('price.yourPlan')}</div>
              )}

              <div className="pr-card-top">
                <h2 className="pr-name">{tier.name}</h2>
                <div className="pr-price">
                  <span className="pr-amount">${amount}</span>
                  <span className="pr-suffix">{suffix}</span>
                </div>
              </div>

              <ul className="pr-features">
                {tier.features.map((f, i) => {
                  const label = typeof f === 'string' ? f : f.label
                  const soon = typeof f === 'object' && f.soon
                  return (
                    <li key={i} className={soon ? 'soon' : undefined}>
                      <CheckIcon soon={soon} />
                      <span>
                        {label}
                        {soon && <span className="pr-soon">{t('price.soon')}</span>}
                      </span>
                    </li>
                  )
                })}
              </ul>

              <button
                type="button"
                className={`pr-cta ${tier.popular && !current ? 'primary' : ''} ${current ? 'ghost' : ''}`}
                disabled={current || tier.key === 'free' || payBusy}
                onClick={() => choose(tier.key)}
              >
                {payBusy && tier.key === 'premium' ? '…' : ctaLabel}
              </button>
            </article>
          )
        })}
      </div>

      <p className="pr-pay-hint">{t('price.payHint')}</p>

      <div className="pr-foot">
        <p className="pr-exchange">
          {t('price.exchangeNotePrefix')} <strong>Bybit</strong> {t('price.exchangeNoteSuffix')}
        </p>
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
      </div>

      <section className="pr-faq">
        <h2 className="pr-faq-title">{t('price.faqTitle')}</h2>
        <div className="pr-faq-list">
          {FAQ.map((f, i) => (
            <div key={i} className={`pr-faq-item ${openFaq === i ? 'open' : ''}`}>
              <button
                type="button"
                className="pr-faq-q"
                aria-expanded={openFaq === i}
                onClick={() => setOpenFaq(openFaq === i ? null : i)}
              >
                <span>{f.q}</span>
                <span className="pr-faq-icon" aria-hidden>{openFaq === i ? '−' : '+'}</span>
              </button>
              <div className="pr-faq-a" hidden={openFaq !== i}>{f.a}</div>
            </div>
          ))}
        </div>
      </section>

      <style>{`
        .pr-page {
          max-width: 820px;
          margin: 0 auto;
          padding: 8px 0 48px;
        }

        .pr-hero {
          text-align: center;
          padding: 28px 12px 8px;
          animation: pr-fade-up 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
        }
        .pr-eyebrow {
          font-size: 12px;
          font-weight: 650;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--accent);
          margin-bottom: 12px;
        }
        .pr-title {
          font-family: var(--font-display);
          font-size: clamp(32px, 5vw, 44px);
          font-weight: 700;
          letter-spacing: -0.04em;
          line-height: 1.05;
          color: var(--text);
          margin: 0 0 12px;
        }
        .pr-sub {
          font-size: 16px;
          line-height: 1.45;
          color: var(--text-secondary);
          max-width: 420px;
          margin: 0 auto 18px;
        }
        .pr-results {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 14px;
          font-weight: 600;
          color: var(--accent);
          text-decoration: none;
          transition: opacity 0.2s;
        }
        .pr-results:hover { opacity: 0.75; }

        .pr-notice {
          margin: 20px auto 0;
          max-width: 640px;
          padding: 14px 18px;
          border-radius: var(--radius-md);
          background: var(--surface);
          border: 1px solid var(--border);
          font-size: 13px;
          line-height: 1.45;
          color: var(--text-secondary);
          text-align: center;
          animation: pr-fade-up 0.4s ease both;
        }
        .pr-notice.ok {
          border-color: color-mix(in srgb, var(--long) 40%, var(--border));
          background: color-mix(in srgb, var(--long-soft) 70%, var(--surface));
          color: var(--text);
        }
        .pr-notice.warn {
          border-color: color-mix(in srgb, var(--amber) 35%, var(--border));
          background: color-mix(in srgb, var(--amber-soft) 60%, var(--surface));
        }
        .pr-notice.err {
          border-color: color-mix(in srgb, var(--short) 35%, var(--border));
          background: color-mix(in srgb, var(--short-soft) 55%, var(--surface));
          color: var(--text);
        }

        .pr-active {
          display: flex;
          align-items: flex-start;
          gap: 14px;
          max-width: 640px;
          margin: 28px auto 0;
          padding: 18px 20px;
          border-radius: var(--radius-lg);
          background: color-mix(in srgb, var(--accent-soft) 80%, var(--surface));
          border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
          animation: pr-fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.05s both;
        }
        .pr-active-dot {
          width: 10px; height: 10px; border-radius: 50%;
          background: var(--long);
          margin-top: 5px;
          flex-shrink: 0;
          box-shadow: 0 0 0 4px color-mix(in srgb, var(--long) 22%, transparent);
        }
        .pr-active-title {
          font-family: var(--font-display);
          font-size: 16px;
          font-weight: 700;
          letter-spacing: -0.02em;
          color: var(--text);
        }
        .pr-active-hint {
          font-size: 13px;
          color: var(--text-secondary);
          margin-top: 4px;
          line-height: 1.45;
        }

        .pr-tg {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 20px;
          flex-wrap: wrap;
          max-width: 640px;
          margin: 20px auto 0;
          padding: 18px 20px;
          border-radius: var(--radius-lg);
          background: var(--surface);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-card), var(--inset-highlight);
          backdrop-filter: blur(16px);
          animation: pr-fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.08s both;
        }
        .pr-tg-title {
          font-size: 15px;
          font-weight: 650;
          color: var(--text);
          letter-spacing: -0.01em;
        }
        .pr-tg-hint {
          font-size: 13px;
          color: var(--text-secondary);
          margin-top: 4px;
          max-width: 420px;
          line-height: 1.45;
        }
        .pr-tg-btn {
          flex-shrink: 0;
          border: none;
          border-radius: 980px;
          padding: 11px 20px;
          font-size: 13px;
          font-weight: 650;
          cursor: pointer;
          background: var(--text);
          color: var(--bg);
          transition: transform 0.2s, opacity 0.2s;
        }
        .pr-tg-btn:hover:not(:disabled) { transform: scale(1.02); }
        .pr-tg-btn:disabled { opacity: 0.55; cursor: default; }

        .pr-period {
          display: flex;
          justify-content: center;
          margin: 36px auto 28px;
          padding: 4px;
          gap: 2px;
          width: fit-content;
          max-width: 100%;
          background: var(--surface-2);
          border-radius: 980px;
          animation: pr-fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.1s both;
        }
        .pr-period-btn {
          border: none;
          background: transparent;
          color: var(--text-secondary);
          font-size: 13px;
          font-weight: 600;
          padding: 9px 18px;
          border-radius: 980px;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          cursor: pointer;
          transition: color 0.2s, background 0.2s, box-shadow 0.2s;
          white-space: nowrap;
        }
        .pr-period-btn.active {
          background: var(--surface-solid);
          color: var(--text);
          box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04);
        }
        .pr-period-off {
          font-size: 10px;
          font-weight: 700;
          color: var(--long);
          letter-spacing: 0.02em;
        }

        .pr-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 16px;
          max-width: 680px;
          margin: 0 auto;
        }
        .pr-card {
          position: relative;
          display: flex;
          flex-direction: column;
          padding: 28px 26px 24px;
          border-radius: 22px;
          background: var(--surface-solid);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-card);
          transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.28s, border-color 0.28s;
          animation: pr-fade-up 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
        }
        .pr-card:hover {
          transform: translateY(-3px);
          box-shadow: var(--shadow-lg);
        }
        .pr-card.popular {
          border-color: color-mix(in srgb, var(--accent) 38%, var(--border));
          background:
            linear-gradient(180deg,
              color-mix(in srgb, var(--accent-soft) 55%, var(--surface-solid)) 0%,
              var(--surface-solid) 48%);
        }
        .pr-card.current,
        .pr-card.active-plan {
          border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
        }
        .pr-badge {
          position: absolute;
          top: -11px;
          left: 50%;
          transform: translateX(-50%);
          background: var(--accent);
          color: #fff;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          padding: 4px 12px;
          border-radius: 999px;
          white-space: nowrap;
        }
        .pr-badge.current {
          background: var(--text);
          color: var(--bg);
        }
        .pr-card-top { margin-bottom: 22px; }
        .pr-name {
          font-family: var(--font-display);
          font-size: 15px;
          font-weight: 650;
          letter-spacing: -0.01em;
          color: var(--text-secondary);
          margin: 0 0 10px;
        }
        .pr-price {
          display: flex;
          align-items: baseline;
          gap: 6px;
          flex-wrap: wrap;
        }
        .pr-amount {
          font-family: var(--font-display);
          font-size: clamp(36px, 5vw, 44px);
          font-weight: 700;
          letter-spacing: -0.045em;
          line-height: 1;
          color: var(--text);
        }
        .pr-suffix {
          font-size: 14px;
          font-weight: 500;
          color: var(--text-tertiary);
        }
        .pr-features {
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 12px;
          margin: 0 0 28px;
          flex: 1;
          padding: 0;
        }
        .pr-features li {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          font-size: 14px;
          line-height: 1.4;
          color: var(--text);
        }
        .pr-features li.soon { color: var(--text-tertiary); }
        .pr-check {
          flex-shrink: 0;
          width: 22px; height: 22px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          margin-top: 0;
          background: color-mix(in srgb, var(--accent) 12%, transparent);
          color: var(--accent);
        }
        .pr-check.soon {
          background: var(--surface-2);
          color: var(--text-tertiary);
        }
        .pr-soon {
          display: inline-block;
          margin-left: 8px;
          font-size: 9px;
          font-weight: 700;
          letter-spacing: 0.08em;
          color: var(--text-tertiary);
          border: 1px solid var(--border);
          border-radius: 6px;
          padding: 2px 6px;
          vertical-align: 1px;
        }
        .pr-cta {
          width: 100%;
          border: 1px solid var(--border-strong);
          border-radius: 980px;
          padding: 13px 18px;
          font-size: 14px;
          font-weight: 650;
          cursor: pointer;
          background: transparent;
          color: var(--text);
          transition: transform 0.2s, background 0.2s, border-color 0.2s, opacity 0.2s;
        }
        .pr-cta.primary {
          background: var(--accent);
          border-color: transparent;
          color: #fff;
          box-shadow: 0 6px 18px color-mix(in srgb, var(--accent) 28%, transparent);
        }
        .pr-cta.primary:hover:not(:disabled) {
          transform: scale(1.015);
          background: color-mix(in srgb, var(--accent) 92%, #000);
        }
        .pr-cta.ghost,
        .pr-cta:disabled {
          cursor: default;
          opacity: 0.7;
          background: var(--surface-2);
          border-color: transparent;
          color: var(--text-secondary);
          box-shadow: none;
        }
        .pr-cta:not(.primary):not(.ghost):not(:disabled):hover {
          border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
          color: var(--accent);
        }

        .pr-pay-hint {
          text-align: center;
          font-size: 13px;
          color: var(--text-tertiary);
          margin: 22px auto 0;
          max-width: 420px;
          line-height: 1.45;
        }

        .pr-foot {
          max-width: 640px;
          margin: 40px auto 0;
          text-align: center;
        }
        .pr-exchange {
          font-size: 12px;
          color: var(--text-tertiary);
          margin-bottom: 20px;
        }
        .pr-support {
          padding: 18px 20px;
          border-radius: var(--radius-lg);
          border: 1px solid var(--border);
          background: var(--surface);
        }
        .pr-support-title {
          font-size: 14px;
          font-weight: 650;
          margin-bottom: 6px;
          color: var(--text);
        }
        .pr-support-body {
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.5;
        }
        .pr-support-body a {
          color: var(--accent);
          text-decoration: none;
          font-weight: 600;
        }
        .pr-support-body a:hover { text-decoration: underline; }

        .pr-faq {
          max-width: 640px;
          margin: 48px auto 0;
        }
        .pr-faq-title {
          font-family: var(--font-display);
          font-size: 22px;
          font-weight: 700;
          letter-spacing: -0.03em;
          text-align: center;
          margin: 0 0 8px;
          color: var(--text);
        }
        .pr-faq-list { margin-top: 12px; }
        .pr-faq-item { border-bottom: 1px solid var(--border); }
        .pr-faq-q {
          width: 100%;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 16px;
          padding: 18px 2px;
          background: transparent;
          border: none;
          color: var(--text);
          font-size: 15px;
          font-weight: 600;
          letter-spacing: -0.01em;
          text-align: left;
          cursor: pointer;
          transition: color 0.2s;
        }
        .pr-faq-q:hover { color: var(--accent); }
        .pr-faq-icon {
          width: 22px; height: 22px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          font-size: 16px;
          line-height: 1;
          color: var(--text-tertiary);
          background: var(--surface-2);
          flex-shrink: 0;
        }
        .pr-faq-item.open .pr-faq-icon {
          background: color-mix(in srgb, var(--accent) 12%, transparent);
          color: var(--accent);
        }
        .pr-faq-a {
          font-size: 14px;
          color: var(--text-secondary);
          line-height: 1.55;
          padding: 0 2px 18px;
          animation: pr-fade-up 0.25s ease both;
        }

        @keyframes pr-fade-up {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @media (max-width: 640px) {
          .pr-page { padding: 0 0 32px; }
          .pr-hero { padding: 12px 4px 4px; }
          .pr-sub { font-size: 15px; }
          .pr-period {
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
          }
          .pr-period-btn { padding: 9px 14px; font-size: 12px; }
          .pr-grid {
            grid-template-columns: 1fr;
            gap: 14px;
          }
          .pr-card { padding: 24px 20px 20px; }
          .pr-tg { padding: 16px; }
          .pr-tg-btn { width: 100%; }
        }

        @media (prefers-reduced-motion: reduce) {
          .pr-hero, .pr-notice, .pr-active, .pr-tg, .pr-period, .pr-card, .pr-faq-a {
            animation: none !important;
          }
          .pr-card:hover, .pr-cta.primary:hover:not(:disabled), .pr-tg-btn:hover:not(:disabled) {
            transform: none;
          }
        }
      `}</style>
    </div>
  )
}
