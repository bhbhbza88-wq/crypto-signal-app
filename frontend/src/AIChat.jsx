import { useState, useRef, useEffect } from 'react'

const SUGGESTIONS = [
  'Почему сканер вошёл в эту сделку?',
  'Какие риски у текущего сигнала?',
  'Объясни стратегию сканера',
  'Покажи статистику за неделю',
  'Что такое ADX и зачем он нужен?',
  'Когда лучше не торговать?',
]

const OPENAI_API_KEY = import.meta.env.VITE_OPENAI_API_KEY || ''

function buildSystemPrompt(signals, stats, market) {
  const activeSignal = signals?.length > 0 ? JSON.stringify(signals[0], null, 2) : 'Нет активных сигналов'
  const statsToday = stats?.today ? `Сделок: ${stats.today.total}, Винрейт: ${stats.today.winrate}%, PnL: ${stats.today.total_pnl}%` : 'Нет данных'
  const marketInfo = market ? `BTC режим: ${market.btc_regime}, Аптренд: ${market.uptrend_count}, Даунтренд: ${market.downtrend_count}` : 'Нет данных'

  return `Ты — AI-ассистент торговой платформы NWICKI. Помогаешь трейдерам понять сигналы, стратегию и риски.

ТЕКУЩИЙ АКТИВНЫЙ СИГНАЛ:
${activeSignal}

СТАТИСТИКА СЕГОДНЯ:
${statsToday}

СОСТОЯНИЕ РЫНКА:
${marketInfo}

СТРАТЕГИЯ СКАНЕРА:
- Сканирует 32 пары USDT на Bybit каждые 2 минуты
- Использует EMA, RSI, ADX, ATR для анализа
- Минимальный Score для входа: 12/20
- Блокирует сигналы против режима BTC
- Устанавливает TP1, TP2, TP3 и стоп-лосс на основе ATR

Отвечай кратко и по делу. Используй эмодзи для наглядности. Отвечай на русском языке.`
}

export default function AIChat({ signals, stats, market }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '👋 Привет! Я AI-ассистент NWICKI на базе GPT-4o. Могу объяснить текущий сигнал, риски, стратегию сканера или ответить на любой вопрос о торговле. Спрашивай!'
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [apiKey, setApiKey] = useState(OPENAI_API_KEY)
  const [showKeyInput, setShowKeyInput] = useState(!OPENAI_API_KEY)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage(text) {
    if (!text.trim() || loading) return
    if (!apiKey) { setShowKeyInput(true); return }

    const userMsg = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const response = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model: 'gpt-4o',
          max_tokens: 800,
          messages: [
            { role: 'system', content: buildSystemPrompt(signals, stats, market) },
            ...messages.filter(m => m.role !== 'system').map(m => ({ role: m.role, content: m.content })),
            userMsg,
          ]
        })
      })
      const data = await response.json()
      if (data.error) throw new Error(data.error.message)
      const reply = data.choices?.[0]?.message?.content || 'Не удалось получить ответ'
      setMessages(prev => [...prev, { role: 'assistant', content: reply }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `❌ Ошибка: ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  if (showKeyInput) {
    return (
      <div className="key-setup">
        <div className="key-icon">🔑</div>
        <h3 className="key-title">Введи OpenAI API ключ</h3>
        <p className="key-desc">Ключ хранится только в браузере и никуда не отправляется кроме OpenAI.</p>
        <input
          className="key-input"
          type="password"
          placeholder="sk-..."
          value={apiKey}
          onChange={e => setApiKey(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && apiKey.startsWith('sk-')) {
              setShowKeyInput(false)
            }
          }}
        />
        <button
          className="key-btn"
          disabled={!apiKey.startsWith('sk-')}
          onClick={() => setShowKeyInput(false)}
        >
          Подключить
        </button>
        <p className="key-hint">Получить ключ: <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">platform.openai.com/api-keys</a></p>
        <style>{`
          .key-setup {
            background: var(--surface); border: 1px solid var(--border);
            border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
            padding: 48px 32px; display: flex; flex-direction: column;
            align-items: center; gap: 16px; text-align: center;
          }
          .key-icon { font-size: 40px; }
          .key-title { font-size: 20px; font-weight: 700; color: var(--text); }
          .key-desc { font-size: 13px; color: var(--text-secondary); max-width: 360px; line-height: 1.6; }
          .key-input {
            width: 100%; max-width: 400px; padding: 12px 16px;
            background: var(--surface-hover); border: 1px solid var(--border);
            border-radius: var(--radius-md); color: var(--text);
            font-family: var(--font-mono); font-size: 14px; outline: none;
            transition: border-color 0.15s;
          }
          .key-input:focus { border-color: var(--accent); }
          .key-btn {
            padding: 12px 32px; background: var(--accent); color: #fff;
            border: none; border-radius: var(--radius-md);
            font-size: 14px; font-weight: 600;
            transition: opacity 0.15s;
          }
          .key-btn:disabled { opacity: 0.4; }
          .key-btn:hover:not(:disabled) { opacity: 0.85; }
          .key-hint { font-size: 12px; color: var(--text-tertiary); }
          .key-hint a { color: var(--accent); }
        `}</style>
      </div>
    )
  }

  return (
    <div className="ai-chat">
      <div className="chat-header">
        <div className="chat-header-left">
          <div className="ai-avatar">AI</div>
          <div>
            <span className="chat-title">NWICKI AI</span>
            <span className="chat-sub">GPT-4o · Знает текущие сигналы и рынок</span>
          </div>
        </div>
        <div className="chat-header-right">
          <div className="ai-status">
            <span className="status-dot" />
            <span className="status-text">Online</span>
          </div>
          <button className="key-change-btn" onClick={() => setShowKeyInput(true)} title="Сменить API ключ">🔑</button>
        </div>
      </div>

      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {msg.role === 'assistant' && <div className="msg-avatar">AI</div>}
            <div className="msg-bubble">
              {msg.content.split('\n').map((line, j) => (
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
        .key-change-btn { border: 1px solid var(--border); background: var(--surface-hover); width: 32px; height: 32px; border-radius: 8px; font-size: 14px; }
        .key-change-btn:hover { background: var(--surface); }

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
