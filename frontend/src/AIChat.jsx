import { useState, useRef, useEffect } from 'react'
import { api } from './api'
import { useI18n } from './i18n'

function stripMd(text) {
  return String(text || '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^#+\s*/gm, '')
    .replace(/^\s*[-*•]\s+/gm, '  • ')
}

function TermBlock({ role, content, streaming }) {
  const lines = stripMd(content || ' ').split('\n')
  const prompt = role === 'user' ? 'you@nowicki ~ %' : 'nick@desk ~ %'
  const tone = role === 'user' ? 'user' : 'asst'

  return (
    <div className={`term-block ${tone}`}>
      {lines.map((line, i) => (
        <div key={i} className="term-line">
          <span className="term-gutter">
            {i === 0 ? <span className="term-prompt">{prompt} </span> : null}
          </span>
          <span className="term-text">
            {line || ' '}
            {streaming && i === lines.length - 1 ? <span className="term-cursor blink">█</span> : null}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function AIChat() {
  const { t } = useI18n()
  const [messages, setMessages] = useState([
    { role: 'assistant', content: t('ai.greeting') }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [quota, setQuota] = useState(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, streaming])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  function appendAssistant(chunk) {
    setMessages(prev => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (!last || last.role !== 'assistant') {
        return [...prev, { role: 'assistant', content: chunk }]
      }
      next[next.length - 1] = { ...last, content: last.content + chunk }
      return next
    })
  }

  async function sendMessage(text) {
    if (!text.trim() || loading) return

    const userMsg = { role: 'user', content: text }
    const history = [
      ...messages.filter(m => m.role !== 'system').map(m => ({ role: m.role, content: m.content })),
      userMsg,
    ]
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setStreaming(false)

    let gotToken = false

    try {
      await api.aiChatStream(history, {
        onToken: (token) => {
          if (!gotToken) {
            gotToken = true
            setStreaming(true)
            setMessages(prev => [...prev, { role: 'assistant', content: token }])
          } else {
            appendAssistant(token)
          }
        },
        onDone: ({ used, limit }) => {
          if (used != null) setQuota({ used, limit })
        },
      })

      if (!gotToken) {
        const data = await api.aiChat(history)
        setQuota({ used: data.used, limit: data.limit })
        const reply = data.reply || ''
        setStreaming(true)
        // мягкий набор при fallback (без стрима)
        let acc = ''
        setMessages(prev => [...prev, { role: 'assistant', content: '' }])
        for (const ch of reply) {
          acc += ch
          const snap = acc
          setMessages(prev => {
            const next = [...prev]
            next[next.length - 1] = { role: 'assistant', content: snap }
            return next
          })
          if (ch !== ' ') await new Promise(r => setTimeout(r, 4))
        }
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `error: ${e.message}` }])
    } finally {
      setStreaming(false)
      setLoading(false)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }

  const waiting = loading && !streaming && messages[messages.length - 1]?.role === 'user'

  return (
    <div className="ai-chat term-window" onClick={() => inputRef.current?.focus()}>
      <div className="chat-titlebar">
        <div className="traffic-lights" aria-hidden="true">
          <span className="tl tl-close" />
          <span className="tl tl-min" />
          <span className="tl tl-max" />
        </div>
        <div className="chat-titlebar-center">
          <span className="chat-title">nick — zsh — 120×40</span>
        </div>
        <div className="chat-header-right">
          {quota && <span className="quota-text">{t('ai.quotaToday', { used: quota.used, limit: quota.limit })}</span>}
        </div>
      </div>

      <div className="term-body">
        <pre className="term-boot">{`# NOWICKI · octo-cmd
# session online · type a command / question
# ─────────────────────────────────────────`}</pre>

        {messages.map((msg, i) => (
          <TermBlock
            key={i}
            role={msg.role}
            content={msg.content}
            streaming={streaming && i === messages.length - 1 && msg.role === 'assistant'}
          />
        ))}

        {waiting && (
          <div className="term-block asst">
            <div className="term-line">
              <span className="term-gutter"><span className="term-prompt">nick@desk ~ % </span></span>
              <span className="term-text"><span className="term-cursor blink">█</span></span>
            </div>
          </div>
        )}

        <div className="term-input-row">
          <span className="term-prompt">you@nowicki ~ % </span>
          <input
            ref={inputRef}
            className="term-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                sendMessage(input)
              }
            }}
            placeholder={t('ai.placeholder')}
            disabled={loading}
            spellCheck={false}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
          />
          {!loading && !input && <span className="term-cursor blink ghost">█</span>}
        </div>
        <div ref={bottomRef} />
      </div>

      <style>{`
        .ai-chat.term-window {
          display: flex; flex-direction: column;
          height: 100%; width: 100%; min-height: 0;
          border-radius: 12px; overflow: hidden;
          background: #1e1e1e;
          border: 1px solid rgba(255,255,255,0.1);
          box-shadow:
            0 0 0 0.5px rgba(0,0,0,0.35),
            0 24px 56px rgba(0,0,0,0.45),
            inset 0 1px 0 rgba(255,255,255,0.08);
          font-family: var(--font-mono), ui-monospace, Menlo, Monaco, "Courier New", monospace;
        }

        .term-window .chat-titlebar {
          height: 40px; flex-shrink: 0;
          display: grid; grid-template-columns: 1fr auto 1fr;
          align-items: center; gap: 12px;
          padding: 0 14px;
          background: linear-gradient(180deg, #3a3a3c 0%, #2c2c2e 100%);
          border-bottom: 1px solid rgba(0,0,0,0.45);
        }
        .traffic-lights { display: flex; align-items: center; gap: 8px; justify-self: start; }
        .tl {
          width: 12px; height: 12px; border-radius: 50%;
          box-shadow: inset 0 0 0 0.5px rgba(0,0,0,0.25);
        }
        .tl-close { background: #ff5f57; }
        .tl-min { background: #febc2e; }
        .tl-max { background: #28c840; }
        .chat-titlebar-center { justify-self: center; }
        .chat-title {
          font-size: 12px; font-weight: 500; color: rgba(255,255,255,0.72);
          font-family: var(--font-ui); letter-spacing: -0.01em;
        }
        .chat-header-right { justify-self: end; }
        .quota-text {
          font-size: 10px; color: rgba(255,255,255,0.4);
          font-family: var(--font-mono);
        }

        .term-body {
          flex: 1; overflow-y: auto; min-height: 0;
          padding: 14px 16px 18px;
          background: #0c0c0c;
          color: #d4d4d4;
          display: flex; flex-direction: column; gap: 14px;
        }
        .term-boot {
          margin: 0; white-space: pre-wrap;
          color: #6a9955; font-size: 12px; line-height: 1.45;
          font-family: inherit;
        }

        .term-block { display: flex; flex-direction: column; gap: 2px; }
        .term-line {
          display: grid;
          grid-template-columns: 16ch 1fr;
          align-items: start;
          font-size: 13px; line-height: 1.55; word-break: break-word;
        }
        .term-block.asst .term-line { grid-template-columns: 14ch 1fr; }
        .term-gutter { flex-shrink: 0; white-space: pre; }
        .term-prompt { font-weight: 600; white-space: pre; }
        .term-block.user .term-prompt { color: #4ec9b0; }
        .term-block.asst .term-prompt { color: #569cd6; }
        .term-text { color: #d4d4d4; white-space: pre-wrap; }
        .term-block.user .term-text { color: #ce9178; }
        .term-block.asst .term-text { color: #dcdcaa; }

        .term-cursor {
          display: inline-block; color: #4ec9b0;
          font-weight: 400; line-height: 1.55; font-size: 13px;
        }
        .term-cursor.ghost {
          position: absolute; pointer-events: none; margin-left: 2px;
          color: rgba(78, 201, 176, 0.7);
        }
        .term-cursor.blink { animation: termBlink 1.05s step-end infinite; }
        @keyframes termBlink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }

        .term-input-row {
          display: flex; align-items: center; position: relative;
          font-size: 13px; line-height: 1.55; margin-top: 4px;
        }
        .term-input-row .term-prompt { color: #4ec9b0; }
        .term-input {
          flex: 1; min-width: 0;
          background: transparent; border: none; outline: none;
          color: #ce9178; font-family: inherit; font-size: 13px;
          line-height: 1.55; padding: 0; caret-color: #4ec9b0;
        }
        .term-input::placeholder { color: rgba(255,255,255,0.22); }
        .term-input:disabled { opacity: 0.5; }

        .term-body::-webkit-scrollbar { width: 8px; }
        .term-body::-webkit-scrollbar-thumb {
          background: rgba(255,255,255,0.12); border-radius: 4px;
        }
        .term-body::-webkit-scrollbar-track { background: transparent; }

        @media (max-width: 720px) {
          .quota-text { display: none; }
          .term-body { padding: 12px; }
          .term-line, .term-input-row, .term-input { font-size: 12px; }
          .term-line, .term-block.asst .term-line { grid-template-columns: 1fr; }
          .term-gutter:empty { display: none; }
        }
      `}</style>
    </div>
  )
}
