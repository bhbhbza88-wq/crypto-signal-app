import { useEffect, useRef, useState } from 'react'
import { useI18n } from './i18n'

export default function AccountMenu({ user, dark, onToggleTheme, onLogout, onLogin, onOpenPricing }) {
  const { t, lang, setLang, locales } = useI18n()
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const handle = user?.email?.split('@')[0] || t('top.account')
  const initial = (handle[0] || 'N').toUpperCase()
  const locale = locales.find((l) => l.code === lang) || locales[0]

  return (
    <div className="acct" ref={rootRef}>
      {user ? (
        <button
          type="button"
          className={`acct-trigger ${open ? 'open' : ''}`}
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-haspopup="menu"
        >
          <span className="acct-avatar" aria-hidden>{initial}</span>
          <span className="acct-meta">
            <span className="acct-name">{handle}</span>
            <span className={`acct-tier tier-${user.tier}`}>{user.tier}</span>
          </span>
          <span className="acct-caret" aria-hidden>{open ? '▴' : '▾'}</span>
        </button>
      ) : (
        <div className="acct-guest">
          <button type="button" className="acct-lang-btn" onClick={() => setOpen((o) => !o)} aria-label={t('top.language')}>
            {locale.short}
          </button>
          <button type="button" className="acct-theme-btn" onClick={onToggleTheme} title={t('top.theme')}>
            {dark ? '☀' : '☾'}
          </button>
          <button type="button" className="auth-login-btn" onClick={onLogin}>{t('top.login')}</button>
        </div>
      )}

      {open && (
        <div className="acct-menu" role="menu">
          {user && (
            <>
              <div className="acct-menu-head">
                <span className="acct-avatar lg" aria-hidden>{initial}</span>
                <div>
                  <div className="acct-menu-name">{handle}</div>
                  <div className="acct-menu-email">{user.email}</div>
                </div>
              </div>
              <button type="button" className="acct-item" role="menuitem" onClick={() => { onOpenPricing?.(); setOpen(false) }}>
                <span>{t('top.plan')}</span>
                <span className={`acct-tier-pill tier-${user.tier}`}>{user.tier.toUpperCase()}</span>
              </button>
              <div className="acct-sep" />
            </>
          )}

          <div className="acct-label">{t('top.theme')}</div>
          <button type="button" className="acct-item" role="menuitem" onClick={onToggleTheme}>
            <span>{dark ? t('top.themeLight') : t('top.themeDark')}</span>
            <span className="acct-item-ico">{dark ? '☀' : '☾'}</span>
          </button>

          <div className="acct-label">{t('top.language')}</div>
          <div className="acct-langs" role="group" aria-label={t('top.language')}>
            {locales.map((l) => (
              <button
                key={l.code}
                type="button"
                className={`acct-lang ${lang === l.code ? 'active' : ''}`}
                onClick={() => setLang(l.code)}
              >
                {l.short}
              </button>
            ))}
          </div>

          {user && (
            <>
              <div className="acct-sep" />
              <button
                type="button"
                className="acct-item danger"
                role="menuitem"
                onClick={() => { setOpen(false); onLogout() }}
              >
                <span>{t('top.logout')}</span>
                <span className="acct-item-ico">→</span>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
