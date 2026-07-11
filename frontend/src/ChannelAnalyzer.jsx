import { useState, useRef, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts'
import { api } from './api'

const POLL_MS = 3000

function Metric({ label, value, sub }) {
  return (
    <div className="ca-metric">
      <div className="ca-metric-label">{label}</div>
      <div className="ca-metric-val">{value}</div>
      {sub && <div className="ca-metric-sub">{sub}</div>}
    </div>
  )
}

const OUTCOME_LABEL = {
  win: 'Прибыль', loss: 'Убыток', not_filled: 'Не дошла до входа',
  no_data: 'Нет данных биржи', timeout: 'Не дошла ни до TP1, ни до SL',
}

function TpCell({ level, hit }) {
  if (level == null) return <td className="ca-hist-dim">—</td>
  return (
    <td>
      {level}
      {hit === true && <span className="ca-tp-hit" title="Цена дошла до этого уровня">✓</span>}
      {hit === false && <span className="ca-tp-miss" title="Не дошла">✕</span>}
    </td>
  )
}

function HistoryRow({ s }) {
  const isWin = s.outcome === 'win'
  const isLoss = s.outcome === 'loss'
  const tone = isWin ? 'pos' : isLoss ? 'neg' : 'neutral'
  return (
    <tr className={`ca-hist-row ${tone}`}>
      <td>{s.posted_at?.slice(0, 16).replace('T', ' ')}</td>
      <td className="ca-hist-sym">{s.symbol}</td>
      <td>{s.side}</td>
      <td>{s.entry}</td>
      <td>{s.stop}</td>
      <td>{s.tp1}</td>
      <TpCell level={s.tp2} hit={s.tp2_hit} />
      <TpCell level={s.tp3} hit={s.tp3_hit} />
      <td><span className={`ca-hist-badge ${tone}`}>{OUTCOME_LABEL[s.outcome] || (s.checked_at ? 'В обработке' : 'Не сверено')}</span></td>
      <td className={tone === 'pos' ? 'pos' : tone === 'neg' ? 'neg' : ''}>
        {s.pnl_pct != null ? `${s.pnl_pct >= 0 ? '+' : ''}${s.pnl_pct}%` : '—'}
      </td>
    </tr>
  )
}

function RankingRow({ c }) {
  const pos = (c.total_pnl_pct ?? 0) >= 0
  return (
    <tr className="ca-rank-row">
      <td className="ca-hist-sym">{c.channel}</td>
      <td>{c.total_signals}</td>
      <td>{c.closed_trades}</td>
      <td>{c.winrate_pct != null ? `${c.winrate_pct}%` : '—'}</td>
      <td>{c.avg_risk_reward ?? '—'}</td>
      <td className={pos ? 'pos' : 'neg'}>{pos ? '+' : ''}{c.total_pnl_pct}%</td>
      <td className="ca-hist-dim">{c.last_analyzed_at?.slice(0, 10)}</td>
    </tr>
  )
}

export default function ChannelAnalyzer() {
  const [url, setUrl] = useState('')
  const [days, setDays] = useState(30)
  const [entryTimeoutHours, setEntryTimeoutHours] = useState(6)
  const [status, setStatus] = useState('idle')   // idle | running | done | error
  const [step, setStep] = useState('')
  const [error, setError] = useState(null)
  const [report, setReport] = useState(null)
  const [curve, setCurve] = useState([])
  const [cached, setCached] = useState(false)
  const [history, setHistory] = useState([])
  const [ranking, setRanking] = useState([])
  const pollRef = useRef(null)

  useEffect(() => () => clearInterval(pollRef.current), [])

  const loadRanking = async () => {
    try { setRanking(await api.getChannelsRanking()) } catch { /* тихо — это вспомогательный блок */ }
  }

  useEffect(() => { loadRanking() }, [])

  const loadHistory = async (channel) => {
    try { setHistory(await api.getChannelHistory(channel)) } catch { setHistory([]) }
  }

  const pollStatus = (jobId, channel) => {
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getAnalysisStatus(jobId)
        setStep(s.step || '')
        if (s.status === 'done') {
          clearInterval(pollRef.current)
          setReport(s.result.report)
          setCurve(s.result.equity_curve || [])
          setStatus('done')
          loadHistory(channel)
          loadRanking()
        } else if (s.status === 'failed') {
          clearInterval(pollRef.current)
          setError(s.error || 'Анализ завершился ошибкой')
          setStatus('error')
        }
      } catch {
        clearInterval(pollRef.current)
        setError('Потеряна связь с сервером')
        setStatus('error')
      }
    }, POLL_MS)
  }

  const analyze = async () => {
    if (!url.trim()) return
    clearInterval(pollRef.current)
    setStatus('running'); setError(null); setReport(null); setCurve([]); setHistory([]); setStep('Отправка запроса...')
    try {
      const res = await api.analyzeChannel(url.trim(), days, entryTimeoutHours)
      setCached(!!res.cached)
      if (res.cached) {
        setReport(res.report)
        setCurve(res.equity_curve || [])
        setStatus('done')
        loadHistory(res.channel)
      } else {
        setStep('Анализирую историю...')
        pollStatus(res.job_id, res.channel)
      }
    } catch (e) {
      setError(e.message)
      setStatus('error')
    }
  }

  const posTotal = (report?.total_pnl_pct_fixed_size ?? 0) >= 0

  return (
    <div className="ca-page animate-in">
      <div className="page-header" style={{ marginBottom: 8 }}>
        <h1 className="page-title">Channel Analyzer <span className="hot-tag">ADMIN</span></h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          Честная сверка сигналов Telegram-канала с реальными ценами на бирже за прошлый период.
        </p>
      </div>

      <div className="ca-input-row">
        <input
          className="ca-input"
          placeholder="https://t.me/channel_username"
          value={url}
          onChange={e => setUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && status !== 'running' && analyze()}
          disabled={status === 'running'}
        />
        <select className="ca-days" value={days} onChange={e => setDays(Number(e.target.value))} disabled={status === 'running'}>
          <option value={7}>7 дней</option>
          <option value={30}>30 дней</option>
          <option value={90}>90 дней</option>
        </select>
        <select
          className="ca-days"
          value={entryTimeoutHours}
          onChange={e => setEntryTimeoutHours(Number(e.target.value))}
          disabled={status === 'running'}
          title="Сколько ждать, пока цена дойдёт до Entry, прежде чем считать сигнал непройденным"
        >
          <option value={2}>Вход за 2ч</option>
          <option value={6}>Вход за 6ч</option>
          <option value={12}>Вход за 12ч</option>
          <option value={24}>Вход за 24ч</option>
          <option value={48}>Вход за 48ч</option>
        </select>
        <button className="ca-btn" onClick={analyze} disabled={status === 'running' || !url.trim()}>
          {status === 'running' ? 'Анализирую...' : 'Analyze'}
        </button>
      </div>

      {status === 'running' && (
        <div className="ca-status animate-in">
          <span className="ca-spinner" />
          <span>{step || 'Анализирую историю...'}</span>
        </div>
      )}

      {status === 'error' && (
        <div className="bt-error animate-in">❌ {error}</div>
      )}

      {status === 'done' && report && (
        <div className="animate-in">
          {cached && <div className="ca-cache-note">Показан кэш анализа (обновляется раз в 24ч)</div>}

          <div className="ca-metrics">
            <Metric label="Сигналов найдено" value={report.total_signals} />
            <Metric label="Закрытых сделок" value={report.closed_trades} />
            <Metric label="Winrate" value={report.winrate_pct != null ? `${report.winrate_pct}%` : '—'} />
            <Metric label="Средний R:R" value={report.avg_risk_reward ?? '—'} />
            <Metric
              label="Итоговый PnL (фикс. объём)"
              value={<span className={posTotal ? 'pos' : 'neg'}>{posTotal ? '+' : ''}{report.total_pnl_pct_fixed_size}%</span>}
              sub={`комиссия 0.1% учтена`}
            />
            {report.tp2_hit_rate != null && (
              <Metric label="Доходили до TP2" value={`${report.tp2_hit_rate}%`} sub={`из ${report.tp2_sample} сигналов с заявленным TP2`} />
            )}
            {report.tp3_hit_rate != null && (
              <Metric label="Доходили до TP3" value={`${report.tp3_hit_rate}%`} sub={`из ${report.tp3_sample} сигналов с заявленным TP3`} />
            )}
          </div>

          {curve.length > 1 ? (
            <div className="ca-chart">
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={curve}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-tertiary)', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'var(--text-tertiary)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} tickFormatter={v => `${v}%`} width={50} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, fontFamily: 'var(--font-mono)', fontSize: 12 }} formatter={v => [`${v}%`, 'Кум. PnL']} />
                  <ReferenceLine y={0} stroke="var(--text-tertiary)" strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="cum_pnl_pct" stroke={posTotal ? 'var(--long)' : 'var(--short)'} strokeWidth={2.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="ca-empty">Недостаточно закрытых сделок для графика доходности.</div>
          )}

          {history.length > 0 && (
            <div className="ca-hist">
              <h3 className="ca-hist-title">История всех найденных сигналов ({history.length})</h3>
              <div className="ca-hist-scroll">
                <table className="ca-hist-table">
                  <thead>
                    <tr>
                      <th>Дата поста</th><th>Символ</th><th>Сторона</th>
                      <th>Entry</th><th>Stop</th><th>TP1</th><th>TP2</th><th>TP3</th><th>Исход</th><th>PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map(s => <HistoryRow key={s.id} s={s} />)}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {ranking.length > 0 && (
        <div className="ca-hist" style={{ marginTop: 34 }}>
          <h3 className="ca-hist-title">Сравнение проанализированных каналов ({ranking.length})</h3>
          <div className="ca-hist-scroll">
            <table className="ca-hist-table">
              <thead>
                <tr>
                  <th>Канал</th><th>Сигналов</th><th>Закрытых сделок</th>
                  <th>Winrate</th><th>R:R</th><th>Итоговый PnL</th><th>Обновлено</th>
                </tr>
              </thead>
              <tbody>
                {ranking.map(c => <RankingRow key={c.channel} c={c} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <style>{`
        .ca-input-row { display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap; }
        .ca-input { flex: 1; min-width: 240px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 11px 14px; color: var(--text); font-size: 14px; }
        .ca-input:focus { outline: none; border-color: var(--accent); }
        .ca-days { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 11px 12px; color: var(--text); font-size: 13px; }
        .ca-btn { background: var(--accent); color: #fff; border: none; border-radius: 10px; padding: 11px 22px; font-weight: 600; font-size: 14px; cursor: pointer; }
        .ca-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .ca-status { display: flex; align-items: center; gap: 10px; margin-top: 18px; padding: 14px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; color: var(--text-secondary); font-size: 13px; }
        .ca-spinner { width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: ca-spin 0.8s linear infinite; flex-shrink: 0; }
        @keyframes ca-spin { to { transform: rotate(360deg); } }
        .ca-cache-note { font-size: 12px; color: var(--text-tertiary); margin-top: 16px; }
        .ca-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin-top: 18px; }
        .ca-metric { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
        .ca-metric-label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
        .ca-metric-val { font-size: 22px; font-weight: 700; font-family: var(--font-mono); color: var(--text); margin-top: 6px; }
        .ca-metric-sub { font-size: 11px; color: var(--text-tertiary); margin-top: 3px; }
        .ca-metric-val .pos { color: var(--long); }
        .ca-metric-val .neg { color: var(--short); }
        .ca-chart { margin-top: 22px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
        .ca-empty { margin-top: 22px; padding: 30px; text-align: center; color: var(--text-tertiary); font-size: 13px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }

        .ca-hist { margin-top: 22px; }
        .ca-hist-title { font-size: 14px; font-weight: 600; color: var(--text); margin: 0 0 10px; }
        .ca-hist-scroll { overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }
        .ca-hist-table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: var(--font-mono); white-space: nowrap; }
        .ca-hist-table th { text-align: left; padding: 10px 14px; color: var(--text-tertiary); font-weight: 600; border-bottom: 1px solid var(--border); text-transform: uppercase; font-size: 10px; letter-spacing: 0.03em; }
        .ca-hist-table td { padding: 9px 14px; border-bottom: 1px solid var(--border); color: var(--text); }
        .ca-hist-row:last-child td { border-bottom: none; }
        .ca-hist-row.pos { background: var(--long-soft); }
        .ca-hist-row.neg { background: var(--short-soft); }
        .ca-hist-sym { font-weight: 700; }
        .ca-hist-badge { padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; }
        .ca-hist-badge.pos { color: var(--long); background: rgba(0,200,150,0.12); }
        .ca-hist-badge.neg { color: var(--short); background: rgba(240,74,89,0.12); }
        .ca-hist-badge.neutral { color: var(--text-tertiary); background: var(--surface-hover); }
        .ca-hist-row td.pos { color: var(--long); font-weight: 700; }
        .ca-hist-row td.neg { color: var(--short); font-weight: 700; }
        .ca-hist-dim { color: var(--text-tertiary); }
        .ca-tp-hit { color: var(--long); margin-left: 5px; font-weight: 700; }
        .ca-tp-miss { color: var(--text-tertiary); margin-left: 5px; }
        .ca-rank-row td.pos { color: var(--long); font-weight: 700; }
        .ca-rank-row td.neg { color: var(--short); font-weight: 700; }
      `}</style>
    </div>
  )
}
