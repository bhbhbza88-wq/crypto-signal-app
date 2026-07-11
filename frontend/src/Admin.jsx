import { useState, useEffect, useCallback } from 'react'
import { api } from './api'

const emptyTraderForm = { name: '', avatar_url: '', bio: '' }
const emptySignalForm = { trader_id: '', symbol: '', signal: 'LONG', entry: '', stop: '', tp1: '', tp2: '', tp3: '', note: '' }

export default function Admin() {
  const [traders, setTraders] = useState([])
  const [openSignals, setOpenSignals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [traderForm, setTraderForm] = useState(emptyTraderForm)
  const [traderBusy, setTraderBusy] = useState(false)
  const [traderMsg, setTraderMsg] = useState(null)

  const [signalForm, setSignalForm] = useState(emptySignalForm)
  const [signalBusy, setSignalBusy] = useState(false)
  const [signalMsg, setSignalMsg] = useState(null)

  const load = useCallback(async () => {
    try {
      const [t, s] = await Promise.all([api.adminGetTraders(), api.getSignals()])
      setTraders(t); setOpenSignals(s); setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function submitTrader(e) {
    e.preventDefault()
    setTraderBusy(true); setTraderMsg(null)
    try {
      await api.adminCreateTrader({
        name: traderForm.name.trim(),
        avatar_url: traderForm.avatar_url.trim() || null,
        bio: traderForm.bio.trim() || null,
      })
      setTraderForm(emptyTraderForm)
      setTraderMsg({ ok: true, text: 'Трейдер добавлен' })
      await load()
    } catch (err) {
      setTraderMsg({ ok: false, text: err.message })
    } finally {
      setTraderBusy(false)
    }
  }

  async function submitSignal(e) {
    e.preventDefault()
    setSignalBusy(true); setSignalMsg(null)
    try {
      await api.adminAddSignal({
        trader_id: Number(signalForm.trader_id),
        symbol: signalForm.symbol.trim(),
        signal: signalForm.signal,
        entry: Number(signalForm.entry),
        stop: Number(signalForm.stop),
        tp1: Number(signalForm.tp1),
        tp2: Number(signalForm.tp2),
        tp3: Number(signalForm.tp3),
        note: signalForm.note.trim() || null,
      })
      setSignalForm({ ...emptySignalForm, trader_id: signalForm.trader_id })
      setSignalMsg({ ok: true, text: 'Сигнал опубликован' })
      await load()
    } catch (err) {
      setSignalMsg({ ok: false, text: err.message })
    } finally {
      setSignalBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="adm-loading animate-in">
        <div className="adm-spinner" /><div>Загрузка...</div>
      </div>
    )
  }

  return (
    <div className="adm-page animate-in">
      <div className="page-header" style={{ marginBottom: 8 }}>
        <h1 className="page-title">Админка <span className="hot-tag">ADMIN</span></h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          Трейдеры и ручной ввод ТВХ. Статистика считается вживую из реальных закрытых сделок — не редактируется.
        </p>
      </div>

      {error && <div className="adm-error animate-in">❌ {error}</div>}

      <div className="adm-grid">
        {/* Трейдеры */}
        <section className="adm-card">
          <h2 className="section-title">Трейдеры</h2>
          <div className="adm-traders-list">
            {traders.length === 0 && <div className="adm-empty">Пока нет ни одного трейдера</div>}
            {traders.map(t => (
              <div key={t.id} className="adm-trader-row">
                <div className="adm-trader-name">
                  {t.name} {!t.is_active && <span className="adm-inactive">неактивен</span>}
                </div>
                <div className="adm-trader-stats">
                  <span>Винрейт: <b className={t.winrate == null ? '' : t.winrate >= 50 ? 'pos' : 'neg'}>{t.winrate != null ? `${t.winrate}%` : '—'}</b></span>
                  <span>PnL: <b className={t.total_pnl >= 0 ? 'pos' : 'neg'}>{t.total_pnl >= 0 ? '+' : ''}{t.total_pnl}%</b></span>
                  <span>Открыто: <b>{t.open_positions}</b></span>
                  <span>Закрыто: <b>{t.closed_trades}</b></span>
                </div>
              </div>
            ))}
          </div>

          <form onSubmit={submitTrader} className="adm-form">
            <div className="adm-form-title">Добавить трейдера</div>
            <input className="adm-input" placeholder="Имя" value={traderForm.name}
                   onChange={e => setTraderForm(f => ({ ...f, name: e.target.value }))} required />
            <input className="adm-input" placeholder="Ссылка на аватар (необязательно)" value={traderForm.avatar_url}
                   onChange={e => setTraderForm(f => ({ ...f, avatar_url: e.target.value }))} />
            <textarea className="adm-input" placeholder="Био (необязательно)" rows={2} value={traderForm.bio}
                   onChange={e => setTraderForm(f => ({ ...f, bio: e.target.value }))} />
            {traderMsg && <div className={traderMsg.ok ? 'adm-msg-ok' : 'adm-msg-err'}>{traderMsg.text}</div>}
            <button className="adm-submit" type="submit" disabled={traderBusy}>
              {traderBusy ? '...' : 'Добавить трейдера'}
            </button>
          </form>
        </section>

        {/* Новый сигнал */}
        <section className="adm-card">
          <h2 className="section-title">Новый сигнал (ТВХ)</h2>
          <form onSubmit={submitSignal} className="adm-form">
            <select className="adm-input" value={signalForm.trader_id}
                    onChange={e => setSignalForm(f => ({ ...f, trader_id: e.target.value }))} required>
              <option value="" disabled>Трейдер...</option>
              {traders.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <div className="adm-row2">
              <input className="adm-input" placeholder="Тикер (BTCUSDT)" value={signalForm.symbol}
                     onChange={e => setSignalForm(f => ({ ...f, symbol: e.target.value }))} required />
              <select className="adm-input" value={signalForm.signal}
                      onChange={e => setSignalForm(f => ({ ...f, signal: e.target.value }))}>
                <option value="LONG">LONG</option>
                <option value="SHORT">SHORT</option>
              </select>
            </div>
            <div className="adm-row2">
              <input className="adm-input" type="number" step="any" placeholder="Вход" value={signalForm.entry}
                     onChange={e => setSignalForm(f => ({ ...f, entry: e.target.value }))} required />
              <input className="adm-input" type="number" step="any" placeholder="Стоп" value={signalForm.stop}
                     onChange={e => setSignalForm(f => ({ ...f, stop: e.target.value }))} required />
            </div>
            <div className="adm-row3">
              <input className="adm-input" type="number" step="any" placeholder="TP1" value={signalForm.tp1}
                     onChange={e => setSignalForm(f => ({ ...f, tp1: e.target.value }))} required />
              <input className="adm-input" type="number" step="any" placeholder="TP2" value={signalForm.tp2}
                     onChange={e => setSignalForm(f => ({ ...f, tp2: e.target.value }))} required />
              <input className="adm-input" type="number" step="any" placeholder="TP3" value={signalForm.tp3}
                     onChange={e => setSignalForm(f => ({ ...f, tp3: e.target.value }))} required />
            </div>
            <textarea className="adm-input" placeholder="Комментарий к сделке (необязательно)" rows={2} value={signalForm.note}
                   onChange={e => setSignalForm(f => ({ ...f, note: e.target.value }))} />
            <div className="adm-hint">Для LONG: стоп &lt; вход &lt; TP1 &lt; TP2 &lt; TP3. Для SHORT — наоборот.</div>
            {signalMsg && <div className={signalMsg.ok ? 'adm-msg-ok' : 'adm-msg-err'}>{signalMsg.text}</div>}
            <button className="adm-submit" type="submit" disabled={signalBusy || traders.length === 0}>
              {signalBusy ? '...' : 'Опубликовать сигнал'}
            </button>
            {traders.length === 0 && <div className="adm-hint">Сначала добавь трейдера слева</div>}
          </form>
        </section>
      </div>

      {/* Открытые позиции */}
      <section className="adm-card" style={{ marginTop: 16 }}>
        <h2 className="section-title">Открытые позиции ({openSignals.length})</h2>
        <div className="adm-open-list">
          {openSignals.length === 0 && <div className="adm-empty">Открытых позиций нет</div>}
          {openSignals.map(s => (
            <div key={s.symbol} className="adm-open-row">
              <span className={`adm-open-side ${s.signal === 'LONG' ? 'pos' : 'neg'}`}>{s.signal}</span>
              <span className="adm-open-sym">{s.symbol}</span>
              <span className="adm-open-trader">{s.trader ? s.trader.name : '— (авто/старое)'}</span>
              <span className="adm-open-entry">вход {s.entry}</span>
            </div>
          ))}
        </div>
      </section>

      <style>{`
        .adm-loading { display: flex; align-items: center; gap: 16px; padding: 40px; color: var(--text-secondary); font-size: 14px; }
        .adm-spinner { width: 30px; height: 30px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: adm-spin 0.8s linear infinite; flex-shrink: 0; }
        @keyframes adm-spin { to { transform: rotate(360deg); } }
        .adm-error { background: var(--short-soft); border: 1px solid var(--short); border-radius: var(--radius-md); padding: 12px 16px; color: var(--short); font-size: 13px; margin-bottom: 16px; }
        .adm-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
        .adm-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px; box-shadow: var(--shadow-card); display: flex; flex-direction: column; gap: 14px; }
        .adm-empty { font-size: 13px; color: var(--text-tertiary); padding: 8px 0; }
        .adm-traders-list { display: flex; flex-direction: column; gap: 8px; max-height: 240px; overflow-y: auto; }
        .adm-trader-row { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }
        .adm-trader-name { font-size: 13px; font-weight: 700; color: var(--text); }
        .adm-inactive { font-size: 10px; font-weight: 500; color: var(--text-tertiary); margin-left: 6px; }
        .adm-trader-stats { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--text-secondary); }
        .adm-trader-stats b { color: var(--text); font-family: var(--font-mono); }
        .adm-form { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--border); padding-top: 12px; }
        .adm-form-title { font-size: 12px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; }
        .adm-input { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px 12px; font-size: 13px; color: var(--text); font-family: var(--font-ui); width: 100%; box-sizing: border-box; }
        .adm-input:focus { outline: none; border-color: var(--accent); }
        .adm-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .adm-row3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
        .adm-msg-ok { font-size: 12px; color: var(--long); }
        .adm-msg-err { font-size: 12px; color: var(--short); }
        .adm-hint { font-size: 11px; color: var(--text-tertiary); }
        .adm-submit { background: var(--accent); color: #fff; border: none; border-radius: var(--radius-sm); padding: 11px; font-size: 13px; font-weight: 700; cursor: pointer; }
        .adm-submit:disabled { opacity: 0.6; cursor: default; }
        .adm-open-list { display: flex; flex-direction: column; gap: 6px; }
        .adm-open-row { display: flex; align-items: center; gap: 12px; font-size: 12px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); flex-wrap: wrap; }
        .adm-open-side { font-weight: 800; font-family: var(--font-mono); width: 52px; }
        .adm-open-sym { font-weight: 700; color: var(--text); font-family: var(--font-mono); }
        .adm-open-trader { color: var(--text-secondary); }
        .adm-open-entry { margin-left: auto; color: var(--text-tertiary); font-family: var(--font-mono); }
        @media (max-width: 768px) {
          .adm-grid { grid-template-columns: 1fr; }
          .adm-row3 { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  )
}
