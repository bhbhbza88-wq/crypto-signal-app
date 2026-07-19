import { useState, useEffect, useCallback } from 'react'
import { api } from './api'

const emptyTraderForm = { name: '', avatar_url: '', bio: '' }
const emptySignalForm = { trader_id: '', symbol: '', signal: 'LONG', entry: '', stop: '', tp1: '', tp2: '', tp3: '', note: '' }

const ADMIN_TABS = [
  { key: 'traders',   label: 'Трейдеры' },
  { key: 'signal',    label: 'Новый сигнал' },
  { key: 'open',      label: 'Открытые позиции' },
  { key: 'premium',   label: 'Premium' },
  { key: 'channels',  label: 'История по каналам' },
  { key: 'engage',    label: 'Telegram практика' },
  { key: 'backfill',  label: 'Публикация истории' },
]

export default function Admin() {
  const [tab, setTab] = useState('traders')
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

  const [premiumEmail, setPremiumEmail] = useState('')
  const [premiumDays, setPremiumDays] = useState(30)
  const [premiumBusy, setPremiumBusy] = useState(false)
  const [premiumMsg, setPremiumMsg] = useState(null)
  const [premiumRequests, setPremiumRequests] = useState([])
  const [engageBusy, setEngageBusy] = useState(false)
  const [engageMsg, setEngageMsg] = useState(null)
  const [backfillBusy, setBackfillBusy] = useState(false)
  const [backfillMsg, setBackfillMsg] = useState(null)

  const [channelDays, setChannelDays] = useState(14)
  const [channelStats, setChannelStats] = useState({ rows: [], since: null, days: 14 })

  const load = useCallback(async () => {
    try {
      const [t, s, reqs, ch] = await Promise.all([
        api.adminGetTraders(),
        api.getSignals(),
        api.adminPremiumRequests().catch(() => []),
        api.adminChannelDaily(channelDays).catch(() => ({ rows: [], days: channelDays })),
      ])
      setTraders(t); setOpenSignals(s); setPremiumRequests(reqs); setChannelStats(ch); setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [channelDays])

  useEffect(() => { load() }, [load])

  // Group channel rows by date for display
  const channelByDate = (() => {
    const map = new Map()
    for (const r of channelStats.rows || []) {
      if (!map.has(r.date)) map.set(r.date, [])
      map.get(r.date).push(r)
    }
    return [...map.entries()]
  })()

  async function submitPremium(e) {
    e.preventDefault()
    setPremiumBusy(true); setPremiumMsg(null)
    try {
      const r = await api.adminGrantPremium(premiumEmail.trim(), Number(premiumDays) || 30, 'premium')
      setPremiumMsg({
        ok: true,
        text: `Premium выдан: ${r.email} до ${r.premium_until ? String(r.premium_until).slice(0, 10) : '—'}`,
      })
      setPremiumEmail('')
      await load()
    } catch (err) {
      setPremiumMsg({ ok: false, text: err.message })
    } finally {
      setPremiumBusy(false)
    }
  }

  async function runEngageTest() {
    setEngageBusy(true); setEngageMsg(null)
    try {
      const r = await api.adminChatEngageTest({ target: 'Kupyansk_2' })
      setEngageMsg({
        ok: true,
        text: `${r.detail}. Жди у @Kupyansk_2 карточку профита + короткий текст.`,
      })
    } catch (err) {
      setEngageMsg({ ok: false, text: err.message })
    } finally {
      setEngageBusy(false)
    }
  }

  async function runBackfillHistory() {
    if (!confirm(
      'Опубликовать всю ещё не отправленную историю сделок в @papayaqq?\n' +
      'Крупные минусы отфильтруются автоматически, посты уходят с паузами (не сразу все).'
    )) return
    setBackfillBusy(true); setBackfillMsg(null)
    try {
      const r = await api.adminBackfillChannelHistory()
      setBackfillMsg({ ok: true, text: r.detail })
    } catch (err) {
      setBackfillMsg({ ok: false, text: err.message })
    } finally {
      setBackfillBusy(false)
    }
  }

  async function revokePremium(email) {
    if (!confirm(`Снять Premium с ${email}?`)) return
    setPremiumBusy(true); setPremiumMsg(null)
    try {
      await api.adminGrantPremium(email, 30, 'free')
      setPremiumMsg({ ok: true, text: `Снято: ${email} → free` })
      await load()
    } catch (err) {
      setPremiumMsg({ ok: false, text: err.message })
    } finally {
      setPremiumBusy(false)
    }
  }

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
          Premium, трейдеры и ручной ввод ТВХ. Статистика считается вживую из закрытых сделок.
        </p>
      </div>

      {error && <div className="adm-error animate-in">❌ {error}</div>}

      <div className="adm-tabs">
        {ADMIN_TABS.map(t => (
          <button
            key={t.key}
            type="button"
            className={`adm-tab-btn ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* История по каналам */}
      {tab === 'channels' && <section className="adm-card" style={{ marginTop: 16 }}>
        <div className="adm-ch-head">
          <h2 className="section-title" style={{ margin: 0, flex: 1 }}>История по каналам</h2>
          <select
            className="adm-input adm-ch-days"
            value={channelDays}
            onChange={e => setChannelDays(Number(e.target.value))}
          >
            <option value={7}>7 дней</option>
            <option value={14}>14 дней</option>
            <option value={30}>30 дней</option>
            <option value={60}>60 дней</option>
          </select>
        </div>
        <p className="adm-hint" style={{ marginTop: -4 }}>
          Сколько сделок закрылось с каждого канала за день и сколько из них в плюс (PnL &gt; 0).
        </p>
        {channelByDate.length === 0 ? (
          <div className="adm-empty">За выбранный период закрытых сделок нет</div>
        ) : (
          <div className="adm-ch-days-list">
            {channelByDate.map(([date, rows]) => {
              const dayTotal = rows.reduce((s, r) => s + r.total, 0)
              const dayWins = rows.reduce((s, r) => s + r.wins, 0)
              const dayPnl = rows.reduce((s, r) => s + r.total_pnl, 0)
              return (
                <div key={date} className="adm-ch-day">
                  <div className="adm-ch-day-head">
                    <span className="adm-ch-date">{date}</span>
                    <span className="adm-ch-sum">
                      {dayTotal} сделок · <b className="pos">{dayWins} в плюс</b>
                      {' · '}
                      <b className={dayPnl >= 0 ? 'pos' : 'neg'}>{dayPnl >= 0 ? '+' : ''}{dayPnl.toFixed(1)}%</b>
                    </span>
                  </div>
                  <div className="adm-ch-table">
                    <div className="adm-ch-tr head">
                      <span>Канал</span>
                      <span>Сделок</span>
                      <span>В плюс</span>
                      <span>Винрейт</span>
                      <span>PnL</span>
                    </div>
                    {rows.map(r => (
                      <div key={`${date}-${r.trader_id}-${r.channel}`} className="adm-ch-tr">
                        <span className="adm-ch-name" title={r.source_type}>{r.channel}</span>
                        <span className="mono">{r.total}</span>
                        <span className="mono pos">{r.wins}</span>
                        <span className="mono">{r.winrate}%</span>
                        <span className={`mono ${r.total_pnl >= 0 ? 'pos' : 'neg'}`}>
                          {r.total_pnl >= 0 ? '+' : ''}{r.total_pnl}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>}

      {/* Практика chat engage */}
      {tab === 'engage' && <section className="adm-card" style={{ marginTop: 16 }}>
        <h2 className="section-title">Практика engage (профит)</h2>
        <p className="adm-hint" style={{ marginTop: -6 }}>
          В чаты больше не пишем входы. Только хороший плюс + карточка PnL.
          Практика сейчас: контакт <b>@Kupyansk_2</b> — картинка профита и короткий текст.
        </p>
        {engageMsg && <div className={engageMsg.ok ? 'adm-msg-ok' : 'adm-msg-err'}>{engageMsg.text}</div>}
        <button
          className="adm-submit"
          type="button"
          disabled={engageBusy}
          onClick={runEngageTest}
          style={{ marginTop: 8 }}
        >
          {engageBusy ? 'Отправка…' : 'Практика → Kupyansk_2'}
        </button>
      </section>}

      {/* Бэкфилл истории в публичный канал */}
      {tab === 'backfill' && <section className="adm-card" style={{ marginTop: 16 }}>
        <h2 className="section-title">История → канал результатов</h2>
        <p className="adm-hint" style={{ marginTop: -6 }}>
          Публикует уже закрытые сделки из истории в <b>@papayaqq</b>, которые туда
          ещё не попали. Профит и небольшой минус — с карточкой, крупный минус
          пропускается. Повторный запуск шлёт только новое (не дублирует).
        </p>
        {backfillMsg && <div className={backfillMsg.ok ? 'adm-msg-ok' : 'adm-msg-err'}>{backfillMsg.text}</div>}
        <button
          className="adm-submit"
          type="button"
          disabled={backfillBusy}
          onClick={runBackfillHistory}
          style={{ marginTop: 8 }}
        >
          {backfillBusy ? 'Запуск…' : 'Опубликовать историю → @papayaqq'}
        </button>
      </section>}

      {/* Дать Premium */}
      {tab === 'premium' && <section className="adm-card adm-premium" style={{ marginTop: 16 }}>
        <h2 className="section-title">Дать Premium</h2>
        <p className="adm-hint" style={{ marginTop: -6 }}>
          Впиши email с nowicki.trade — тариф станет Premium. Потом вручную добавь человека в платный канал/чат.
        </p>
        <form onSubmit={submitPremium} className="adm-form" style={{ borderTop: 'none', paddingTop: 0 }}>
          <div className="adm-row2">
            <input
              className="adm-input"
              type="email"
              placeholder="email@gmail.com"
              value={premiumEmail}
              onChange={e => setPremiumEmail(e.target.value)}
              required
            />
            <input
              className="adm-input"
              type="number"
              min={1}
              max={3650}
              placeholder="Дней"
              value={premiumDays}
              onChange={e => setPremiumDays(e.target.value)}
              title="Срок в днях"
            />
          </div>
          {premiumMsg && <div className={premiumMsg.ok ? 'adm-msg-ok' : 'adm-msg-err'}>{premiumMsg.text}</div>}
          <button className="adm-submit" type="submit" disabled={premiumBusy || !premiumEmail.trim()}>
            {premiumBusy ? '...' : 'Выдать Premium'}
          </button>
        </form>
        {premiumRequests.length > 0 && (
          <div className="adm-req-list">
            <div className="adm-form-title">Заявки из Telegram («Я оплатил»)</div>
            {premiumRequests.slice(0, 12).map(r => (
              <div key={r.id} className="adm-req-row">
                <span className="adm-req-email">{r.email}</span>
                <span className={`adm-req-status ${r.status}`}>{r.status}</span>
                <span className="adm-req-date">{String(r.created_at || '').slice(0, 16).replace('T', ' ')}</span>
                {r.status === 'pending' && (
                  <button
                    type="button"
                    className="adm-req-btn"
                    disabled={premiumBusy}
                    onClick={() => { setPremiumEmail(r.email); }}
                  >
                    Подставить
                  </button>
                )}
                {r.status === 'granted' && (
                  <button type="button" className="adm-req-btn ghost" disabled={premiumBusy} onClick={() => revokePremium(r.email)}>
                    Снять
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>}

      {/* Трейдеры */}
      {tab === 'traders' && (
        <section className="adm-card" style={{ marginTop: 16 }}>
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
      )}

      {/* Новый сигнал */}
      {tab === 'signal' && (
        <section className="adm-card" style={{ marginTop: 16 }}>
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
            {traders.length === 0 && <div className="adm-hint">Сначала добавь трейдера во вкладке «Трейдеры»</div>}
          </form>
        </section>
      )}

      {/* Открытые позиции */}
      {tab === 'open' && (
        <section className="adm-card" style={{ marginTop: 16 }}>
          <h2 className="section-title">Открытые позиции ({openSignals.length})</h2>
          <div className="adm-open-list">
            {openSignals.length === 0 && <div className="adm-empty">Открытых позиций нет</div>}
            {openSignals.map(s => (
              <div key={s.id ?? s.symbol} className="adm-open-row">
                <span className={`adm-open-side ${s.signal === 'LONG' ? 'pos' : 'neg'}`}>{s.signal}</span>
                <span className="adm-open-sym">{s.symbol}</span>
                <span className="adm-open-trader">{s.trader ? s.trader.name : '— (авто/старое)'}</span>
                <span className="adm-open-entry">вход {s.entry}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <style>{`
        .adm-loading { display: flex; align-items: center; gap: 16px; padding: 40px; color: var(--text-secondary); font-size: 14px; }
        .adm-spinner { width: 30px; height: 30px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: adm-spin 0.8s linear infinite; flex-shrink: 0; }
        @keyframes adm-spin { to { transform: rotate(360deg); } }
        .adm-error { background: var(--short-soft); border: 1px solid var(--short); border-radius: var(--radius-md); padding: 12px 16px; color: var(--short); font-size: 13px; margin-bottom: 16px; }
        .adm-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }
        .adm-tab-btn { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; font-weight: 700; padding: 8px 14px; border-radius: 20px; cursor: pointer; transition: background 0.15s, color 0.15s, border-color 0.15s; }
        .adm-tab-btn:hover { color: var(--text); border-color: color-mix(in srgb, var(--accent) 30%, var(--border)); }
        .adm-tab-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
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
        .adm-premium { border-color: color-mix(in srgb, var(--accent) 35%, var(--border)); }
        .adm-ch-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
        .adm-ch-days { width: auto; max-width: 120px; padding: 8px 10px; }
        .adm-ch-days-list { display: flex; flex-direction: column; gap: 14px; max-height: 520px; overflow-y: auto; }
        .adm-ch-day { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; }
        .adm-ch-day-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; padding: 10px 12px; background: var(--surface-hover); border-bottom: 1px solid var(--border); }
        .adm-ch-date { font-weight: 800; font-family: var(--font-mono); font-size: 13px; }
        .adm-ch-sum { font-size: 12px; color: var(--text-secondary); }
        .adm-ch-table { display: flex; flex-direction: column; }
        .adm-ch-tr { display: grid; grid-template-columns: 1.6fr 0.7fr 0.7fr 0.8fr 0.8fr; gap: 8px; padding: 8px 12px; font-size: 12px; border-top: 1px solid var(--border); align-items: center; }
        .adm-ch-tr.head { border-top: none; color: var(--text-tertiary); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; font-size: 10px; background: transparent; }
        .adm-ch-name { font-weight: 650; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .adm-ch-tr .mono { font-family: var(--font-mono); font-weight: 700; }
        .adm-req-list { display: flex; flex-direction: column; gap: 6px; border-top: 1px solid var(--border); padding-top: 12px; }
        .adm-req-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 12px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); }
        .adm-req-email { font-weight: 700; font-family: var(--font-mono); color: var(--text); }
        .adm-req-status { text-transform: uppercase; font-size: 10px; font-weight: 800; letter-spacing: 0.04em; color: var(--text-tertiary); }
        .adm-req-status.pending { color: var(--amber); }
        .adm-req-status.granted { color: var(--long); }
        .adm-req-date { color: var(--text-tertiary); margin-left: auto; }
        .adm-req-btn { border: 1px solid var(--border); background: var(--surface-hover); color: var(--text); border-radius: 8px; padding: 5px 10px; font-size: 11px; font-weight: 700; cursor: pointer; }
        .adm-req-btn.ghost { opacity: 0.75; }
        .adm-open-list { display: flex; flex-direction: column; gap: 6px; }
        .adm-open-row { display: flex; align-items: center; gap: 12px; font-size: 12px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); flex-wrap: wrap; }
        .adm-open-side { font-weight: 800; font-family: var(--font-mono); width: 52px; }
        .adm-open-sym { font-weight: 700; color: var(--text); font-family: var(--font-mono); }
        .adm-open-trader { color: var(--text-secondary); }
        .adm-open-entry { margin-left: auto; color: var(--text-tertiary); font-family: var(--font-mono); }
        @media (max-width: 768px) {
          .adm-row3 { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  )
}
