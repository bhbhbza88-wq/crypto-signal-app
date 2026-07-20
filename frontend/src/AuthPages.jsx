import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, setToken } from './api'
import { useI18n } from './i18n'

export function VerifyEmailPage() {
  const { t } = useI18n()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState('loading') // loading | ok | err
  const [message, setMessage] = useState('')

  useEffect(() => {
    const token = params.get('token')
    if (!token) {
      setStatus('err')
      setMessage(t('auth.verify.noToken'))
      return
    }
    api.verifyEmail(token)
      .then((res) => {
        setToken(res.token)
        setStatus('ok')
        setMessage(t('auth.verify.success'))
        setTimeout(() => navigate('/app/overview', { replace: true }), 1200)
      })
      .catch((err) => {
        setStatus('err')
        setMessage(err.message || t('auth.verify.failed'))
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, navigate])

  return (
    <AuthShell title={t('auth.verify.title')}>
      {status === 'loading' && <p className="as-muted">{t('auth.verify.checking')}</p>}
      {status === 'ok' && <p className="as-ok">{message}</p>}
      {status === 'err' && (
        <>
          <p className="as-err">{message}</p>
          <Link to="/" className="as-link">{t('auth.verify.home')}</Link>
        </>
      )}
    </AuthShell>
  )
}

export function ResetPasswordPage() {
  const { t } = useI18n()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token') || ''
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError(null)
    if (password.length < 8) {
      setError(t('auth.reset.minLength'))
      return
    }
    if (password !== password2) {
      setError(t('auth.reset.mismatch'))
      return
    }
    if (!token) {
      setError(t('auth.reset.noToken'))
      return
    }
    setBusy(true)
    try {
      const res = await api.resetPassword(token, password)
      setToken(res.token)
      navigate('/app/overview', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title={t('auth.reset.title')}>
      {!token ? (
        <>
          <p className="as-err">{t('auth.reset.incompleteLink')}</p>
          <Link to="/" className="as-link">{t('auth.verify.home')}</Link>
        </>
      ) : (
        <form onSubmit={submit} className="as-form">
          <label className="as-label">{t('auth.reset.newPassword')}</label>
          <input
            className="as-input"
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <label className="as-label">{t('auth.reset.repeat')}</label>
          <input
            className="as-input"
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={password2}
            onChange={(e) => setPassword2(e.target.value)}
            required
          />
          {error && <p className="as-err">{error}</p>}
          <button className="as-btn" type="submit" disabled={busy}>
            {busy ? '...' : t('auth.reset.save')}
          </button>
        </form>
      )}
    </AuthShell>
  )
}

function AuthShell({ title, children }) {
  return (
    <div className="as-page">
      <div className="as-card">
        <Link to="/" className="as-brand">NOWICKI</Link>
        <h1 className="as-title">{title}</h1>
        {children}
      </div>
      <style>{`
        .as-page { min-height: 100vh; display: grid; place-items: center; padding: 24px;
          background:
            radial-gradient(ellipse 80% 50% at 20% 0%, color-mix(in srgb, var(--accent) 12%, transparent), transparent 55%),
            radial-gradient(ellipse 60% 40% at 90% 100%, color-mix(in srgb, var(--long) 8%, transparent), transparent 50%),
            var(--bg); }
        .as-card {
          width: 100%; max-width: 400px; background: var(--glass);
          border: 1px solid var(--glass-border); border-radius: var(--radius-lg); padding: 28px;
          box-shadow: var(--shadow-lg), var(--inset-highlight);
          backdrop-filter: saturate(180%) blur(28px);
          -webkit-backdrop-filter: saturate(180%) blur(28px);
        }
        .as-brand { font-family: var(--font-display); font-weight: 700;
          font-size: 18px; color: var(--accent); letter-spacing: -0.03em; }
        .as-title { font-family: var(--font-display); font-size: 24px;
          font-weight: 700; margin: 16px 0 12px; color: var(--text); letter-spacing: -0.02em; }
        .as-form { display: flex; flex-direction: column; gap: 8px; }
        .as-label { font-size: 11px; font-weight: 600; color: var(--text-tertiary);
          text-transform: uppercase; letter-spacing: 0.04em; }
        .as-input { background: var(--surface-2); border: 1px solid var(--border);
          border-radius: var(--radius-sm); padding: 11px 14px; font-size: 14px; color: var(--text); font-family: var(--font-ui); }
        .as-btn { margin-top: 8px; background: var(--accent); color: #fff; border: none;
          border-radius: 980px; padding: 12px; font-weight: 650; cursor: pointer;
          box-shadow: 0 4px 14px color-mix(in srgb, var(--accent) 28%, transparent); }
        .as-btn:disabled { opacity: 0.6; box-shadow: none; }
        .as-muted { color: var(--text-secondary); font-size: 14px; }
        .as-ok { color: var(--accent); font-size: 14px; }
        .as-err { color: var(--short); font-size: 14px; }
        .as-link { display: inline-block; margin-top: 12px; color: var(--accent);
          font-weight: 600; font-size: 14px; }
      `}</style>
    </div>
  )
}
