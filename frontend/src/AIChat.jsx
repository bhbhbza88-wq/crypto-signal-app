import { useState, useRef, useEffect, useMemo } from 'react'
import { api } from './api'
import { useI18n } from './i18n'

// Инлайновый markdown: **жирный** и `код`. Возвращает массив React-узлов.
function renderInline(text, keyPrefix) {
  const parts = []
  const regex = /(\*\*[^*]+\*\*|`[^`]+`)/g
  let last = 0, m, i = 0
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**')) parts.push(<strong key={`${keyPrefix}-b${i}`}>{tok.slice(2, -2)}</strong>)
    else parts.push(<code key={`${keyPrefix}-c${i}`} className="md-code">{tok.slice(1, -1)}</code>)
    last = m.index + tok.length
    i++
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

// Блочный markdown: абзацы, маркированные и нумерованные списки, заголовки.
function MarkdownMessage({ content }) {
  const lines = content.split('\n')
  const blocks = []
  let list = null   // { type: 'ul'|'ol', items: [] }
  const flush = () => { if (list) { blocks.push(list); list = null } }

  lines.forEach((raw) => {
    const line = raw.trimEnd()
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/)
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/)
    if (bullet) {
      if (!list || list.type !== 'ul') { flush(); list = { type: 'ul', items: [] } }
      list.items.push(bullet[1])
    } else if (numbered) {
      if (!list || list.type !== 'ol') { flush(); list = { type: 'ol', items: [] } }
      list.items.push(numbered[1])
    } else {
      flush()
      if (line.trim()) blocks.push({ type: 'p', text: line.replace(/^#+\s*/, '') })
    }
  })
  flush()

  return (
    <>
      {blocks.map((b, i) => {
        if (b.type === 'p') return <p key={i} className="md-p">{renderInline(b.text, `p${i}`)}</p>
        const Tag = b.type === 'ol' ? 'ol' : 'ul'
        return (
          <Tag key={i} className="md-list">
            {b.items.map((it, j) => <li key={j}>{renderInline(it, `l${i}-${j}`)}</li>)}
          </Tag>
        )
      })}
    </>
  )
}

export default function AIChat() {
  const { t, lang } = useI18n()
  const SUGGESTIONS = useMemo(() => [
    t('ai.chip1'), t('ai.chip2'), t('ai.chip3'), t('ai.chip4'), t('ai.chip5'), t('ai.chip6'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [lang])

  const [messages, setMessages] = useState([
    { role: 'assistant', content: t('ai.greeting') }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [quota, setQuota] = useState(null)   // {used, limit} с бэкенда
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage(text) {
    if (!text.trim() || loading) return

    const userMsg = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      // Системный контекст (цены, скринер, сигналы, фаза) строит бэкенд из реальных данных.
      const data = await api.aiChat([
        ...messages.filter(m => m.role !== 'system').map(m => ({ role: m.role, content: m.content })),
        userMsg,
      ])
      setQuota({ used: data.used, limit: data.limit })
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `❌ ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="ai-chat">
      <div className="chat-titlebar">
        <div className="traffic-lights" aria-hidden="true">
          <span className="tl tl-close" />
          <span className="tl tl-min" />
          <span className="tl tl-max" />
        </div>
        <div className="chat-titlebar-center">
          <span className="chat-title">{t('ai.deskTitle')}</span>
          <span className="beta-pill">BETA</span>
        </div>
        <div className="chat-header-right">
          {quota && <span className="quota-text">{t('ai.quotaToday', { used: quota.used, limit: quota.limit })}</span>}
          <div className="ai-status">
            <span className="status-dot" />
            <span className="status-text">{t('ai.online')}</span>
          </div>
        </div>
      </div>

      <div className="chat-toolbar">
        <div className="chat-header-left">
          <div className="ai-avatar">AI</div>
          <div>
            <span className="chat-sub-title">{t('ai.title')}</span>
            <span className="chat-sub">{t('ai.deskSub')}</span>
          </div>
        </div>
      </div>

      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {msg.role === 'assistant' && <div className="msg-avatar">AI</div>}
            <div className="msg-bubble">
              {msg.role === 'assistant'
                ? <MarkdownMessage content={msg.content} />
                : msg.content.split('\n').map((line, j) => (
                    <span key={j}>{line}{j < msg.content.split('\n').length - 1 && <br />}</span>
                  ))}
            </div>
          </div>
        ))}
        {loading && (
          <div className="message assistant">
            <div className="msg-avatar">AI</div>
            <div className="msg-bubble typing">
              <span /><span /><span />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {messages.length <= 1 && (
        <div className="suggestions">
          {SUGGESTIONS.map((s, i) => (
            <button key={i} className="suggestion-btn" onClick={() => sendMessage(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="chat-input-wrap">
        <input
          className="chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage(input)}
          placeholder={t('ai.placeholder')}
          disabled={loading}
        />
        <button className="send-btn" onClick={() => sendMessage(input)} disabled={loading || !input.trim()}>
          ↑
        </button>
      </div>

      <style>{`
        .ai-chat {
          display: flex; flex-direction: column;
          height: 100%; width: 100%; min-height: 0;
          border-radius: 14px; overflow: hidden;
          background: color-mix(in srgb, var(--surface) 72%, transparent);
          border: 1px solid color-mix(in srgb, #fff 12%, var(--border));
          box-shadow:
            0 0 0 0.5px color-mix(in srgb, #000 25%, transparent),
            0 22px 48px rgba(0, 0, 0, 0.32),
            0 2px 6px rgba(0, 0, 0, 0.18),
            inset 0 1px 0 color-mix(in srgb, #fff 10%, transparent);
          backdrop-filter: saturate(160%) blur(28px);
          -webkit-backdrop-filter: saturate(160%) blur(28px);
        }

        .chat-titlebar {
          height: 44px; flex-shrink: 0;
          display: grid; grid-template-columns: 1fr auto 1fr;
          align-items: center; gap: 12px;
          padding: 0 14px;
          background: color-mix(in srgb, var(--surface-hover) 55%, transparent);
          border-bottom: 1px solid color-mix(in srgb, #fff 8%, var(--border));
        }
        .traffic-lights {
          display: flex; align-items: center; gap: 8px; justify-self: start;
        }
        .tl {
          width: 12px; height: 12px; border-radius: 50%;
          box-shadow: inset 0 0 0 0.5px rgba(0,0,0,0.18);
        }
        .tl-close { background: #ff5f57; }
        .tl-min { background: #febc2e; }
        .tl-max { background: #28c840; }
        .chat-titlebar-center {
          display: flex; align-items: center; gap: 8px; justify-self: center;
        }
        .chat-title {
          font-size: 13px; font-weight: 650; color: var(--text);
          font-family: var(--font-display); letter-spacing: -0.02em;
        }
        .beta-pill {
          font-size: 9px; font-weight: 800; letter-spacing: 0.06em;
          color: var(--accent); background: var(--accent-soft);
          border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
          padding: 2px 6px; border-radius: 999px;
        }
        .chat-header-right {
          display: flex; align-items: center; gap: 10px; justify-self: end;
        }
        .ai-status { display: flex; align-items: center; gap: 6px; }
        .status-dot {
          width: 7px; height: 7px; border-radius: 50%; background: var(--long);
          animation: pulse 2s infinite;
        }
        .status-text { font-size: 12px; color: var(--text-tertiary); }
        .quota-text { font-size: 11px; color: var(--text-tertiary); font-family: var(--font-mono); }

        .chat-toolbar {
          padding: 12px 18px; flex-shrink: 0;
          border-bottom: 1px solid color-mix(in srgb, #fff 6%, var(--border));
          background: color-mix(in srgb, var(--surface) 40%, transparent);
        }
        .chat-header-left { display: flex; align-items: center; gap: 12px; }
        .ai-avatar {
          width: 36px; height: 36px; border-radius: 10px;
          background: linear-gradient(145deg, var(--accent), color-mix(in srgb, var(--accent) 55%, #0a1f18));
          display: flex; align-items: center; justify-content: center;
          color: #fff; font-size: 11px; font-weight: 800;
          font-family: var(--font-display); flex-shrink: 0;
          box-shadow: 0 4px 12px color-mix(in srgb, var(--accent) 35%, transparent);
        }
        .chat-sub-title {
          display: block; font-size: 14px; font-weight: 700; color: var(--text);
          font-family: var(--font-display); letter-spacing: -0.02em;
        }
        .chat-sub { display: block; font-size: 12px; color: var(--text-tertiary); margin-top: 1px; }

        .chat-messages {
          flex: 1; overflow-y: auto; min-height: 0;
          padding: 22px 20px;
          display: flex; flex-direction: column; gap: 16px;
          background:
            radial-gradient(ellipse 60% 40% at 50% 0%, color-mix(in srgb, var(--accent) 6%, transparent), transparent 70%);
        }
        .message { display: flex; gap: 10px; align-items: flex-start; }
        .message.user { flex-direction: row-reverse; }
        .msg-avatar {
          width: 30px; height: 30px; border-radius: 9px;
          background: linear-gradient(145deg, var(--accent), color-mix(in srgb, var(--accent) 55%, #0a1f18));
          display: flex; align-items: center; justify-content: center;
          color: #fff; font-size: 10px; font-weight: 800; flex-shrink: 0;
          font-family: var(--font-display);
        }
        .msg-bubble {
          max-width: min(720px, 78%); padding: 12px 16px;
          border-radius: 18px; font-size: 13.5px; line-height: 1.6; word-break: break-word;
        }
        .message.assistant .msg-bubble {
          background: color-mix(in srgb, var(--surface-hover) 88%, transparent);
          color: var(--text);
          border: 1px solid color-mix(in srgb, #fff 6%, var(--border));
          border-radius: 6px 18px 18px 18px;
          box-shadow: 0 1px 2px rgba(0,0,0,0.08);
        }
        .message.user .msg-bubble {
          background: var(--accent); color: #fff;
          border-radius: 18px 6px 18px 18px;
          box-shadow: 0 6px 16px color-mix(in srgb, var(--accent) 28%, transparent);
        }
        .msg-bubble .md-p { margin: 0 0 8px; }
        .msg-bubble .md-p:last-child { margin-bottom: 0; }
        .msg-bubble .md-list { margin: 0 0 8px; padding-left: 20px; display: flex; flex-direction: column; gap: 4px; }
        .msg-bubble .md-list:last-child { margin-bottom: 0; }
        .msg-bubble .md-list li { line-height: 1.5; }
        .msg-bubble strong { font-weight: 700; }
        .msg-bubble .md-code {
          font-family: var(--font-mono); font-size: 12px;
          background: color-mix(in srgb, var(--surface) 80%, transparent);
          border: 1px solid var(--border);
          border-radius: 6px; padding: 1px 5px;
        }
        .typing { display: flex; gap: 5px; align-items: center; padding: 14px 18px; }
        .typing span {
          width: 7px; height: 7px; border-radius: 50%;
          background: var(--text-tertiary); animation: bounce 1.2s infinite;
        }
        .typing span:nth-child(2) { animation-delay: 0.2s; }
        .typing span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes bounce {
          0%,60%,100% { transform: translateY(0); }
          30% { transform: translateY(-6px); }
        }
        @keyframes pulse {
          0%   { box-shadow: 0 0 0 0 rgba(0,201,150,0.4); }
          70%  { box-shadow: 0 0 0 6px rgba(0,201,150,0); }
          100% { box-shadow: 0 0 0 0 rgba(0,201,150,0); }
        }

        .suggestions {
          padding: 0 16px 12px; display: flex; flex-wrap: wrap; gap: 8px; flex-shrink: 0;
        }
        .suggestion-btn {
          border: 1px solid color-mix(in srgb, #fff 8%, var(--border));
          background: color-mix(in srgb, var(--surface-hover) 70%, transparent);
          color: var(--text-secondary); font-size: 12px;
          padding: 8px 13px; border-radius: 14px; transition: all 0.15s; text-align: left;
          backdrop-filter: blur(8px);
        }
        .suggestion-btn:hover {
          border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
          color: var(--accent); background: var(--accent-soft);
        }

        .chat-input-wrap {
          padding: 14px 16px 16px;
          border-top: 1px solid color-mix(in srgb, #fff 8%, var(--border));
          display: flex; gap: 10px; align-items: center; flex-shrink: 0;
          background: color-mix(in srgb, var(--surface-hover) 45%, transparent);
        }
        .chat-input {
          flex: 1; padding: 12px 16px;
          background: color-mix(in srgb, var(--bg) 55%, var(--surface));
          border: 1px solid color-mix(in srgb, #fff 10%, var(--border));
          border-radius: 14px; color: var(--text);
          font-family: var(--font-ui); font-size: 14px; outline: none;
          transition: border-color 0.15s, box-shadow 0.15s;
          box-shadow: inset 0 1px 2px rgba(0,0,0,0.12);
        }
        .chat-input:focus {
          border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
          box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
        }
        .chat-input::placeholder { color: var(--text-tertiary); }
        .send-btn {
          width: 40px; height: 40px; border-radius: 12px;
          background: var(--accent); border: none; color: #fff;
          font-size: 18px; display: flex; align-items: center; justify-content: center;
          transition: opacity 0.15s, transform 0.15s; flex-shrink: 0;
          box-shadow: 0 6px 14px color-mix(in srgb, var(--accent) 30%, transparent);
        }
        .send-btn:hover:not(:disabled) { opacity: 0.9; transform: scale(1.04); }
        .send-btn:disabled { opacity: 0.4; box-shadow: none; }

        @media (max-width: 720px) {
          .chat-titlebar { grid-template-columns: auto 1fr auto; }
          .chat-sub { display: none; }
          .msg-bubble { max-width: 88%; }
          .quota-text { display: none; }
        }
      `}</style>
    </div>
  )
}
