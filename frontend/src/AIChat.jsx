import { useState, useRef, useEffect } from 'react'
import { api } from './api'

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

const SUGGESTIONS = [
  'Почему сканер вошёл в эту сделку?',
  'Какие риски у текущего сигнала?',
  'Объясни стратегию сканера',
  'Покажи статистику за неделю',
  'Что такое ADX и зачем он нужен?',
  'Когда лучше не торговать?',
]

export default function AIChat() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '👋 Привет! Я AI-ассистент NWICKI. Могу объяснить текущий сигнал, риски, стратегию сканера или ответить на любой вопрос о торговле. Спрашивай!'
    }
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
      <div className="chat-header">
        <div className="chat-header-left">
          <div className="ai-avatar">AI</div>
          <div>
            <span className="chat-title">NWICKI AI</span>
            <span className="chat-sub">Знает текущие сигналы и рынок</span>
          </div>
        </div>
        <div className="chat-header-right">
          {quota && <span className="quota-text">{quota.used}/{quota.limit} сегодня</span>}
          <div className="ai-status">
            <span className="status-dot" />
            <span className="status-text">Online</span>
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
          placeholder="Спроси о сигнале, рисках, стратегии..."
          disabled={loading}
        />
        <button className="send-btn" onClick={() => sendMessage(input)} disabled={loading || !input.trim()}>
          ↑
        </button>
      </div>

      <style>{`
        .ai-chat {
          display: flex; flex-direction: column;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
          height: 600px; overflow: hidden;
        }
        .chat-header {
          padding: 16px 20px; border-bottom: 1px solid var(--border);
          display: flex; justify-content: space-between; align-items: center;
          flex-shrink: 0;
        }
        .chat-header-left { display: flex; align-items: center; gap: 12px; }
        .chat-header-right { display: flex; align-items: center; gap: 10px; }
        .ai-avatar {
          width: 38px; height: 38px; border-radius: 10px;
          background: linear-gradient(135deg, #10a37f, #1a7f64);
          display: flex; align-items: center; justify-content: center;
          color: #fff; font-size: 13px; font-weight: 700;
          box-shadow: 0 4px 12px rgba(16,163,127,0.3); flex-shrink: 0;
        }
        .chat-title { display: block; font-size: 15px; font-weight: 700; color: var(--text); }
        .chat-sub { display: block; font-size: 11px; color: var(--text-tertiary); }
        .ai-status { display: flex; align-items: center; gap: 6px; }
        .status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; }
        .status-text { font-size: 12px; color: var(--text-tertiary); }
        .quota-text { font-size: 11px; color: var(--text-tertiary); font-family: var(--font-mono); }

        .chat-messages {
          flex: 1; overflow-y: auto; padding: 20px;
          display: flex; flex-direction: column; gap: 16px;
        }
        .message { display: flex; gap: 10px; align-items: flex-start; }
        .message.user { flex-direction: row-reverse; }
        .msg-avatar {
          width: 30px; height: 30px; border-radius: 8px;
          background: linear-gradient(135deg, #10a37f, #1a7f64);
          display: flex; align-items: center; justify-content: center;
          color: #fff; font-size: 11px; font-weight: 700; flex-shrink: 0;
        }
        .msg-bubble {
          max-width: 75%; padding: 12px 16px;
          border-radius: 16px; font-size: 13px; line-height: 1.6; word-break: break-word;
        }
        .message.assistant .msg-bubble {
          background: var(--surface-hover); color: var(--text);
          border-radius: 4px 16px 16px 16px;
        }
        .message.user .msg-bubble {
          background: var(--accent); color: #fff;
          border-radius: 16px 4px 16px 16px;
        }
        /* markdown внутри ответов ассистента */
        .msg-bubble .md-p { margin: 0 0 8px; }
        .msg-bubble .md-p:last-child { margin-bottom: 0; }
        .msg-bubble .md-list { margin: 0 0 8px; padding-left: 20px; display: flex; flex-direction: column; gap: 4px; }
        .msg-bubble .md-list:last-child { margin-bottom: 0; }
        .msg-bubble .md-list li { line-height: 1.5; }
        .msg-bubble strong { font-weight: 700; }
        .msg-bubble .md-code {
          font-family: var(--font-mono); font-size: 12px;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 5px; padding: 1px 5px;
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
          border: 1px solid var(--border); background: var(--surface-hover);
          color: var(--text-secondary); font-size: 12px;
          padding: 7px 12px; border-radius: 20px; transition: all 0.15s; text-align: left;
        }
        .suggestion-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
        .chat-input-wrap {
          padding: 12px 16px; border-top: 1px solid var(--border);
          display: flex; gap: 10px; align-items: center; flex-shrink: 0;
        }
        .chat-input {
          flex: 1; padding: 11px 16px;
          background: var(--surface-hover); border: 1px solid var(--border);
          border-radius: 24px; color: var(--text);
          font-family: var(--font-ui); font-size: 14px; outline: none;
          transition: border-color 0.15s;
        }
        .chat-input:focus { border-color: var(--accent); }
        .chat-input::placeholder { color: var(--text-tertiary); }
        .send-btn {
          width: 38px; height: 38px; border-radius: 50%;
          background: var(--accent); border: none; color: #fff;
          font-size: 18px; display: flex; align-items: center; justify-content: center;
          transition: opacity 0.15s, transform 0.15s; flex-shrink: 0;
        }
        .send-btn:hover:not(:disabled) { opacity: 0.85; transform: scale(1.05); }
        .send-btn:disabled { opacity: 0.4; }
      `}</style>
    </div>
  )
}
