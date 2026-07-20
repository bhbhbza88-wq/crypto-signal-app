import { useCallback, useRef, useState } from 'react'
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

export default function ChartAnalyze({ user, onNeedAuth }) {
  const { t, lang } = useI18n()
  const inputRef = useRef(null)
  const [preview, setPreview] = useState(null)
  const [payload, setPayload] = useState(null)
  const [symbol, setSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('')
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
        symbol_hint: symbol.trim() || undefined,
        timeframe_hint: timeframe.trim() || undefined,
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

          <div className="ca-fields">
            <label>
              <span>{t('chart.symbol')}</span>
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                placeholder="BTCUSDT"
                maxLength={32}
              />
            </label>
            <label>
              <span>{t('chart.tf')}</span>
              <input
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                placeholder="15m / 1h / 4h"
                maxLength={16}
              />
            </label>
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

      <style>{`
        .ca-page { max-width: 1100px; }
        .ca-lead { color: var(--text-secondary); font-size: 14px; line-height: 1.5; margin: 0 0 18px; max-width: 62ch; }
        .ca-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        @media (max-width: 900px) { .ca-grid { grid-template-columns: 1fr; } }
        .ca-panel {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 16px; padding: 16px; box-shadow: var(--shadow-card);
        }
        .ca-drop {
          border: 1px dashed color-mix(in srgb, var(--accent) 35%, var(--border));
          border-radius: 14px; min-height: 220px; cursor: pointer;
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
        .ca-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
        .ca-fields label, .ca-q {
          display: flex; flex-direction: column; gap: 6px;
          font-size: 11px; font-weight: 700; letter-spacing: .04em;
          text-transform: uppercase; color: var(--text-tertiary);
        }
        .ca-fields input, .ca-q textarea {
          border: 1px solid var(--border); background: var(--surface-2); color: var(--text);
          border-radius: 10px; padding: 10px 12px; font-size: 13px; font-weight: 500;
          text-transform: none; letter-spacing: 0; font-family: inherit;
        }
        .ca-q { margin-top: 10px; }
        .ca-q textarea { resize: vertical; min-height: 64px; }
        .ca-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 14px; }
        .ca-run { min-width: 140px; }
        .ca-clear {
          border: 1px solid var(--border); background: transparent; color: var(--text-secondary);
          border-radius: 10px; padding: 10px 14px; cursor: pointer; font-size: 13px; font-weight: 600;
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
          margin: 0 0 14px; padding: 14px 16px; border-radius: 14px;
          border: 1px solid var(--border);
          background: color-mix(in srgb, var(--surface-2) 80%, transparent);
        }
        .ca-take.long {
          border-color: color-mix(in srgb, var(--green, #3dcc8a) 40%, var(--border));
          background: color-mix(in srgb, var(--green, #3dcc8a) 10%, var(--surface));
        }
        .ca-take.short {
          border-color: color-mix(in srgb, var(--danger, #e25) 40%, var(--border));
          background: color-mix(in srgb, var(--danger, #e25) 10%, var(--surface));
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
        .ca-bias.long { color: var(--green, #3dcc8a); border-color: color-mix(in srgb, var(--green, #3dcc8a) 40%, var(--border)); }
        .ca-bias.short { color: var(--danger, #e25); border-color: color-mix(in srgb, var(--danger, #e25) 40%, var(--border)); }
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
      `}</style>
    </div>
  )
}
