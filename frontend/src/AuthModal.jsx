import { useState } from 'react'
import { api, setToken } from './api'

export default function AuthModal({ onClose, onAuth }) {
  const [mode, setMode] = useState('login')   // 'login' | 'register'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError(null); setBusy(true)
    try {
      const fn = mode === 'login' ? api.login : api.register
      const res = await fn(email, password)
      setToken(res.token)
      onAuth(res.user)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="am-overlay" onClick={onClose}>
      <div className="am-modal" onClick={e => e.stopPropagation()}>
        <button className="am-close" onClick={onClose}>✕</button>
        <h2 className="am-title">{mode === 'login' ? 'Вход' : 'Регистрация'}</h2>
        <p className="am-sub">{mode === 'login' ? 'Войдите в аккаунт NWICKI' : 'Создайте бесплатный аккаунт'}</p>

        <form onSubmit={submit} className="am-form">
          <input className="am-input" type="email" placeholder="Email" value={email}
                 onChange={e => setEmail(e.target.value)} autoFocus required />
          <input className="am-input" type="password" placeholder="Пароль (мин. 6 символов)" value={password}
                 onChange={e => setPassword(e.target.value)} required />
          {error && <div className="am-error">{error}</div>}
          <button className="am-submit" type="submit" disabled={busy}>
            {busy ? '...' : (mode === 'login' ? 'Войти' : 'Зарегистрироваться')}
          </button>
        </form>

        <div className="am-switch">
          {mode === 'login' ? (
            <>Нет аккаунта? <button onClick={() => { setMode('register'); setError(null) }}>Регистрация</button></>
          ) : (
            <>Уже есть аккаунт? <button onClick={() => { setMode('login'); setError(null) }}>Войти</button></>
          )}
        </div>

        <style>{`
          .am-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; z-index: 1000; }
          .am-modal { position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 28px; width: 360px; max-width: 92vw; box-shadow: var(--shadow-lg); }
          .am-close { position: absolute; top: 14px; right: 14px; background: none; border: none; color: var(--text-tertiary); font-size: 16px; cursor: pointer; }
          .am-title { font-size: 22px; font-weight: 800; color: var(--text); }
          .am-sub { font-size: 13px; color: var(--text-secondary); margin: 4px 0 18px; }
          .am-form { display: flex; flex-direction: column; gap: 10px; }
          .am-input { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 11px 14px; font-size: 14px; color: var(--text); font-family: var(--font-ui); }
          .am-input:focus { outline: none; border-color: var(--accent); }
          .am-error { font-size: 12px; color: var(--short); }
          .am-submit { background: var(--accent); color: #fff; border: none; border-radius: var(--radius-sm); padding: 12px; font-size: 14px; font-weight: 700; cursor: pointer; margin-top: 4px; }
          .am-submit:disabled { opacity: 0.6; }
          .am-switch { text-align: center; font-size: 13px; color: var(--text-secondary); margin-top: 16px; }
          .am-switch button { background: none; border: none; color: var(--accent); cursor: pointer; font-weight: 600; }
        `}</style>
      </div>
    </div>
  )
}
