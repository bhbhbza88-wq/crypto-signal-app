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

export default function ChannelAnalyzer() {
  const [url, setUrl] = useState('')
  const [days, setDays] = useState(30)
  const [status, setStatus] = useState('idle')   // idle | running | done | error
  const [step, setStep] = useState('')
  const [error, setError] = useState(null)
  const [report, setReport] = useState(null)
  const [curve, setCurve] = useState([])
  const [cached, setCached] = useState(false)
  const pollRef = useRef(null)

  useEffect(() => () => clearInterval(pollRef.current), [])

  const pollStatus = (jobId) => {
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getAnalysisStatus(jobId)
        setStep(s.step || '')
        if (s.status === 'done') {
          clearInterval(pollRef.current)
          setReport(s.result.report)
          setCurve(s.result.equity_curve || [])
          setStatus('done')
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
    setStatus('running'); setError(null); setReport(null); setCurve([]); setStep('Отправка запроса...')
    try {
      const res = await api.analyzeChannel(url.trim(), days)
      setCached(!!res.cached)
      if (res.cached) {
        setReport(res.report)
        setCurve(res.equity_curve || [])
        setStatus('done')
      } else {
        setStep('Анализирую историю...')
        pollStatus(res.job_id)
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
      `}</style>
    </div>
  )
}
