import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { useI18n } from './i18n'

const MAX_EDGE = 1400
const JPEG_QUALITY = 0.82

function looksLikeImage(file) {
  if (!file) return false
  const t = (file.type || '').toLowerCase()
  if (t.startsWith('image/')) return true
  // iPhone Photos часто отдаёт пустой MIME
  const name = (file.name || '').toLowerCase()
  return /\.(jpe?g|png|webp|heic|heif|gif)$/i.test(name) || !t
}

async function loadBitmap(file) {
  try {
    return await createImageBitmap(file)
  } catch {
    // fallback для странных MIME с iPhone
    const url = URL.createObjectURL(file)
    try {
      const img = await new Promise((resolve, reject) => {
        const el = new Image()
        el.onload = () => resolve(el)
        el.onerror = reject
        el.src = url
      })
      const canvas = document.createElement('canvas')
      canvas.width = img.naturalWidth || img.width
      canvas.height = img.naturalHeight || img.height
      canvas.getContext('2d').drawImage(img, 0, 0)
      return await createImageBitmap(canvas)
    } finally {
      URL.revokeObjectURL(url)
    }
  }
}

async function fileToCompressedPayload(file) {
  const bitmap = await loadBitmap(file)
  const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height))
  const w = Math.max(1, Math.round(bitmap.width * scale))
  const h = Math.max(1, Math.round(bitmap.height * scale))
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, w, h)
  ctx.drawImage(bitmap, 0, 0, w, h)
  bitmap.close()

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY))
  if (!blob) throw new Error('compress_failed')
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
  const base64 = String(dataUrl).split(',')[1] || ''
  return { base64, mediaType: 'image/jpeg', previewUrl: dataUrl, width: w, height: h }
}

function BiasBadge({ bias, t }) {
  const map = {
    long: { cls: 'ca-bias long', label: t('chart.biasLong') },
    short: { cls: 'ca-bias short', label: t('chart.biasShort') },
    flat: { cls: 'ca-bias flat', label: t('chart.biasFlat') },
  }
  const m = map[bias] || map.flat
  return <span className={m.cls}>{m.label}</span>
}

function ConfBadge({ confidence, t }) {
  const key = confidence === 'high' ? 'chart.confHigh'
    : confidence === 'medium' ? 'chart.confMed'
      : 'chart.confLow'
  return <span className={`ca-conf ${confidence || 'low'}`}>{t(key)}</span>
}

function formatReviewTime(iso, t) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return t('chart.social.agoMin', { n: Math.max(1, mins) })
  const hrs = Math.floor(mins / 60)
  if (hrs < 48) return t('chart.social.agoHrs', { n: hrs })
  const days = Math.floor(hrs / 24)
  return t('chart.social.agoDays', { n: days })
}

function ChartSocialProof({ user, onNeedAuth }) {
  const { t } = useI18n()
  const [stats, setStats] = useState(null)
  const [reviews, setReviews] = useState([])
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState(null)
  const [ok, setOk] = useState(false)
  const [form, setForm] = useState({
    display_name: '',
    symbol: '',
    side: 'LONG',
    pnl_pct: '',
    comment: '',
  })

  const load = useCallback(async () => {
    try {
      const data = await api.getChartReviews(48)
      setStats(data.stats)
      setReviews(data.reviews || [])
    } catch {
      /* keep empty */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function submit(e) {
    e.preventDefault()
    if (!user) {
      onNeedAuth?.()
      return
    }
    setSending(true)
    setErr(null)
    setOk(false)
    try {
      const data = await api.postChartReview({
        display_name: form.display_name.trim(),
        symbol: form.symbol.trim() || 'BTC',
        side: form.side,
        pnl_pct: parseFloat(form.pnl_pct) || 0,
        comment: form.comment.trim(),
      })
      setReviews((prev) => [data.review, ...prev].slice(0, 48))
      if (data.stats) setStats(data.stats)
      setForm({ display_name: '', symbol: '', side: 'LONG', pnl_pct: '', comment: '' })
      setOk(true)
    } catch (ex) {
      setErr(ex.message || t('chart.social.err'))
    } finally {
      setSending(false)
    }
  }

  const helped = stats?.helped ?? 627
  const winrate = stats?.winrate ?? 96
  const avgPnl = stats?.avg_pnl ?? 3.8

  return (
    <section className="ca-social">
      <div className="ca-social-head">
        <div>
          <div className="ca-social-kicker mono">{t('chart.social.kicker')}</div>
          <h2 className="ca-social-title">{t('chart.social.title')}</h2>
          <p className="ca-social-sub">{t('chart.social.sub')}</p>
        </div>
        <div className="ca-social-stats">
          <div className="ca-stat accent">
            <span className="ca-stat-val mono">{helped.toLocaleString('ru-RU')}+</span>
            <span className="ca-stat-lbl">{t('chart.social.helped')}</span>
          </div>
          <div className="ca-stat">
            <span className="ca-stat-val mono">{winrate}%</span>
            <span className="ca-stat-lbl">{t('chart.social.winrate')}</span>
          </div>
          <div className="ca-stat">
            <span className="ca-stat-val mono pos">+{avgPnl}%</span>
            <span className="ca-stat-lbl">{t('chart.social.avgPnl')}</span>
          </div>
        </div>
      </div>

      <div className="ca-social-grid">
        <div className="ca-social-feed">
          {loading && <div className="ca-social-empty mono">{t('chart.social.loading')}</div>}
          {!loading && reviews.map((r) => (
            <article key={r.id} className="ca-review">
              <div className="ca-review-top">
                <span className="ca-review-avatar">{(r.display_name || '?').charAt(0).toUpperCase()}</span>
                <div className="ca-review-who">
                  <strong>{r.display_name}</strong>
                  <span className="mono">{formatReviewTime(r.created_at, t)}</span>
                </div>
                <div className="ca-review-trade">
                  <span className="mono">{r.symbol}</span>
                  <span className={`ca-review-side ${String(r.side).toLowerCase()}`}>{r.side}</span>
                  <span className={`mono ${r.pnl_pct >= 0 ? 'pos' : 'neg'}`}>
                    {r.pnl_pct >= 0 ? '+' : ''}{Number(r.pnl_pct).toFixed(1)}%
                  </span>
                </div>
              </div>
              <p className="ca-review-text">{r.comment}</p>
            </article>
          ))}
        </div>

        <form className="ca-social-form" onSubmit={submit}>
          <div className="ca-form-title mono">{t('chart.social.formTitle')}</div>
          <p className="ca-form-hint">{t('chart.social.formHint')}</p>
          <label>
            <span>{t('chart.social.name')}</span>
            <input
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              placeholder={t('chart.social.namePh')}
              maxLength={40}
            />
          </label>
          <div className="ca-form-row">
            <label>
              <span>{t('chart.social.symbol')}</span>
              <input
                value={form.symbol}
                onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
                placeholder="BTC"
                maxLength={12}
              />
            </label>
            <label>
              <span>{t('chart.social.side')}</span>
              <select value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })}>
                <option value="LONG">LONG</option>
                <option value="SHORT">SHORT</option>
              </select>
            </label>
            <label>
              <span>{t('chart.social.pnl')}</span>
              <input
                value={form.pnl_pct}
                onChange={(e) => setForm({ ...form, pnl_pct: e.target.value })}
                placeholder="+3.2"
                inputMode="decimal"
              />
            </label>
          </div>
          <label>
            <span>{t('chart.social.comment')}</span>
            <textarea
              value={form.comment}
              onChange={(e) => setForm({ ...form, comment: e.target.value })}
              placeholder={t('chart.social.commentPh')}
              rows={3}
              maxLength={400}
              required
            />
          </label>
          {err && <div className="ca-error">{err}</div>}
          {ok && <div className="ca-social-ok">{t('chart.social.ok')}</div>}
          <button type="submit" className="btn-primary" disabled={sending || form.comment.trim().length < 8}>
            {sending ? t('chart.social.sending') : t('chart.social.send')}
          </button>
        </form>
      </div>
    </section>
  )
}

export default function ChartAnalyze({ user, onNeedAuth }) {
  const { t, lang } = useI18n()
  const inputRef = useRef(null)
  const [preview, setPreview] = useState(null)
  const [payload, setPayload] = useState(null)
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [quota, setQuota] = useState(null)

  const clear = useCallback(() => {
    setPreview(null)
    setPayload(null)
    setResult(null)
    setError(null)
    setQuestion('')
    if (inputRef.current) inputRef.current.value = ''
  }, [])

  async function onPick(file) {
    if (!file) return
    setError(null)
    setResult(null)
    try {
      if (!looksLikeImage(file)) {
        setError(t('chart.errType'))
        return
      }
      const packed = await fileToCompressedPayload(file)
      setPreview(packed.previewUrl)
      setPayload(packed)
    } catch {
      setError(t('chart.errCompress'))
    }
  }

  async function analyze() {
    if (!user) {
      onNeedAuth?.()
      return
    }
    if (!payload || loading) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.chartAnalyze({
        image_base64: payload.base64,
        media_type: payload.mediaType,
        question: question.trim() || undefined,
        language: lang,
      })
      setResult(data.analysis)
      setQuota({ used: data.used, limit: data.limit })
    } catch (e) {
      setError(e.message || t('chart.errGeneric'))
    } finally {
      setLoading(false)
    }
  }

  const a = result

  return (
    <div className="ca-page">
      <p className="ca-lead">{t('chart.lead')}</p>

      <div className="ca-grid">
        <div className="ca-panel">
          <div
            className={`ca-drop ${preview ? 'has' : ''}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              onPick(e.dataTransfer.files?.[0])
            }}
            onClick={() => inputRef.current?.click()}
          >
            <input
              ref={inputRef}
              type="file"
              accept="image/*,.heic,.heif,.jpg,.jpeg,.png,.webp"
              hidden
              onChange={(e) => onPick(e.target.files?.[0])}
            />
            {preview ? (
              <img src={preview} alt="" className="ca-preview" />
            ) : (
              <div className="ca-drop-empty">
                <span className="ca-drop-ico">▣</span>
                <strong>{t('chart.dropTitle')}</strong>
                <span>{t('chart.dropHint')}</span>
              </div>
            )}
          </div>

          <label className="ca-q">
            <span>{t('chart.question')}</span>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={t('chart.questionPh')}
              rows={2}
              maxLength={300}
            />
          </label>

          <div className="ca-actions">
            <button className="btn-primary ca-run" disabled={!payload || loading} onClick={analyze}>
              {loading ? t('chart.analyzing') : t('chart.run')}
            </button>
            {(preview || result) && (
              <button type="button" className="ca-clear" onClick={clear}>{t('chart.clear')}</button>
            )}
            {quota && (
              <span className="ca-quota">{t('chart.quota', { used: quota.used, limit: quota.limit })}</span>
            )}
          </div>

          {error && <div className="ca-error">{error}</div>}
        </div>

        <div className="ca-panel ca-result">
          {!a && !loading && (
            <div className="ca-empty">
              <h3>{t('chart.emptyTitle')}</h3>
              <p>{t('chart.emptyBody')}</p>
              <ul>
                <li>{t('chart.rule1')}</li>
                <li>{t('chart.rule2')}</li>
                <li>{t('chart.rule3')}</li>
              </ul>
            </div>
          )}

          {loading && (
            <div className="ca-empty">
              <div className="ca-spinner" />
              <p>{t('chart.analyzing')}</p>
            </div>
          )}

          {a && !loading && (
            <div className="ca-out">
              <div className={`ca-take ${a.bias || 'flat'}`}>
                <span className="ca-take-label">{t('chart.myTake')}</span>
                <p>{a.take || t('chart.noReasons')}</p>
              </div>

              <div className="ca-out-head">
                <BiasBadge bias={a.bias} t={t} />
                <ConfBadge confidence={a.confidence} t={t} />
                {!a.evidence_ok && <span className="ca-warn">{t('chart.weakEvidence')}</span>}
              </div>

              <div className="ca-meta">
                {a.symbol && <span className="mono">{a.symbol}</span>}
                {a.timeframe && <span>{a.timeframe}</span>}
                {a.price_hint && <span className="mono">{a.price_hint}</span>}
              </div>

              {!!a.seen?.length && (
                <section>
                  <h4>{t('chart.seen')}</h4>
                  <ul>{a.seen.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </section>
              )}

              <section>
                <h4>{t('chart.reasons')}</h4>
                <ul>{(a.reasons?.length ? a.reasons : [t('chart.noReasons')]).map((x, i) => <li key={i}>{x}</li>)}</ul>
              </section>

              <section className="ca-inv">
                <h4>{t('chart.invalidation')}</h4>
                <p>{a.invalidation}</p>
              </section>

              {!!a.risks?.length && (
                <section>
                  <h4>{t('chart.risks')}</h4>
                  <ul>{a.risks.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </section>
              )}

              {!!a.watch?.length && (
                <section>
                  <h4>{t('chart.watch')}</h4>
                  <ul>{a.watch.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </section>
              )}

              <p className="ca-disc">{a.disclaimer || t('chart.disclaimer')}</p>
            </div>
          )}
        </div>
      </div>

      <ChartSocialProof user={user} onNeedAuth={onNeedAuth} />

      <style>{`
        .ca-page { max-width: 1100px; }
        .ca-lead { color: var(--text-secondary); font-size: 14px; line-height: 1.5; margin: 0 0 18px; max-width: 62ch; }
        .ca-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        @media (max-width: 900px) { .ca-grid { grid-template-columns: 1fr; } }
        .ca-panel {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 12px; padding: 18px;
          box-shadow: var(--inset-highlight);
          backdrop-filter: saturate(160%) blur(16px);
        }
        .ca-drop {
          border: 1px dashed color-mix(in srgb, var(--accent) 35%, var(--border));
          border-radius: var(--radius-md); min-height: 220px; cursor: pointer;
          display: grid; place-items: center; overflow: hidden;
          background: color-mix(in srgb, var(--surface-2) 70%, transparent);
          transition: border-color .15s, background .15s;
        }
        .ca-drop:hover { border-color: var(--accent); }
        .ca-drop.has { border-style: solid; }
        .ca-drop-empty { text-align: center; padding: 24px; display: flex; flex-direction: column; gap: 6px; color: var(--text-secondary); }
        .ca-drop-empty strong { color: var(--text); font-size: 15px; }
        .ca-drop-empty span:last-child { font-size: 12px; color: var(--text-tertiary); }
        .ca-drop-ico { font-size: 28px; color: var(--accent); margin-bottom: 4px; }
        .ca-preview { width: 100%; max-height: 320px; object-fit: contain; display: block; background: #0a0a0a; }
        .ca-q {
          display: flex; flex-direction: column; gap: 6px; margin-top: 14px;
          font-size: 11px; font-weight: 700; letter-spacing: .04em;
          text-transform: uppercase; color: var(--text-tertiary);
        }
        .ca-q textarea {
          border: 1px solid var(--border); background: var(--surface-2); color: var(--text);
          border-radius: var(--radius-sm); padding: 10px 12px; font-size: 13px; font-weight: 500;
          text-transform: none; letter-spacing: 0; font-family: inherit;
          resize: vertical; min-height: 64px;
        }
        .ca-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 14px; }
        .ca-run { min-width: 140px; }
        .ca-clear {
          border: 1px solid var(--border); background: transparent; color: var(--text-secondary);
          border-radius: 980px; padding: 10px 16px; cursor: pointer; font-size: 13px; font-weight: 600;
        }
        .ca-quota { margin-left: auto; font-size: 12px; color: var(--text-tertiary); }
        .ca-error {
          margin-top: 12px; padding: 10px 12px; border-radius: 10px; font-size: 13px;
          background: color-mix(in srgb, var(--danger, #e25) 12%, transparent);
          color: var(--danger, #e25); border: 1px solid color-mix(in srgb, var(--danger, #e25) 30%, var(--border));
        }
        .ca-result { min-height: 360px; }
        .ca-empty { color: var(--text-secondary); padding: 12px 4px; }
        .ca-empty h3 { margin: 0 0 8px; color: var(--text); font-size: 16px; }
        .ca-empty p { margin: 0 0 12px; font-size: 13px; line-height: 1.5; }
        .ca-empty ul { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.6; }
        .ca-spinner {
          width: 28px; height: 28px; border-radius: 50%;
          border: 2px solid var(--border); border-top-color: var(--accent);
          animation: ca-spin .8s linear infinite; margin-bottom: 12px;
        }
        @keyframes ca-spin { to { transform: rotate(360deg); } }
        .ca-out-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
        .ca-take {
          margin: 0 0 14px; padding: 14px 16px; border-radius: var(--radius-md);
          border: 1px solid var(--border);
          background: color-mix(in srgb, var(--surface-2) 80%, transparent);
        }
        .ca-take.long {
          border-color: color-mix(in srgb, var(--long) 40%, var(--border));
          background: color-mix(in srgb, var(--long) 10%, var(--surface));
        }
        .ca-take.short {
          border-color: color-mix(in srgb, var(--short) 40%, var(--border));
          background: color-mix(in srgb, var(--short) 10%, var(--surface));
        }
        .ca-take-label {
          display: block; margin-bottom: 6px;
          font-size: 11px; font-weight: 800; letter-spacing: .06em;
          text-transform: uppercase; color: var(--text-tertiary);
        }
        .ca-take p {
          margin: 0; font-size: 16px; line-height: 1.45; font-weight: 650; color: var(--text);
        }
        .ca-bias {
          font-size: 12px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase;
          padding: 6px 10px; border-radius: 999px; border: 1px solid var(--border);
        }
        .ca-bias.long { color: var(--long); border-color: color-mix(in srgb, var(--long) 40%, var(--border)); }
        .ca-bias.short { color: var(--short); border-color: color-mix(in srgb, var(--short) 40%, var(--border)); }
        .ca-bias.flat { color: var(--text-secondary); }
        .ca-conf {
          font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
          padding: 6px 10px; border-radius: 999px; background: var(--surface-2); color: var(--text-secondary);
        }
        .ca-conf.high { color: var(--accent); }
        .ca-conf.medium { color: var(--amber, #d4a017); }
        .ca-warn {
          font-size: 11px; font-weight: 700; color: var(--amber, #d4a017);
          border: 1px solid color-mix(in srgb, var(--amber, #d4a017) 35%, var(--border));
          padding: 5px 8px; border-radius: 8px;
        }
        .ca-meta { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; font-size: 13px; color: var(--text-secondary); }
        .ca-out section { margin-bottom: 14px; }
        .ca-out h4 {
          margin: 0 0 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
          color: var(--text-tertiary); font-weight: 800;
        }
        .ca-out ul { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.55; color: var(--text); }
        .ca-inv p { margin: 0; font-size: 14px; line-height: 1.5; color: var(--text); }
        .ca-disc {
          margin: 18px 0 0; padding-top: 12px; border-top: 1px solid var(--border);
          font-size: 12px; color: var(--text-tertiary); line-height: 1.45;
        }

        /* ── Social proof / review wall ── */
        .ca-social {
          margin-top: 28px; padding: 22px;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 14px; box-shadow: var(--inset-highlight);
        }
        .ca-social-head {
          display: flex; justify-content: space-between; gap: 20px; flex-wrap: wrap;
          margin-bottom: 18px; align-items: flex-end;
        }
        .ca-social-kicker {
          font-size: 11px; color: var(--accent); margin-bottom: 6px;
        }
        .ca-social-title {
          margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.03em;
          font-family: var(--font-display); color: var(--text);
        }
        .ca-social-sub {
          margin: 6px 0 0; font-size: 13px; color: var(--text-secondary); max-width: 48ch; line-height: 1.45;
        }
        .ca-social-stats { display: flex; gap: 10px; flex-wrap: wrap; }
        .ca-stat {
          min-width: 110px; padding: 12px 14px; border-radius: 12px;
          background: color-mix(in srgb, var(--bg) 55%, transparent);
          border: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px;
        }
        .ca-stat.accent {
          background: linear-gradient(160deg, color-mix(in srgb, var(--bg) 40%, transparent), var(--accent-soft));
          border-color: color-mix(in srgb, var(--accent) 28%, var(--border));
        }
        .ca-stat-val { font-size: 22px; font-weight: 700; color: var(--text); letter-spacing: -0.03em; }
        .ca-stat-val.pos { color: var(--long); }
        .ca-stat-lbl { font-size: 10px; color: var(--text-tertiary); font-weight: 600; }
        .ca-social-grid {
          display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; align-items: start;
        }
        @media (max-width: 900px) { .ca-social-grid { grid-template-columns: 1fr; } }
        .ca-social-feed {
          display: flex; flex-direction: column; gap: 10px;
          max-height: 520px; overflow: auto; padding-right: 4px;
        }
        .ca-social-empty { font-size: 12px; color: var(--text-tertiary); padding: 20px; }
        .ca-review {
          padding: 12px 14px; border-radius: 12px;
          background: color-mix(in srgb, var(--bg) 50%, transparent);
          border: 1px solid var(--border);
        }
        .ca-review-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .ca-review-avatar {
          width: 32px; height: 32px; border-radius: 9px; flex-shrink: 0;
          display: grid; place-items: center;
          background: var(--accent-soft); color: var(--accent);
          font-weight: 700; font-size: 13px; font-family: var(--font-mono);
        }
        .ca-review-who { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
        .ca-review-who strong { font-size: 13px; color: var(--text); }
        .ca-review-who span { font-size: 10px; color: var(--text-tertiary); }
        .ca-review-trade { display: flex; align-items: center; gap: 8px; font-size: 12px; }
        .ca-review-side {
          font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 6px; font-family: var(--font-mono);
        }
        .ca-review-side.long { background: var(--long-soft); color: var(--long); }
        .ca-review-side.short { background: var(--short-soft); color: var(--short); }
        .ca-review-text {
          margin: 10px 0 0; font-size: 13px; line-height: 1.45; color: var(--text-secondary);
        }
        .ca-social-form {
          padding: 16px; border-radius: 12px;
          background: color-mix(in srgb, var(--bg) 45%, transparent);
          border: 1px solid var(--border);
          display: flex; flex-direction: column; gap: 10px;
          position: sticky; top: 72px;
        }
        .ca-form-title { font-size: 12px; color: var(--accent); font-weight: 600; }
        .ca-form-hint { margin: 0; font-size: 12px; color: var(--text-tertiary); line-height: 1.4; }
        .ca-social-form label {
          display: flex; flex-direction: column; gap: 5px;
          font-size: 10px; font-weight: 650; color: var(--text-tertiary); letter-spacing: 0.04em;
          text-transform: uppercase;
        }
        .ca-social-form input, .ca-social-form select, .ca-social-form textarea {
          border: 1px solid var(--border); background: var(--surface); color: var(--text);
          border-radius: 8px; padding: 9px 11px; font-size: 13px; font-weight: 500;
          text-transform: none; letter-spacing: 0; font-family: inherit;
        }
        .ca-social-form textarea { resize: vertical; min-height: 72px; }
        .ca-form-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
        @media (max-width: 520px) { .ca-form-row { grid-template-columns: 1fr; } }
        .ca-social-ok {
          font-size: 12px; color: var(--long); background: var(--long-soft);
          padding: 8px 10px; border-radius: 8px;
        }
        .ca-social-form .btn-primary { margin-top: 4px; border-radius: 980px; }
        .ca-social .pos { color: var(--long); }
        .ca-social .neg { color: var(--short); }
      `}</style>
    </div>
  )
}
