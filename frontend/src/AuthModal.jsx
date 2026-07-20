import { useState, useEffect, useRef, useCallback } from 'react'
import { api, setToken } from './api'
import { useI18n } from './i18n'

const GIS_SRC = 'https://accounts.google.com/gsi/client'

function loadGisScript() {
  if (window.google?.accounts?.id) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${GIS_SRC}"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', reject)
      return
    }
    const s = document.createElement('script')
    s.src = GIS_SRC
    s.async = true
    s.onload = () => resolve()
    s.onerror = reject
    document.head.appendChild(s)
  })
}

export default function AuthModal({ onClose, onAuth, initialMode = 'login' }) {
  const { t, lang } = useI18n()
  const [mode, setMode] = useState(initialMode) // login | register | forgot | check_email
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(false)
  const [googleClientId, setGoogleClientId] = useState(null)
  const [emailEnabled, setEmailEnabled] = useState(false)
  const dialogRef = useRef(null)
  const firstFieldRef = useRef(null)
  const googleBtnRef = useRef(null)

  useEffect(() => {
    api.authConfig().then(c => {
      setGoogleClientId(c.google_client_id || null)
      setEmailEnabled(!!c.email_enabled)
    }).catch(() => {})
  }, [])

  const finishAuth = useCallback((res) => {
    setToken(res.token)
    onAuth(res.user)
    onClose()
  }, [onAuth, onClose])

  const onGoogleCredential = useCallback(async (response) => {
    setError(null); setBusy(true)
    try {
      const res = await api.googleLogin(response.credential)
      finishAuth(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }, [finishAuth])

  useEffect(() => {
    if (!googleClientId || !googleBtnRef.current) return
    let cancelled = false
    loadGisScript().then(() => {
      if (cancelled || !googleBtnRef.current) return
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: onGoogleCredential,
        ux_mode: 'popup',
      })
      googleBtnRef.current.innerHTML = ''
      window.google.accounts.id.renderButton(googleBtnRef.current, {
        theme: 'outline',
        size: 'large',
        width: 312,
        text: 'continue_with',
        shape: 'rectangular',
        locale: lang === 'pl' ? 'pl' : lang === 'en' ? 'en' : 'ru',
      })
    }).catch(() => {})
    return () => { cancelled = true }
  }, [googleClientId, onGoogleCredential, mode, lang])

  useEffect(() => {
    firstFieldRef.current?.focus()
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key !== 'Tab' || !dialogRef.current) return
      const focusable = dialogRef.current.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
      )
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = prev
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  async function submit(e) {
    e.preventDefault()
    setError(null); setInfo(null); setBusy(true)
    try {
      if (mode === 'forgot') {
        const res = await api.forgotPassword(email)
        setInfo(res.message || t('auth.infoAccountExists'))
        return
      }
      if (mode === 'login') {
        const res = await api.login(email, password)
        finishAuth(res)
        return
      }
      if (mode === 'register') {
        const res = await api.register(email, password)
        if (res.needs_verification) {
          setMode('check_email')
          setInfo(res.message)
          return
        }
        finishAuth(res)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function resend() {
    setError(null); setBusy(true)
    try {
      const res = await api.resendVerification(email)
      setInfo(res.message)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const title = {
    login: t('auth.title.login'),
    register: t('auth.title.register'),
    forgot: t('auth.title.forgot'),
    check_email: t('auth.title.check_email'),
  }[mode]

  const sub = {
    login: t('auth.sub.login'),
    register: t('auth.sub.register'),
    forgot: emailEnabled ? t('auth.sub.forgotEnabled') : t('auth.sub.forgotDisabled'),
    check_email: t('auth.sub.checkEmail', { email }),
  }[mode]

  return (
    <div className="am-overlay" onClick={onClose} role="presentation">
      <div
        className="am-modal"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="am-title"
        onClick={e => e.stopPropagation()}
      >
        <button type="button" className="am-close" onClick={onClose} aria-label={t('auth.close')}>✕</button>
        <h2 id="am-title" className="am-title">{title}</h2>
        <p className="am-sub">{sub}</p>

        {mode !== 'check_email' && googleClientId && (
          <>
            <div ref={googleBtnRef} className="am-google" />
            <div className="am-or"><span>{t('auth.or')}</span></div>
          </>
        )}

        {mode === 'check_email' ? (
          <div className="am-check">
            {info && <div className="am-info" role="status">{info}</div>}
            {error && <div className="am-error" role="alert">{error}</div>}
            <button type="button" className="am-submit" onClick={resend} disabled={busy}>
              {busy ? '...' : t('auth.resend')}
            </button>
            <button type="button" className="am-linkish" onClick={() => { setMode('login'); setError(null) }}>
              {t('auth.backToLogin')}
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="am-form">
            <label className="am-label" htmlFor="am-email">{t('auth.email')}</label>
            <input
              id="am-email"
              ref={firstFieldRef}
              className="am-input"
              type="email"
              autoComplete="email"
              placeholder="you@gmail.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
            {mode !== 'forgot' && (
              <>
                <label className="am-label" htmlFor="am-password">{t('auth.password')}</label>
                <input
                  id="am-password"
                  className="am-input"
                  type="password"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  placeholder={t('auth.passwordPlaceholder')}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  minLength={8}
                />
              </>
            )}
            {error && <div className="am-error" role="alert">{error}</div>}
            {info && <div className="am-info" role="status">{info}</div>}
            <button className="am-submit" type="submit" disabled={busy || (mode === 'forgot' && !emailEnabled)}>
              {busy ? '...' : (
                mode === 'login' ? t('auth.submit.login')
                  : mode === 'register' ? t('auth.submit.register')
                    : t('auth.submit.forgot')
              )}
            </button>
          </form>
        )}

        <div className="am-switch">
          {mode === 'login' && (
            <>
              <button type="button" onClick={() => { setMode('forgot'); setError(null); setInfo(null) }}>{t('auth.forgotLink')}</button>
              <span className="am-dot">·</span>
              {t('auth.noAccount')} <button type="button" onClick={() => { setMode('register'); setError(null); setInfo(null) }}>{t('auth.registerLink')}</button>
            </>
          )}
          {mode === 'register' && (
            <>{t('auth.haveAccount')} <button type="button" onClick={() => { setMode('login'); setError(null); setInfo(null) }}>{t('auth.loginLink')}</button></>
          )}
          {mode === 'forgot' && (
            <>{t('auth.rememberedLink')} <button type="button" onClick={() => { setMode('login'); setError(null); setInfo(null) }}>{t('auth.loginLink')}</button></>
          )}
        </div>

        <style>{`
          .am-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45); backdrop-filter: blur(10px); display: flex; align-items: center; justify-content: center; z-index: 1000; }
          .am-modal {
            position: relative; background: var(--glass); border: 1px solid var(--glass-border);
            border-radius: var(--radius-lg); padding: 28px; width: 380px; max-width: 92vw;
            box-shadow: var(--shadow-lg), var(--inset-highlight);
            backdrop-filter: saturate(180%) blur(28px);
            -webkit-backdrop-filter: saturate(180%) blur(28px);
          }
          .am-close { position: absolute; top: 14px; right: 14px; background: var(--surface-2); border: none; color: var(--text-tertiary); font-size: 14px; cursor: pointer; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; }
          .am-title { font-family: var(--font-display); font-size: 22px; font-weight: 700; color: var(--text); letter-spacing: -0.02em; }
          .am-sub { font-size: 13px; color: var(--text-secondary); margin: 4px 0 18px; }
          .am-google { display: flex; justify-content: center; min-height: 40px; margin-bottom: 4px; }
          .am-or { display: flex; align-items: center; gap: 10px; color: var(--text-tertiary); font-size: 12px; margin: 14px 0; }
          .am-or::before, .am-or::after { content: ''; flex: 1; height: 1px; background: var(--border); }
          .am-label { font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
          .am-form, .am-check { display: flex; flex-direction: column; gap: 8px; }
          .am-input { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 11px 14px; font-size: 14px; color: var(--text); font-family: var(--font-ui); }
          .am-input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent); }
          .am-error { font-size: 12px; color: var(--short); }
          .am-info { font-size: 12px; color: var(--accent); }
          .am-submit { background: var(--accent); color: #fff; border: none; border-radius: 980px; padding: 12px; font-size: 14px; font-weight: 650; cursor: pointer; margin-top: 4px; box-shadow: 0 4px 14px color-mix(in srgb, var(--accent) 28%, transparent); }
          .am-submit:disabled { opacity: 0.6; box-shadow: none; }
          .am-linkish { background: none; border: none; color: var(--accent); cursor: pointer; font-size: 13px; font-weight: 600; margin-top: 8px; }
          .am-switch { text-align: center; font-size: 13px; color: var(--text-secondary); margin-top: 16px; }
          .am-switch button { background: none; border: none; color: var(--accent); cursor: pointer; font-weight: 600; }
          .am-dot { margin: 0 6px; color: var(--text-tertiary); }
        `}</style>
      </div>
    </div>
  )
}
