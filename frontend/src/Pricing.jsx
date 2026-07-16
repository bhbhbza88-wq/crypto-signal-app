import { useState } from 'react'
import { TG_BOT } from './shared'

const PERIODS = [
  { key: 'month', label: 'Месяц', mult: 1, discount: 0 },
  { key: '3mo', label: '3 месяца', mult: 3, discount: 0.14 },
  { key: 'lifetime', label: 'Lifetime', mult: null, discount: 0 },
]

// features: строка — уже работает; { label, soon: true } — честно помечаем «СКОРО»
const TIERS = [
  {
    key: 'free', name: 'Free', price: 0, lifetime: 0,
    features: ['Активные сигналы и живая лента', 'Винрейт за всё время — открыт всем', 'AI-ассистент (5 вопросов/день)'],
    cta: 'Бесплатно', accent: 'var(--text-tertiary)',
  },
  {
    key: 'premium', name: 'Premium', price: 29, lifetime: 299,
    features: ['Полная история сделок', 'PnL по дням и разбивка по TP/SL', 'AI-ассистент (50 вопросов/день)', { label: 'Push-алерты', soon: true }],
    cta: 'Оформить в Telegram', accent: 'var(--accent)', popular: true,
  },
]

const FAQ = [
  { q: 'Это реальная торговля или бэктест?', a: 'Каждая сделка в истории — вход и выход по актуальным ценам Bybit. Сигналы формирует наш AI-сканер.' },
  { q: 'Как считается винрейт?', a: 'Доля закрытых сделок с положительным PnL от общего числа закрытых — учитываются TP, стоп и таймаут.' },
  { q: 'Как сканер выбирает монеты?', a: 'Анализируем тренд, силу движения, волатильность и объём. Сигнал появляется только когда условия сходятся и уровни entry/stop/TP согласованы.' },
  { q: 'Как оплатить Premium?', a: 'Нажми «Оформить в Telegram» — бот примет оплату криптой на адрес. После подтверждения откроем Premium на аккаунте.' },
  { q: 'На какой бирже работает платформа?', a: 'Сейчас — Bybit. Поддержка других бирж в планах.' },
]

export default function Pricing({ user }) {
  const [period, setPeriod] = useState('month')
  const [openFaq, setOpenFaq] = useState(null)

  function priceFor(t) {
    if (t.key === 'free') return { amount: 0, suffix: '/навсегда' }
    if (period === 'lifetime') return { amount: t.lifetime, suffix: ' lifetime' }
    const p = PERIODS.find(p => p.key === period)
    const total = Math.round(t.price * p.mult * (1 - p.discount))
    return { amount: total, suffix: period === 'month' ? '/мес' : ` /${p.mult}мес` }
  }

  function choose(tier) {
    if (tier === 'free') return
    window.open(TG_BOT, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="pr-page animate-in">
      <div className="page-header" style={{ marginBottom: 8 }}>
        <h1 className="page-title">Тарифы</h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          Честные сигналы с реальной статистикой. Без обещаний «иксов».
        </p>
      </div>

      <div className="pr-banner">Оплата Premium — в Telegram-боте криптой. После оплаты откроем доступ вручную.</div>

      <div className="pr-period-switch">
        {PERIODS.map(p => (
          <button key={p.key} className={`pr-period-btn ${period === p.key ? 'active' : ''}`} onClick={() => setPeriod(p.key)}>
            {p.label}{p.discount > 0 && <span className="pr-period-off">-{Math.round(p.discount * 100)}%</span>}
          </button>
        ))}
      </div>

      <div className="pr-grid">
        {TIERS.map(t => {
          const current = (user?.base_tier ?? user?.tier) === t.key || (t.key === 'premium' && (user?.tier === 'premium' || user?.tier === 'vip'))
          const { amount, suffix } = priceFor(t)
          return (
            <div key={t.key} className={`pr-card ${t.popular ? 'popular' : ''}`} style={{ borderColor: current ? t.accent : undefined }}>
              {t.popular && <div className="pr-badge">Популярный</div>}
              <div className="pr-name" style={{ color: t.accent }}>{t.name}</div>
              <div className="pr-price">${amount}<span>{suffix}</span></div>
              <ul className="pr-features">
                {t.features.map((f, i) => {
                  const label = typeof f === 'string' ? f : f.label
                  const soon = typeof f === 'object' && f.soon
                  return (
                    <li key={i} style={soon ? { opacity: 0.65 } : undefined}>
                      {soon ? '◷' : '✓'} {label}
                      {soon && <span className="pr-soon">СКОРО</span>}
                    </li>
                  )
                })}
              </ul>
              <button
                className="pr-cta"
                style={{ background: current ? 'var(--surface-2)' : t.accent, color: current ? 'var(--text-secondary)' : '#fff' }}
                disabled={current || t.key === 'free'}
                onClick={() => choose(t.key)}
              >
                {current ? 'Ваш тариф' : t.cta}
              </button>
            </div>
          )
        })}
      </div>

      <div className="pr-exchange-note">Работает на <strong>Bybit</strong> · реальные рыночные данные, бумажное исполнение</div>

      <h2 className="pr-faq-title">Частые вопросы</h2>
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
        .pr-banner { background: var(--accent-soft); border: 1px solid var(--accent); border-radius: var(--radius-md); padding: 10px 14px; font-size: 12px; color: var(--text-secondary); margin-bottom: 14px; }
        .pr-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; max-width: 640px; }
        .pr-card { position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 24px; box-shadow: var(--shadow-card); display: flex; flex-direction: column; transition: border-color 0.2s, transform 0.2s; }
        .pr-card:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--accent) 40%, var(--border)); }
        .pr-card.popular { box-shadow: var(--shadow-lg); border-color: var(--accent); }
        .pr-badge { position: absolute; top: -10px; left: 24px; background: var(--accent); color: #fff; font-size: 10px; font-weight: 700; padding: 3px 10px; border-radius: 6px; text-transform: uppercase; letter-spacing: 0.06em; }
        .pr-name { font-size: 16px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; font-family: var(--font-display); }
        .pr-price { font-size: 34px; font-weight: 800; font-family: var(--font-mono); color: var(--text); margin: 8px 0 16px; }
        .pr-price span { font-size: 14px; color: var(--text-tertiary); font-weight: 400; }
        .pr-features { list-style: none; display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; flex: 1; }
        .pr-features li { font-size: 13px; color: var(--text-secondary); }
        .pr-soon { font-size: 9px; font-weight: 800; letter-spacing: 0.08em; color: var(--text-tertiary); border: 1px solid var(--border); border-radius: 8px; padding: 1px 6px; margin-left: 6px; vertical-align: 1px; }
        .pr-cta { border: none; border-radius: var(--radius-sm); padding: 12px; font-size: 14px; font-weight: 700; cursor: pointer; }
        .pr-cta:disabled { cursor: default; }

        .pr-period-switch { display: inline-flex; gap: 2px; background: var(--surface-2); border-radius: 10px; padding: 3px; margin-bottom: 18px; }
        .pr-period-btn { border: none; background: transparent; color: var(--text-secondary); font-size: 13px; font-weight: 600; padding: 8px 16px; border-radius: 8px; display: flex; align-items: center; gap: 6px; }
        .pr-period-btn.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
        .pr-period-off { font-size: 10px; color: var(--long); font-weight: 700; }

        .pr-exchange-note { text-align: center; font-size: 12px; color: var(--text-tertiary); margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border); }

        .pr-faq-title { font-size: 20px; font-weight: 800; color: var(--text); margin: 40px 0 8px; text-align: center; }
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
