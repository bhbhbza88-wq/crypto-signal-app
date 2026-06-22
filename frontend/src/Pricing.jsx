import { useState } from 'react'
import { api } from './api'

const TIERS = [
  {
    key: 'free', name: 'Free', price: '$0', period: 'навсегда',
    features: ['Обзор рынка и фаза', 'Базовый бэктест', 'Просмотр стратегий (с задержкой)'],
    cta: 'Текущий', accent: 'var(--text-tertiary)',
  },
  {
    key: 'premium', name: 'Premium', price: '$29', period: '/мес',
    features: ['Все 3 стратегии в реальном времени', 'Полный дашборд сравнения', 'Дальран-мониторинг', 'Telegram-алерты'],
    cta: 'Выбрать Premium', accent: 'var(--accent)', popular: true,
  },
  {
    key: 'vip', name: 'VIP', price: '$79', period: '/мес',
    features: ['Всё из Premium', 'Закрытый VIP Telegram-канал', 'Приоритетные сигналы', 'Личная поддержка'],
    cta: 'Выбрать VIP', accent: 'var(--purple)',
  },
]

export default function Pricing({ user, onUpgraded, onNeedAuth }) {
  const [busy, setBusy] = useState(null)
  const [msg, setMsg] = useState(null)

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

      <div className="pr-grid">
        {TIERS.map(t => {
          const current = user?.tier === t.key
          return (
            <div key={t.key} className={`pr-card ${t.popular ? 'popular' : ''}`} style={{ borderColor: current ? t.accent : undefined }}>
              {t.popular && <div className="pr-badge">Популярный</div>}
              <div className="pr-name" style={{ color: t.accent }}>{t.name}</div>
              <div className="pr-price">{t.price}<span>{t.period}</span></div>
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
      `}</style>
    </div>
  )
}
