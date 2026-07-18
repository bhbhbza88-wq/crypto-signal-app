import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, setToken } from './api'

export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState('loading') // loading | ok | err
  const [message, setMessage] = useState('')

  useEffect(() => {
    const token = params.get('token')
    if (!token) {
      setStatus('err')
      setMessage('Нет токена в ссылке')
      return
    }
    api.verifyEmail(token)
      .then((res) => {
        setToken(res.token)
        setStatus('ok')
        setMessage('Email подтверждён. Переходим в кабинет…')
        setTimeout(() => navigate('/app/overview', { replace: true }), 1200)
      })
      .catch((err) => {
        setStatus('err')
        setMessage(err.message || 'Не удалось подтвердить')
      })
  }, [params, navigate])

  return (
    <AuthShell title="Подтверждение email">
      {status === 'loading' && <p className="as-muted">Проверяем ссылку…</p>}
      {status === 'ok' && <p className="as-ok">{message}</p>}
      {status === 'err' && (
        <>
          <p className="as-err">{message}</p>
          <Link to="/" className="as-link">На главную</Link>
        </>
      )}
    </AuthShell>
  )
}

export function ResetPasswordPage() {
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
      setError('Пароль минимум 8 символов')
      return
    }
    if (password !== password2) {
      setError('Пароли не совпадают')
      return
    }
    if (!token) {
      setError('Нет токена в ссылке')
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
    <AuthShell title="Новый пароль">
      {!token ? (
        <>
          <p className="as-err">Ссылка неполная — запроси сброс пароля ещё раз.</p>
          <Link to="/" className="as-link">На главную</Link>
        </>
      ) : (
        <form onSubmit={submit} className="as-form">
          <label className="as-label">Новый пароль</label>
          <input
            className="as-input"
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <label className="as-label">Ещё раз</label>
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
            {busy ? '...' : 'Сохранить и войти'}
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
          background: radial-gradient(ellipse at 20% 0%, rgba(0,180,160,0.12), transparent 50%),
                      radial-gradient(ellipse at 80% 100%, rgba(20,40,60,0.4), transparent 45%),
                      var(--bg, #0b1118); }
        .as-card { width: 100%; max-width: 400px; background: var(--surface, #121a24);
          border: 1px solid var(--border, #243041); border-radius: 16px; padding: 28px; }
        .as-brand { font-family: var(--font-display, Syne, sans-serif); font-weight: 800;
          font-size: 18px; color: var(--accent, #00c9a7); letter-spacing: -0.03em; }
        .as-title { font-family: var(--font-display, Syne, sans-serif); font-size: 24px;
          font-weight: 800; margin: 16px 0 12px; color: var(--text, #e8eef5); }
        .as-form { display: flex; flex-direction: column; gap: 8px; }
        .as-label { font-size: 11px; font-weight: 600; color: var(--text-tertiary, #8a9bb0);
          text-transform: uppercase; letter-spacing: 0.04em; }
        .as-input { background: var(--surface-2, #0f1620); border: 1px solid var(--border, #243041);
          border-radius: 8px; padding: 11px 14px; font-size: 14px; color: var(--text, #e8eef5); }
        .as-btn { margin-top: 8px; background: var(--accent, #00c9a7); color: #fff; border: none;
          border-radius: 8px; padding: 12px; font-weight: 700; cursor: pointer; }
        .as-btn:disabled { opacity: 0.6; }
        .as-muted { color: var(--text-secondary, #a8b6c8); font-size: 14px; }
        .as-ok { color: var(--accent, #00c9a7); font-size: 14px; }
        .as-err { color: #ff6b7a; font-size: 14px; }
        .as-link { display: inline-block; margin-top: 12px; color: var(--accent, #00c9a7);
          font-weight: 600; font-size: 14px; }
      `}</style>
    </div>
  )
}
