import { useState } from 'react'
import { api } from './api'
import { useI18n } from './i18n'
import { trackEvent, Goals } from './analytics'
import {
  TG_BOT,
  TG_RESULTS_CHANNEL,
  TG_SUPPORT,
  TG_SUPPORT_USER,
  SUPPORT_EMAIL,
} from './shared'

export default function Telegram({ user, onNeedAuth, onOpenPricing }) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const linked = !!(user?.telegram_id || user?.telegram_linked)
  const isPremium = !!(user && (user.tier === 'premium' || user.tier === 'vip'))

  async function connectTelegram() {
    if (!user) {
      onNeedAuth?.()
      return
    }
    setBusy(true)
    setError(null)
    try {
      const r = await api.telegramLinkToken()
      trackEvent(Goals.telegramBot, { source: 'app_telegram_tab', action: 'connect' })
      window.open(r.bot_url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setError(err.message || t('tg.err'))
    } finally {
      setBusy(false)
    }
  }

  function openBot() {
    trackEvent(Goals.telegramBot, { source: 'app_telegram_tab', action: 'open_bot' })
    if (user) {
      connectTelegram()
      return
    }
    window.open(TG_BOT, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="tg-page">
      <header className="tg-hero">
        <p className="tg-eyebrow mono">{t('tg.path')}</p>
        <h1 className="tg-title">{t('tg.title')}</h1>
        <p className="tg-sub">{t('tg.subtitle')}</p>
      </header>

      {user && (
        <div className={`tg-status ${linked ? 'ok' : ''}`} role="status">
          <span className="tg-status-dot" aria-hidden />
          <div>
            <div className="tg-status-title">
              {linked ? t('tg.status.linked') : t('tg.status.unlinked')}
            </div>
            <div className="tg-status-hint">
              {linked
                ? (isPremium ? t('tg.status.linkedPremium') : t('tg.status.linkedFree'))
                : t('tg.status.unlinkedHint')}
            </div>
          </div>
        </div>
      )}

      {error && <div className="tg-notice err" role="alert">{error}</div>}

      <div className="tg-actions">
        <button
          type="button"
          className="tg-btn primary"
          onClick={connectTelegram}
          disabled={busy}
        >
          {busy ? '…' : linked ? t('tg.btn.relink') : t('tg.btn.connect')}
        </button>
        <button type="button" className="tg-btn" onClick={openBot} disabled={busy}>
          {t('tg.btn.bot')}
        </button>
      </div>

      <div className="tg-grid">
        <a
          className="tg-card"
          href={TG_RESULTS_CHANNEL}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => trackEvent(Goals.telegramBot, { source: 'app_telegram_tab', action: 'results' })}
        >
          <div className="tg-card-label mono">{t('tg.card.resultsLabel')}</div>
          <div className="tg-card-value">{t('tg.card.resultsValue')}</div>
          <div className="tg-card-hint">{t('tg.card.resultsHint')}</div>
        </a>

        <a
          className="tg-card"
          href={TG_SUPPORT}
          target="_blank"
          rel="noopener noreferrer"
        >
          <div className="tg-card-label mono">{t('tg.card.supportLabel')}</div>
          <div className="tg-card-value">@{TG_SUPPORT_USER}</div>
          <div className="tg-card-hint">{t('tg.card.supportHint')}</div>
        </a>

        <a className="tg-card" href={`mailto:${SUPPORT_EMAIL}`}>
          <div className="tg-card-label mono">{t('tg.card.emailLabel')}</div>
          <div className="tg-card-value mono">{SUPPORT_EMAIL}</div>
          <div className="tg-card-hint">{t('tg.card.emailHint')}</div>
        </a>
      </div>

      {!isPremium && (
        <div className="tg-premium">
          <div className="tg-premium-copy">
            <div className="tg-premium-title">{t('tg.premium.title')}</div>
            <div className="tg-premium-hint">{t('tg.premium.hint')}</div>
          </div>
          <button type="button" className="tg-btn primary" onClick={() => onOpenPricing?.()}>
            {t('tg.premium.cta')}
          </button>
        </div>
      )}

      {isPremium && (
        <div className="tg-premium ok">
          <div className="tg-premium-copy">
            <div className="tg-premium-title">{t('tg.premium.activeTitle')}</div>
            <div className="tg-premium-hint">{t('tg.premium.activeHint')}</div>
          </div>
          <button type="button" className="tg-btn primary" onClick={connectTelegram} disabled={busy}>
            {busy ? '…' : t('tg.premium.inviteCta')}
          </button>
        </div>
      )}

      <ol className="tg-steps">
        <li>{t('tg.step1')}</li>
        <li>{t('tg.step2')}</li>
        <li>{t('tg.step3')}</li>
      </ol>

      <style>{`
        .tg-page {
          max-width: 720px;
          margin: 0 auto;
          padding: 8px 4px 40px;
        }
        .tg-hero { margin-bottom: 22px; }
        .tg-eyebrow {
          font-size: 11px;
          color: var(--text-tertiary);
          letter-spacing: 0.04em;
          margin: 0 0 10px;
        }
        .tg-title {
          font-size: clamp(22px, 3vw, 28px);
          font-weight: 700;
          letter-spacing: -0.03em;
          margin: 0 0 8px;
          color: var(--text);
        }
        .tg-sub {
          margin: 0;
          font-size: 14px;
          line-height: 1.5;
          color: var(--text-secondary);
          max-width: 520px;
        }
        .tg-status {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 14px 16px;
          border-radius: var(--radius-lg);
          background: var(--surface);
          border: 1px solid var(--border);
          margin-bottom: 16px;
        }
        .tg-status.ok { border-color: color-mix(in srgb, var(--long) 35%, var(--border)); }
        .tg-status-dot {
          width: 8px; height: 8px; border-radius: 50%;
          margin-top: 6px; flex-shrink: 0;
          background: var(--text-tertiary);
        }
        .tg-status.ok .tg-status-dot { background: var(--long); box-shadow: 0 0 0 3px color-mix(in srgb, var(--long) 22%, transparent); }
        .tg-status-title { font-size: 14px; font-weight: 650; color: var(--text); }
        .tg-status-hint { font-size: 13px; color: var(--text-secondary); margin-top: 3px; line-height: 1.45; }
        .tg-notice.err {
          padding: 12px 14px;
          border-radius: var(--radius-lg);
          background: color-mix(in srgb, var(--short) 12%, var(--surface));
          border: 1px solid color-mix(in srgb, var(--short) 30%, var(--border));
          color: var(--short);
          font-size: 13px;
          margin-bottom: 14px;
        }
        .tg-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-bottom: 22px;
        }
        .tg-btn {
          border: 1px solid var(--border);
          background: var(--surface);
          color: var(--text);
          border-radius: 980px;
          padding: 11px 18px;
          font-size: 13px;
          font-weight: 650;
          cursor: pointer;
          transition: transform 0.2s, opacity 0.2s, border-color 0.2s;
        }
        .tg-btn:hover:not(:disabled) { transform: translateY(-1px); border-color: color-mix(in srgb, var(--accent) 40%, var(--border)); }
        .tg-btn:disabled { opacity: 0.55; cursor: default; }
        .tg-btn.primary {
          border: none;
          background: var(--text);
          color: var(--bg);
        }
        .tg-btn.primary:hover:not(:disabled) { border: none; filter: brightness(1.05); }
        .tg-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 12px;
          margin-bottom: 20px;
        }
        .tg-card {
          display: block;
          text-decoration: none;
          color: inherit;
          padding: 16px;
          border-radius: var(--radius-lg);
          background: var(--surface);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-card), var(--inset-highlight);
          transition: transform 0.2s, border-color 0.2s;
        }
        .tg-card:hover {
          transform: translateY(-2px);
          border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
        }
        .tg-card-label {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--text-tertiary);
          font-weight: 700;
        }
        .tg-card-value {
          font-size: 15px;
          font-weight: 700;
          margin: 8px 0 6px;
          color: var(--accent);
          word-break: break-word;
        }
        .tg-card-hint {
          font-size: 12px;
          color: var(--text-secondary);
          line-height: 1.4;
        }
        .tg-premium {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          flex-wrap: wrap;
          padding: 16px 18px;
          border-radius: var(--radius-lg);
          background: var(--surface);
          border: 1px solid var(--border);
          margin-bottom: 22px;
        }
        .tg-premium.ok { border-color: color-mix(in srgb, var(--long) 35%, var(--border)); }
        .tg-premium-title { font-size: 14px; font-weight: 650; color: var(--text); }
        .tg-premium-hint { font-size: 13px; color: var(--text-secondary); margin-top: 4px; line-height: 1.45; max-width: 420px; }
        .tg-steps {
          margin: 0;
          padding: 0 0 0 18px;
          color: var(--text-secondary);
          font-size: 13px;
          line-height: 1.7;
        }
        .tg-steps li { margin-bottom: 4px; }
        @media (max-width: 720px) {
          .tg-grid { grid-template-columns: 1fr; }
          .tg-actions .tg-btn { flex: 1; text-align: center; }
          .tg-premium .tg-btn { width: 100%; }
        }
      `}</style>
    </div>
  )
}
