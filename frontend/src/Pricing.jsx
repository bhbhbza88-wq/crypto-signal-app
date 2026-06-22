import { useState } from 'react'
import { api } from './api'

const PERIODS = [
  { key: 'month', label: 'Месяц', mult: 1, discount: 0 },
  { key: '3mo', label: '3 месяца', mult: 3, discount: 0.14 },
  { key: 'lifetime', label: 'Lifetime', mult: null, discount: 0 },
]

const TIERS = [
  {
    key: 'free', name: 'Free', price: 0, lifetime: 0, period: 'навсегда',
    features: ['Обзор рынка и фаза', 'Базовый бэктест', 'Просмотр стратегий (с задержкой)'],
    cta: 'Текущий', accent: 'var(--text-tertiary)',
  },
  {
    key: 'premium', name: 'Premium', price: 29, lifetime: 299,
    features: ['Все 3 стратегии в реальном времени', 'Полный дашборд сравнения', 'Дальран-мониторинг', 'Telegram-алерты'],
    cta: 'Выбрать Premium', accent: 'var(--accent)', popular: true,
  },
  {
    key: 'vip', name: 'VIP', price: 79, lifetime: 799,
    features: ['Всё из Premium', 'Закрытый VIP Telegram-канал', 'Приоритетные сигналы', 'Личная поддержка'],
    cta: 'Выбрать VIP', accent: 'var(--purple)',
  },
]

const FAQ = [
  { q: 'Это реальная торговля или бэктест?', a: 'Все стратегии сейчас в режиме бумажной торговли (paper) на живых данных Bybit — реальные цены, виртуальный депозит. Это честный дальран перед тем как доверить им реальные деньги.' },
  { q: 'Почему PF/Sharpe могут меняться со временем?', a: 'Это нормально для любой статистики на ограниченной истории. Мы показываем метрики как есть, без сглаживания, и предупреждаем, если результат пока статистически некрепкий.' },
  { q: 'Что если стратегия уйдёт в минус?', a: 'Risk management встроен в каждую стратегию (стопы, market-neutral хедж, control просадки). Но прошлые результаты не гарантируют будущих — это всегда указано рядом с цифрами.' },
  { q: 'Можно ли отменить подписку?', a: 'Да, в любой момент из настройки аккаунта. Списания пока в тестовом режиме — реальный платёж подключим отдельным шагом.' },
  { q: 'На какой бирже работает платформа?', a: 'Сейчас — Bybit (spot и futures данные). Поддержка других бирж в планах.' },
]

export default function Pricing({ user, onUpgraded, onNeedAuth }) {
  const [busy, setBusy] = useState(null)
  const [msg, setMsg] = useState(null)
  const [period, setPeriod] = useState('month')
  const [openFaq, setOpenFaq] = useState(null)

  function priceFor(t) {
    if (t.key === 'free') return { amount: 0, suffix: '/навсегда' }
    if (period === 'lifetime') return { amount: t.lifetime, suffix: ' lifetime' }
    const p = PERIODS.find(p => p.key === period)
    const total = Math.round(t.price * p.mult * (1 - p.discount))
    return { amount: total, suffix: period === 'month' ? '/мес' : ` /${p.mult}мес` }
  }

  async function choose(tier) {
    if (!user) { onNeedAuth?.(); return }
    if (tier === 'free') return
    setBusy(tier); setMsg(null)
    try {
      const res = await api.upgrade(tier)
      onUpgraded?.(res.tier)
      setMsg(`Тариф изменён на ${res.tier.toUpperCase()} (тестовый режим — реальная оплата позже)`)
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="pr-page animate-in">
      <div className="page-header" style={{ marginBottom: 8 }}>
        <h1 className="page-title">Тарифы</h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          Честные сигналы с реальной статистикой. Без обещаний «иксов».
        </p>
      </div>

      <div className="pr-banner">⚠️ Оплата в тестовом режиме — кнопки меняют тариф мгновенно, реальный платёж подключим позже.</div>

      {msg && <div className="pr-msg">{msg}</div>}

      <div className="pr-period-switch">
        {PERIODS.map(p => (
          <button key={p.key} className={`pr-period-btn ${period === p.key ? 'active' : ''}`} onClick={() => setPeriod(p.key)}>
            {p.label}{p.discount > 0 && <span className="pr-period-off">-{Math.round(p.discount * 100)}%</span>}
          </button>
        ))}
      </div>

      <div className="pr-grid">
        {TIERS.map(t => {
          const current = user?.tier === t.key
          const { amount, suffix } = priceFor(t)
          return (
            <div key={t.key} className={`pr-card ${t.popular ? 'popular' : ''}`} style={{ borderColor: current ? t.accent : undefined }}>
              {t.popular && <div className="pr-badge">Популярный</div>}
              <div className="pr-name" style={{ color: t.accent }}>{t.name}</div>
              <div className="pr-price">${amount}<span>{suffix}</span></div>
              <ul className="pr-features">
                {t.features.map((f, i) => <li key={i}>✓ {f}</li>)}
              </ul>
              <button
                className="pr-cta"
                style={{ background: current ? 'var(--surface-2)' : t.accent, color: current ? 'var(--text-secondary)' : '#fff' }}
                disabled={current || busy === t.key}
                onClick={() => choose(t.key)}
              >
                {current ? 'Ваш тариф' : busy === t.key ? '...' : t.cta}
              </button>
            </div>
          )
        })}
      </div>

      {!user && <p className="pr-hint">Войдите, чтобы выбрать тариф.</p>}

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
        .pr-banner { background: var(--amber-soft); border: 1px solid var(--amber); border-radius: var(--radius-md); padding: 10px 14px; font-size: 12px; color: var(--text-secondary); margin-bottom: 14px; }
        .pr-msg { background: var(--accent-soft); border: 1px solid var(--accent); border-radius: var(--radius-md); padding: 10px 14px; font-size: 13px; color: var(--text); margin-bottom: 14px; }
        .pr-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
        .pr-card { position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 24px; box-shadow: var(--shadow-card); display: flex; flex-direction: column; }
        .pr-card.popular { box-shadow: var(--shadow-lg); }
        .pr-badge { position: absolute; top: -10px; left: 24px; background: var(--accent); color: #fff; font-size: 10px; font-weight: 700; padding: 3px 10px; border-radius: 6px; text-transform: uppercase; }
        .pr-name { font-size: 16px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; }
        .pr-price { font-size: 34px; font-weight: 800; font-family: var(--font-mono); color: var(--text); margin: 8px 0 16px; }
        .pr-price span { font-size: 14px; color: var(--text-tertiary); font-weight: 400; }
        .pr-features { list-style: none; display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; flex: 1; }
        .pr-features li { font-size: 13px; color: var(--text-secondary); }
        .pr-cta { border: none; border-radius: var(--radius-sm); padding: 12px; font-size: 14px; font-weight: 700; cursor: pointer; }
        .pr-cta:disabled { cursor: default; }
        .pr-hint { text-align: center; color: var(--text-tertiary); font-size: 13px; margin-top: 16px; }

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
