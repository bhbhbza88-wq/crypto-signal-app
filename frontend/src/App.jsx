import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api'
import StatsHero from './StatsHero'
import SignalCard from './SignalCard'
import HistoryTable from './HistoryTable'
import MarketView from './MarketView'
import AIChat from './AIChat'
import Backtest from './Backtest'
import SmartTrade from './SmartTrade'
import DryRunDashboard from './DryRunDashboard'
import XSecDashboard from './XSecDashboard'
import TrendDashboard from './TrendDashboard'

const POLL_INTERVAL = 15000
const MARKET_POLL_INTERVAL = 60000

const NAV_SECTIONS = [
  { items: [
    { key: 'ai_assistant', label: 'AI Ассистент', icon: '✦', badge: 'BETA' },
    { key: 'overview',     label: 'Dashboard',     icon: '◈' },
    { key: 'dryrun',       label: 'Дальран',        icon: '🛰', badge: 'LIVE' },
    { key: 'xsec',         label: 'Long-Short',     icon: '⚖', badge: 'NEW' },
    { key: 'trend_ff',     label: 'Trend-Following', icon: '📈', badge: 'NEW' },
    { key: 'portfolio',    label: 'Мой портфель',  icon: '◉' },
    { key: 'strategies',   label: 'Стратегии',     icon: '★', badge: 'HOT' },
    { key: 'dca_bot',      label: 'DCA Bot',        icon: '⟳' },
    { key: 'signal_bot',   label: 'Signal Bot',     icon: '⚡' },
    { key: 'grid_bot',     label: 'GRID Bot',       icon: '⊞' },
    { key: 'smarttrade',   label: 'SmartTrade',     icon: '⬡', sub: true },
    { key: 'market',       label: 'Скринер',        icon: '◫' },
    { key: 'backtest',     label: 'Бэктест',        icon: '📊' },
    { key: 'smarttrade_calc', label: 'Smart Trade', icon: '⚡', badge: 'NEW' },
    { key: 'history',      label: 'История',        icon: '📋' },
    { key: 'terminal',     label: 'Терминал',       icon: '▣' },
    { key: 'invite',       label: 'Пригласить',     icon: '👥' },
    { key: 'subscriptions',label: 'Подписки',       icon: '🎫' },
  ]}
]

const STEPS = [
  { icon: '✓', title: 'Сканер запущен', desc: 'Анализирует 32 пары на Bybit', done: true },
  { icon: '◈', title: 'Ищем сигнал', desc: 'EMA · RSI · ADX · ATR', active: true },
  { icon: '⚡', title: 'Уровни выставлены', desc: 'TP1 · TP2 · TP3 · SL' },
  { icon: '✦', title: 'AI объясняет', desc: 'Причины входа и риски' },
]

const TOP_STRATEGIES = [
  { symbol: 'SOL/USDT', dir: 'SHORT', type: 'Isolated x5', days: 92, roi: 171.83, apy: 681.74, minDeposit: 75, drawdown: -48.18 },
  { symbol: 'HYPE/USDT', dir: 'LONG', type: 'SPOT', days: 182, roi: 160.36, apy: 321.61, minDeposit: 32.5, drawdown: -58.94 },
  { symbol: 'ETH/EUR', dir: 'SHORT', type: 'SPOT', days: 273, roi: 135.64, apy: 181.25, minDeposit: 2.06, drawdown: -53.03 },
  { symbol: 'ETH/EUR', dir: 'SHORT', type: 'SPOT', days: 273, roi: 115.53, apy: 154.46, minDeposit: 3.05, drawdown: -51.02 },
  { symbol: 'SOL/USD', dir: 'SHORT', type: 'SPOT', days: 365, roi: 69.27, apy: 69.27, minDeposit: 9.95, drawdown: -39.41 },
  { symbol: 'SOL/USDT', dir: 'SHORT', type: 'SPOT', days: 181, roi: 64.09, apy: 129.25, minDeposit: 17.43, drawdown: -38.57 },
]

const GRID_PRESETS = [
  { name: 'Rising', desc: 'Зарабатывай на бычьем рынке', dir: 'LONG', type: 'SPOT TRAILING', users: 7278, bots: 3487 },
  { name: 'Stable', desc: 'Зарабатывай пока рынок движется боком', dir: 'LONG', type: 'SPOT', users: 7764, bots: 2721 },
  { name: 'To the moon', desc: 'Увеличь потенциал до x25 на бычьем рынке', dir: 'LONG', type: 'x2 TRAILING', users: 417, bots: 135 },
  { name: 'Reversal', desc: 'Зарабатывай на разворотах рынка', dir: 'REVERSAL', type: 'x3', users: 2302, bots: 315 },
  { name: 'Falling', desc: 'Увеличь потенциал до x25 на медвежьем рынке', dir: 'SHORT', type: 'x2 TRAILING', users: 177, bots: 60 },
]

function useLivePrices() {
  const [prices, setPrices] = useState(null)
  useEffect(() => {
    async function fp() {
      try {
        const [b, e] = await Promise.all([
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT'),
          fetch('https://api.bybit.com/v5/market/tickers?category=spot&symbol=ETHUSDT'),
        ])
        const btc = (await b.json())?.result?.list?.[0]
        const eth = (await e.json())?.result?.list?.[0]
        if (btc && eth) setPrices({
          btc: { price: parseFloat(btc.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }), change: (parseFloat(btc.price24hPcnt)*100).toFixed(2), positive: parseFloat(btc.price24hPcnt) >= 0 },
          eth: { price: parseFloat(eth.lastPrice).toLocaleString('en-US', { maximumFractionDigits: 0 }), change: (parseFloat(eth.price24hPcnt)*100).toFixed(2), positive: parseFloat(eth.price24hPcnt) >= 0 },
        })
      } catch {}
    }
    fp(); const id = setInterval(fp, 30000); return () => clearInterval(id)
  }, [])
  return prices
}

function MiniChart({ positive }) {
  const pts = positive ? "0,50 30,40 60,28 90,18 120,10 150,5 180,3" : "0,3 30,8 60,18 90,28 120,38 150,45 180,50"
  const color = positive ? '#00e5a8' : '#ff4f60'
  return (
    <svg width="100%" height="50" viewBox="0 0 180 55" preserveAspectRatio="none">
      <defs><linearGradient id={`g${positive}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity="0.25"/><stop offset="100%" stopColor={color} stopOpacity="0"/></linearGradient></defs>
      <polygon points={`0,50 ${pts} 180,55 0,55`} fill={`url(#g${positive})`}/>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/>
    </svg>
  )
}

function requestPush() { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission() }
function sendPush(t, b) { if ('Notification' in window && Notification.permission === 'granted') new Notification(t, { body: b }) }

// ── PAGES ──────────────────────────────────────────────────────

function AIAssistantPage() {
  const [input, setInput] = useState('')
  const suggestions = ['Найди лучшую стратегию для бокового рынка', 'Какой бот подходит для BTC в даунтренде?', 'Объясни разницу между DCA и GRID ботом', 'Как настроить стоп-лосс для скальпинга?']
  return (
    <div className="ai-page animate-in">
      <div className="aip-hero">
        <h1 className="aip-title">Строй и тестируй<br/>торговые стратегии с AI</h1>
        <p className="aip-sub">Опиши свои торговые идеи и получи стратегию которая подходит твоим целям</p>
        <div className="aip-input-wrap">
          <input className="aip-input" placeholder="Спроси AI..." value={input} onChange={e => setInput(e.target.value)} />
          <button className="aip-send" onClick={() => setInput('')}>→</button>
        </div>
        <p className="aip-disclaimer">Не является финансовым советом — проверяй перед торговлей · v1.0</p>
      </div>
      <div className="aip-suggestions">
        {suggestions.map((s, i) => (
          <button key={i} className="aip-sug" onClick={() => setInput(s)}>{s}</button>
        ))}
      </div>
    </div>
  )
}

function PortfolioPage() {
  return (
    <div className="portfolio-page animate-in">
      <div className="page-header"><h1 className="page-title">Мой портфель</h1></div>
      <div className="port-tabs">
        <span className="port-tab active">Обзор</span>
        <span className="port-tab">Биржи</span>
        <span className="port-tab">Виртуальный портфель</span>
      </div>
      <div className="port-block">
        <div className="port-block-inner">
          <div className="port-block-text">
            <h2 className="port-block-title">Биржи</h2>
            <p className="port-block-desc">Подключи все аккаунты на биржах, управляй сделками и отслеживай их прибыльность.</p>
            <button className="port-btn">Подключить биржу</button>
          </div>
          <div className="port-block-visual">
            <div className="port-exchange-icons">
              {['₿','Ξ','◎','⬡'].map((ic, i) => (
                <div key={i} className="port-exc-icon" style={{background:`hsl(${i*60+200},70%,45%)`}}>{ic}</div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="port-block alt">
        <div className="port-block-inner">
          <div className="port-block-text">
            <h2 className="port-block-title">Нет биржи?</h2>
            <p className="port-block-desc">Мы рекомендуем Bybit — можешь начать торговать сразу после верификации аккаунта.</p>
            <button className="port-btn">Создать аккаунт Bybit</button>
          </div>
          <div className="port-block-visual">
            <div className="port-bybit-logo">BYBIT</div>
          </div>
        </div>
      </div>
      <div className="port-soon">
        <h3 className="port-soon-title">Топ бирж для твоей страны</h3>
        <div className="port-exchanges-table">
          <div className="pet-header">
            <span>Биржа</span><span>Типы аккаунтов</span><span>Инструменты</span><span>Подключить</span><span>Создать</span>
          </div>
          {['Bybit','Binance','OKX','Kraken'].map((e, i) => (
            <div key={i} className="pet-row">
              <span className="pet-name">{e}</span>
              <span className="pet-val">Spot, Futures</span>
              <span className="pet-val">USDT, BTC</span>
              <button className="pet-btn">Подключить</button>
              <button className="pet-btn outline">Создать</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function StrategyGalleryPage() {
  const [filter, setFilter] = useState('all')
  return (
    <div className="strategy-page animate-in">
      <div className="page-header" style={{display:'flex',justifyContent:'space-between',alignItems:'center',flexWrap:'wrap',gap:12}}>
        <h1 className="page-title">Галерея стратегий ⓘ</h1>
        <div style={{display:'flex',gap:8}}>
          <button className="sg-filter-btn">↑↓ Сортировка</button>
          <button className="sg-filter-btn">⚙ Фильтры</button>
        </div>
      </div>
      <div className="sg-filters">
        {['Все биржи','Все пары','Long & Short','Spot & Futures','Max просадка','ROI','Длительность'].map((f,i) => (
          <button key={i} className={`sg-filter ${i===0?'active':''}`}>{f} ▾</button>
        ))}
        <button className="sg-clear">Сбросить фильтры</button>
      </div>
      <div className="sg-grid">
        {TOP_STRATEGIES.map((s, i) => (
          <div key={i} className="sg-card animate-in" style={{animationDelay:`${i*0.05}s`}}>
            <div className="sg-card-header">
              <div className="sg-coin">
                <div className="sg-coin-icon">{s.symbol.replace('/USDT','').replace('/EUR','').replace('/USD','').charAt(0)}</div>
                <div>
                  <div className="sg-symbol">{s.symbol}</div>
                  <div className="sg-tags">
                    <span className={`sg-tag ${s.dir==='LONG'?'long':s.dir==='SHORT'?'short':'rev'}`}>{s.dir}</span>
                    <span className="sg-tag neutral">{s.type}</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="sg-chart"><MiniChart positive={s.roi > 0} /></div>
            <div className="sg-roi-block">
              <div className="sg-roi-label">{s.days}Д BACKTEST, ROI</div>
              <div className={`sg-roi-val ${s.roi > 0 ? 'pos' : 'neg'}`}>{s.roi}%</div>
            </div>
            <div className="sg-stats">
              <div className="sg-stat"><span>APY</span><span>{s.apy}%</span></div>
              <div className="sg-stat"><span>Мин. депозит</span><span>${s.minDeposit}</span></div>
              <div className="sg-stat"><span>Макс. просадка</span><span className="neg">{s.drawdown}%</span></div>
            </div>
            <div className="sg-actions">
              <button className="sg-copy-btn">Копировать стратегию</button>
              <button className="sg-info-btn">ⓘ</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function DCABotPage() {
  return (
    <div className="bot-page animate-in">
      <div className="bot-layout">
        <div className="bot-chart-area">
          <div className="bot-chart-header">
            <span className="bot-chart-title">TV Chart</span>
            <div className="bot-chart-tabs">
              <button className="bct active">📊 График</button>
              <button className="bct">📋 Ордера 3</button>
              <button className="bct">⚡ AO Использование</button>
            </div>
          </div>
          <div className="bot-chart-placeholder">
            <div className="bcp-label">TradingView Chart</div>
            <div className="bcp-candles">
              {[40,55,35,65,45,70,50,60,42,58,48,72,38,62,44,66,52,68,46,64].map((h,i) => (
                <div key={i} className="bcp-candle" style={{height:`${h}%`,background:i%2===0?'var(--long)':'var(--short)',opacity:0.7,width:8,borderRadius:2}} />
              ))}
            </div>
          </div>
        </div>
        <div className="bot-form-area">
          <h2 className="bot-form-title">Создать DCA Bot</h2>
          <div className="bot-form">
            <div className="bf-group">
              <label className="bf-label">Название</label>
              <input className="bf-input" defaultValue="BTC/USDT Classic trading" />
            </div>
            <div className="bf-row">
              <div className="bf-group">
                <label className="bf-label">Биржа</label>
                <div className="bf-select-mock">⚠ Не подключена <span className="bf-connect">+Подключить</span></div>
              </div>
              <div className="bf-group">
                <label className="bf-label">Направление</label>
                <div className="bf-toggle">
                  <button className="bft active">Long</button>
                  <button className="bft">Short</button>
                </div>
              </div>
            </div>
            <div className="bf-group">
              <label className="bf-label">Пары</label>
              <div className="bf-select-mock">⭐ BTC/USDT <span style={{marginLeft:'auto',color:'var(--text-tertiary)'}}>1000 BTC ▾</span></div>
            </div>
            <div className="bf-section">
              <div className="bf-section-title">📌 Ордера входа <span className="bf-video">Видео туториал ▲</span></div>
              <div className="bf-row">
                <div className="bf-group">
                  <label className="bf-label">Базовый размер ордера</label>
                  <div className="bf-input-row"><input className="bf-input" defaultValue="20" /><span className="bf-unit">USDT ▾</span></div>
                </div>
                <div className="bf-group">
                  <label className="bf-label">Тип стартового ордера</label>
                  <div className="bf-toggle"><button className="bft active">Market</button><button className="bft">Limit</button></div>
                </div>
              </div>
            </div>
            <div className="bf-section">
              <div className="bf-section-title">📌 Период бэктеста</div>
              <div className="bf-row">
                <input className="bf-input" defaultValue="05/19/2026 - 06/19/2026" />
                <select className="bf-input" style={{flex:'0 0 100px'}}><option>1 месяц</option></select>
              </div>
              <button className="bf-backtest-btn">⟳ Запустить бэктест (0/10)</button>
            </div>
          </div>
          <div className="bot-form-footer">
            <button className="bf-summary-btn">📊 Сводка ▲</button>
            <button className="bf-backtest-btn2">⟳ Бэктест ▼</button>
            <button className="bf-trial-btn">Попробовать 7 дней</button>
          </div>
        </div>
      </div>
    </div>
  )
}

function SignalBotPage() {
  return (
    <div className="signal-page animate-in">
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:24}}>
        <h1 className="page-title">Создать Signal Bot</h1>
        <button className="sg-filter-btn">📖 Гайд</button>
      </div>
      <div className="signal-layout">
        <div className="signal-main">
          <div className="signal-section">
            <div className="ss-title">▲ Основное <span className="ss-video">Видео туториал</span></div>
            <div className="bf-group" style={{marginTop:16}}>
              <label className="bf-label">Тип алерта</label>
              <div className="alert-types">
                <div className="alert-type">
                  <div className="at-icon">📊</div>
                  <div><div className="at-title">Пользовательский сигнал</div><div className="at-desc">Разные типы сигналов из любых источников.</div></div>
                </div>
                <div className="alert-type active">
                  <div className="at-icon">📈</div>
                  <div><div className="at-title">TradingView Стратегия</div><div className="at-desc">Автоматизируй торговые правила с Pine Script.</div></div>
                </div>
              </div>
            </div>
            <div className="bf-row" style={{marginTop:16}}>
              <div className="bf-group">
                <label className="bf-label">Название</label>
                <input className="bf-input" defaultValue="Demo Signal Bot" />
              </div>
              <div className="bf-group">
                <label className="bf-label">Биржа</label>
                <div className="bf-select-mock">⚠ Не подключена <span className="bf-connect">+Подключить</span></div>
              </div>
            </div>
            <div className="bf-row" style={{marginTop:12}}>
              <div className="bf-group">
                <label className="bf-label">Направление</label>
                <div className="bf-toggle"><button className="bft active">Long</button><button className="bft">Reversal</button><button className="bft">Short</button></div>
              </div>
              <div className="bf-group">
                <label className="bf-label">Пары</label>
                <div className="bf-select-mock">Выбрать пары ▾</div>
              </div>
            </div>
            <div className="bf-group" style={{marginTop:12}}>
              <label className="bf-label">Макс. использование инвестиций</label>
              <div className="bf-input-row"><input className="bf-input" defaultValue="100" /><span className="bf-unit">% на бота ▾</span></div>
            </div>
          </div>

          <div className="signal-section">
            <div className="ss-title">▲ Настройка алертов <span className="ss-video">Видео туториал</span></div>
            <div className="bf-group" style={{marginTop:16}}>
              <label className="bf-label">Webhook URL для TradingView или других источников</label>
              <div className="webhook-row">
                <input className="bf-input" defaultValue="https://api.nwicki.app/signal_bots/webhooks" readOnly />
                <button className="sg-filter-btn">📋</button>
                <button className="sg-filter-btn">Перейти в TradingView ↗</button>
              </div>
              <p style={{fontSize:11,color:'var(--text-tertiary)',marginTop:6}}>Скопируй и вставь Webhook URL во вкладку Alert notifications в TradingView</p>
            </div>
          </div>

          <div className="signal-section">
            <div className="ss-title">▲ Настройки ордеров <span className="ss-video">Видео туториал</span></div>
            <div className="bf-row" style={{marginTop:16}}>
              <div className="bf-group">
                <label className="bf-label">Объём на ордер</label>
                <div className="bf-input-row"><input className="bf-input" defaultValue="100" /><span className="bf-unit">Total % ▾</span></div>
              </div>
              <div className="bf-group">
                <label className="bf-label">Тип ордера</label>
                <div className="bf-toggle"><button className="bft active">Market</button><button className="bft">Limit</button></div>
              </div>
            </div>
          </div>
        </div>
        <div className="signal-summary">
          <div className="ss-card">
            <div className="ss-card-title">Сводка</div>
            <div className="ss-row"><span>Макс. инвестиции</span><span>0</span></div>
            <div className="ss-row"><span>Условие старта</span><span>Пользовательский сигнал</span></div>
            <button className="bf-trial-btn" style={{width:'100%',marginTop:16}}>Попробовать 7 дней</button>
          </div>
        </div>
      </div>
    </div>
  )
}

function GridBotPage() {
  const [preset, setPreset] = useState(0)
  return (
    <div className="bot-page animate-in">
      <div className="bot-layout">
        <div className="bot-chart-area">
          <div className="bot-chart-header">
            <span className="bot-chart-title">GRID Bot</span>
            <div style={{display:'flex',gap:8}}>
              <button className="bct active">Пара</button>
              <button className="bct">Стратегии</button>
            </div>
          </div>
          <div className="bot-chart-placeholder">
            <div className="bcp-label">TradingView Chart</div>
            <div className="bcp-candles">
              {[45,52,38,60,42,55,48,65,40,58,44,62,50,56,46,68,38,60,44,58].map((h,i) => (
                <div key={i} className="bcp-candle" style={{height:`${h}%`,background:i%2===0?'var(--long)':'var(--short)',opacity:0.7,width:8,borderRadius:2}} />
              ))}
            </div>
            <div className="grid-lines">
              {[20,40,60,80].map((p,i) => <div key={i} className="grid-line" style={{top:`${p}%`}} />)}
            </div>
          </div>
          <div className="grid-no-bots">
            <div className="gnb-icon">🤖</div>
            <div className="gnb-title">Нет ботов</div>
            <div className="gnb-sub">Твои боты появятся здесь</div>
          </div>
        </div>
        <div className="bot-form-area">
          <h2 className="bot-form-title">Создать GRID Bot</h2>
          <div className="grid-presets">
            {GRID_PRESETS.map((p, i) => (
              <div key={i} className={`gp-item ${preset === i ? 'active' : ''}`} onClick={() => setPreset(i)}>
                <div className="gp-header">
                  <div>
                    <div className="gp-name">{p.name}</div>
                    <div className="gp-desc">{p.desc}</div>
                  </div>
                  <div className="gp-tags">
                    <span className={`sg-tag ${p.dir==='LONG'?'long':p.dir==='SHORT'?'short':'rev'}`}>{p.dir}</span>
                    <span className="sg-tag neutral">{p.type}</span>
                  </div>
                </div>
                <div className="gp-stats">
                  <span>👥 {p.users.toLocaleString()}</span>
                  <span>🤖 {p.bots.toLocaleString()}</span>
                </div>
              </div>
            ))}
          </div>
          <button className="bf-trial-btn" style={{width:'100%',marginTop:16}}>Попробовать 7 дней</button>
        </div>
      </div>
    </div>
  )
}

function TerminalPage() {
  return (
    <div className="terminal-page animate-in">
      <div className="term-toggles">
        {['TradingView','Сигналы','Торговый терминал','Ордера и позиции'].map((t,i) => (
          <label key={i} className="term-toggle">
            <div className={`tt-switch ${i < 3 ? 'on' : ''}`} />
            <span>{t}</span>
          </label>
        ))}
      </div>
      <div className="term-header">
        <div className="th-exchange">
          <span style={{color:'var(--amber)'}}>⚠</span> Не подключена
          <button className="bf-connect" style={{marginLeft:8}}>+Подключить</button>
        </div>
        <div className="th-market">
          <span className="th-market-label">Рынок</span>
          <span className="th-market-val">● BTC</span>
          <span style={{color:'var(--text-tertiary)',fontSize:11}}>5 BTC ▾</span>
        </div>
        <div className="th-pair">
          <span className="th-market-label">Торговая пара</span>
          <span className="th-market-val">⭐ ETH/BTC</span>
          <span style={{color:'var(--text-tertiary)',fontSize:11}}>20 ETH ▾</span>
        </div>
      </div>
      <div className="term-layout">
        <div className="term-chart">
          <div className="bot-chart-placeholder" style={{height:'100%'}}>
            <div className="bcp-label">TradingView Chart — ETH/BTC</div>
            <div className="bcp-candles">
              {[35,50,28,60,40,55,32,65,42,58,36,62,45,52,38,68,30,60,44,56].map((h,i) => (
                <div key={i} className="bcp-candle" style={{height:`${h}%`,background:i%2===0?'var(--long)':'var(--short)',opacity:0.7,width:8,borderRadius:2}} />
              ))}
            </div>
          </div>
        </div>
        <div className="term-orderbook">
          <div className="tob-title">Стакан цен</div>
          <div className="tob-asks">
            {[0.02727,0.02726,0.02725,0.02724,0.02722,0.02720].map((p,i) => (
              <div key={i} className="tob-row ask">
                <span className="tob-price">{p.toFixed(5)}</span>
                <span className="tob-size">{(Math.random()*200+50).toFixed(2)}</span>
                <span className="tob-total">{(Math.random()*200+50).toFixed(2)}</span>
              </div>
            ))}
          </div>
          <div className="tob-spread">0.02708 <span style={{color:'var(--text-tertiary)',fontSize:10}}>текущая</span></div>
          <div className="tob-bids">
            {[0.02707,0.02706,0.02705,0.02703,0.02702,0.02701].map((p,i) => (
              <div key={i} className="tob-row bid">
                <span className="tob-price">{p.toFixed(5)}</span>
                <span className="tob-size">{(Math.random()*200+50).toFixed(2)}</span>
                <span className="tob-total">{(Math.random()*200+50).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ComingSoonPage({ tab }) {
  const icons = { portfolio:'◉', invite:'👥', subscriptions:'🎫', smarttrade:'⬡' }
  const labels = { portfolio:'Мой портфель', invite:'Пригласить друга', subscriptions:'Подписки', smarttrade:'SmartTrade' }
  return (
    <div className="coming-soon-card animate-in">
      <div className="cs-icon">{icons[tab] || '◈'}</div>
      <div className="cs-title">{labels[tab] || tab}</div>
      <div className="cs-desc">Этот раздел находится в разработке. Следи за обновлениями!</div>
      <div className="cs-badge">Скоро</div>
    </div>
  )
}

export default function App() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('overview')
  const [signals, setSignals] = useState([])
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)
  const [market, setMarket] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const prevRef = useRef([])
  const prices = useLivePrices()

  const [dark, setDark] = useState(() => {
    const s = localStorage.getItem('theme')
    if (s) return s === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => {
    const h = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      if (e.key === 'd') setDark(d => !d)
      if (e.key === 'Escape') setSidebarOpen(false)
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  useEffect(() => { requestPush() }, [])

  const fetchCore = useCallback(async () => {
    try {
      const [s, h, st] = await Promise.all([api.getSignals(), api.getHistory(50), api.getStats()])
      if (s.length > 0 && prevRef.current.length === 0) sendPush(`🚨 NWICKI: ${s[0].signal} ${s[0].symbol}`, `Score ${s[0].score}/20`)
      prevRef.current = s; setSignals(s); setHistory(h); setStats(st); setError(null)
    } catch { setError('Нет связи с сервером.') }
    finally { setLoading(false) }
  }, [])

  const fetchMarket = useCallback(async () => { try { setMarket(await api.getMarket()) } catch {} }, [])

  useEffect(() => { fetchCore(); const id = setInterval(fetchCore, POLL_INTERVAL); return () => clearInterval(id) }, [fetchCore])
  useEffect(() => {
    if (tab !== 'market') return
    fetchMarket(); const id = setInterval(fetchMarket, MARKET_POLL_INTERVAL); return () => clearInterval(id)
  }, [tab, fetchMarket])

  const allItems = NAV_SECTIONS.flatMap(s => s.items)
  const currentItem = allItems.find(t => t.key === tab)

  return (
    <div className={`layout ${sidebarOpen ? 'sidebar-open' : ''} ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>

      {/* ── SIDEBAR ── */}
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="sidebar-logo" onClick={() => navigate('/')}>
            {!sidebarCollapsed && (
              <><div className="logo-icon"><span className="logo-n">N</span></div>
              <div className="logo-text-wrap">
                <span className="logo-name gradient-text">NWICKI</span>
                <span className="logo-sub">Crypto Scanner</span>
              </div></>
            )}
            {sidebarCollapsed && <div className="logo-icon"><span className="logo-n">N</span></div>}
          </div>
          <button className="sidebar-collapse-btn" onClick={() => setSidebarCollapsed(c => !c)}>
            {sidebarCollapsed ? '›' : '‹'}
          </button>
        </div>

        {prices && !sidebarCollapsed && (
          <div className="sidebar-prices">
            <div className="sp-item">
              <span className="sp-sym">BTC/USD</span>
              <span className="sp-val">${prices.btc.price}</span>
              <span className={`sp-chg ${prices.btc.positive ? 'pos' : 'neg'}`}>{prices.btc.positive ? '▲' : '▼'}{Math.abs(prices.btc.change)}%</span>
            </div>
            <div className="sp-div" />
            <div className="sp-item">
              <span className="sp-sym">ETH/USD</span>
              <span className="sp-val">${prices.eth.price}</span>
              <span className={`sp-chg ${prices.eth.positive ? 'pos' : 'neg'}`}>{prices.eth.positive ? '▲' : '▼'}{Math.abs(prices.eth.change)}%</span>
            </div>
          </div>
        )}

        <nav className="sidebar-nav">
          {NAV_SECTIONS[0].items.map((t) => (
            <button
              key={t.key}
              className={`nav-item ${tab === t.key ? 'active' : ''}`}
              onClick={() => { setTab(t.key); setSidebarOpen(false) }}
              title={sidebarCollapsed ? t.label : ''}
            >
              <span className="nav-icon">{t.icon}</span>
              {!sidebarCollapsed && <span className="nav-label">{t.label}</span>}
              {!sidebarCollapsed && (
                <div className="nav-right">
                  {t.badge && <span className={`nav-badge ${t.badge==='HOT'?'hot':t.badge==='AI'?'ai':'beta'}`}>{t.badge}</span>}
                  {tab === t.key && <span className="nav-pip" />}
                  {t.sub && <span style={{fontSize:10,color:'var(--text-tertiary)'}}>▾</span>}
                </div>
              )}
            </button>
          ))}
        </nav>

        {!sidebarCollapsed && (
          <>
            <div className="sidebar-banner">
              <div className="banner-content">
                <div className="banner-title">Explore QuantPilot →</div>
                <div className="banner-desc">Автономная AI платформа для крипто-стратегий</div>
              </div>
            </div>
            <div className="sidebar-community">
              <button className="community-close">✕</button>
              <div className="sc-title">Сообщество</div>
              <div className="sc-desc">Оставайся на связи с тысячами активных трейдеров</div>
              <button className="sc-tg-btn">✈ Join Telegram</button>
            </div>
          </>
        )}

        <div className="sidebar-bottom">
          {!sidebarCollapsed && (
            <div className="scan-status">
              <span className="scan-dot" />
              <div>
                <span className="scan-text">Сканирую рынок</span>
                <span className="scan-sub">каждые 2 мин</span>
              </div>
            </div>
          )}
          <div className="sidebar-actions">
            <button className="theme-toggle" onClick={() => setDark(d => !d)}>{dark ? '☀' : '☾'}</button>
          </div>
        </div>
      </aside>

      {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}

      {/* ── MAIN ── */}
      <div className="main-wrap">
        <header className="topbar">
          <div className="topbar-left">
            <button className="burger" onClick={() => setSidebarOpen(o => !o)}><span /><span /><span /></button>
            {prices && (
              <div className="topbar-prices">
                <div className="tp-item">
                  <span className="tp-sym">BTC/USD</span>
                  <span className="tp-val">${prices.btc.price}</span>
                  <span className={`tp-chg ${prices.btc.positive ? 'pos' : 'neg'}`}>{prices.btc.positive ? '▲' : '▼'}{Math.abs(prices.btc.change)}%</span>
                </div>
                <div className="tp-div" />
                <div className="tp-item">
                  <span className="tp-sym">ETH/USD</span>
                  <span className="tp-val">${prices.eth.price}</span>
                  <span className={`tp-chg ${prices.eth.positive ? 'pos' : 'neg'}`}>{prices.eth.positive ? '▲' : '▼'}{Math.abs(prices.eth.change)}%</span>
                </div>
              </div>
            )}
          </div>
          <div className="topbar-right">
            <button className="btn-create" onClick={() => setTab('dca_bot')}>+ Новый бот</button>
            <button className="btn-trial" onClick={() => setTab('ai_assistant')}>✦ AI Ассистент</button>
            <div className="plan-badge">Free plan ▾</div>
            <button className="theme-toggle-sm" onClick={() => setDark(d => !d)}>{dark ? '☀' : '☾'}</button>
          </div>
        </header>

        <main className="content">
          {error && <div className="error-banner animate-in">{error}</div>}

          {tab === 'ai_assistant' && <AIAssistantPage />}
          {tab === 'portfolio' && <PortfolioPage />}
          {tab === 'strategies' && <StrategyGalleryPage />}
          {tab === 'dca_bot' && <DCABotPage />}
          {tab === 'signal_bot' && <SignalBotPage />}
          {tab === 'grid_bot' && <GridBotPage />}
          {tab === 'terminal' && <TerminalPage />}
          {tab === 'market' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">Скринер рынка</h1></div><MarketView market={market} /></section>}
          {tab === 'history' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">История сделок</h1></div><HistoryTable history={history} /></section>}
          {tab === 'backtest' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">Бэктест <span className="beta-tag">BETA</span></h1></div><Backtest /></section>}
          {tab === 'dryrun' && <section className="section animate-in"><DryRunDashboard /></section>}
          {tab === 'xsec' && <section className="section animate-in"><XSecDashboard /></section>}
          {tab === 'trend_ff' && <section className="section animate-in"><TrendDashboard /></section>}
          {tab === 'smarttrade_calc' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">Smart Trade <span className="hot-tag">NEW</span></h1></div><SmartTrade /></section>}
          {tab === 'scanner' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">AI Сканер <span className="hot-tag">AI</span></h1></div><MarketView market={market} /></section>}
          {tab === 'ai' && <section className="section animate-in"><div className="page-header"><h1 className="page-title">AI Ассистент <span className="beta-tag">BETA</span></h1></div><AIChat signals={signals} stats={stats} market={market} /></section>}
          {(tab === 'invite' || tab === 'subscriptions' || tab === 'smarttrade') && <ComingSoonPage tab={tab} />}

          {tab === 'overview' && (
            <div className="animate-in">
              <div className="page-header">
                <h1 className="page-title">Dashboard</h1>
              </div>
              <div className="page-tabs-row">
                <span className="page-tab active">Главная</span>
                <span className="page-tab">Руководство</span>
              </div>
              <div className="steps-grid">
                {STEPS.map((s, i) => (
                  <div key={i} className={`step-card ${s.done?'done':''} ${s.active?'active-step':''}`}>
                    <div className={`step-icon-wrap ${s.done?'done':s.active?'act':''}`}>{s.icon}</div>
                    <div className="step-title">{s.title}</div>
                    <div className="step-desc">{s.desc}</div>
                    {s.done && <div className="step-check">✓</div>}
                    {s.active && <button className="step-btn" onClick={() => setTab('market')}>Скринер →</button>}
                  </div>
                ))}
              </div>
              <StatsHero stats={stats} loading={loading} />
              <div className="top-strategies">
                <div className="ts-header">
                  <div><h2 className="ts-title">Лучшие стратегии</h2><p className="ts-sub">Автоматические стратегии отсортированные по историческим результатам</p></div>
                  <button className="ts-more" onClick={() => setTab('strategies')}>Все стратегии →</button>
                </div>
                <div className="ts-grid">
                  {TOP_STRATEGIES.slice(0,3).map((s, i) => (
                    <div key={i} className="ts-card">
                      <div className="ts-card-header">
                        <div className="ts-coin">
                          <div className="ts-coin-icon">{s.symbol.replace('/USDT','').replace('/EUR','').replace('/USD','').charAt(0)}</div>
                          <div>
                            <div className="ts-symbol">{s.symbol}</div>
                            <div className="ts-tags">
                              <span className={`sg-tag ${s.dir==='LONG'?'long':'short'}`}>{s.dir}</span>
                              <span className="sg-tag neutral">{s.type}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="ts-chart"><MiniChart positive={s.roi > 0} /></div>
                      <div className="ts-roi-row"><span className="ts-roi-label">{s.days}Д BACKTEST, ROI</span><span className="ts-roi-val pos">{s.roi}%</span></div>
                      <div className="ts-stats">
                        <div className="ts-stat"><span className="ts-stat-label">APY</span><span className="ts-stat-val">{s.apy}%</span></div>
                        <div className="ts-stat"><span className="ts-stat-label">Мин. депозит</span><span className="ts-stat-val">${s.minDeposit}</span></div>
                        <div className="ts-stat"><span className="ts-stat-label">Просадка</span><span className="ts-stat-val neg">{s.drawdown}%</span></div>
                      </div>
                      <button className="ts-btn" onClick={() => setTab('strategies')}>Копировать стратегию</button>
                    </div>
                  ))}
                </div>
              </div>
              <section className="section" style={{marginTop:28}}>
                <h2 className="section-title">Активный сигнал</h2>
                {loading ? <SignalSkeleton /> : signals.length === 0 ? <EmptySignal /> : (
                  <div className="signals-grid">{signals.map(s => <SignalCard key={s.symbol} signal={s} />)}</div>
                )}
              </section>
            </div>
          )}
        </main>
      </div>

      <style>{`
        .layout { display: flex; min-height: 100vh; background: var(--bg); }
        .layout.sidebar-collapsed .sidebar { width: 56px; }
        .layout.sidebar-collapsed .content { max-width: 100%; }

        /* SIDEBAR */
        .sidebar { width: 220px; flex-shrink: 0; background: var(--sidebar-bg); border-right: 1px solid var(--sidebar-border); display: flex; flex-direction: column; position: sticky; top: 0; height: 100vh; z-index: 100; overflow-y: auto; overflow-x: hidden; transition: width 0.2s ease; }
        .sidebar-top { display: flex; align-items: center; justify-content: space-between; padding: 14px 10px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
        .sidebar-logo { display: flex; align-items: center; gap: 10px; cursor: pointer; flex: 1; min-width: 0; }
        .logo-icon { width: 32px; height: 32px; background: linear-gradient(135deg, var(--accent), var(--purple)); border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .logo-n { color: #fff; font-size: 17px; font-weight: 900; }
        .logo-text-wrap { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
        .logo-name { font-size: 14px; font-weight: 900; letter-spacing: 0.04em; line-height: 1; }
        .logo-sub { font-size: 9px; color: var(--text-tertiary); letter-spacing: 0.08em; text-transform: uppercase; }
        .sidebar-collapse-btn { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); width: 24px; height: 24px; border-radius: 6px; font-size: 14px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }

        .sidebar-prices { padding: 8px 12px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 6px; background: var(--surface-hover); flex-shrink: 0; flex-wrap: wrap; }
        .sp-item { display: flex; align-items: center; gap: 4px; }
        .sp-sym { font-size: 9px; color: var(--text-tertiary); font-weight: 600; }
        .sp-val { font-family: var(--font-mono); font-size: 10px; font-weight: 700; color: var(--text); }
        .sp-chg { font-family: var(--font-mono); font-size: 9px; font-weight: 600; }
        .sp-chg.pos { color: var(--long); } .sp-chg.neg { color: var(--short); }
        .sp-div { width: 1px; height: 12px; background: var(--border); }

        .sidebar-nav { flex: 1; padding: 8px 8px; display: flex; flex-direction: column; gap: 1px; }
        .nav-item { display: flex; align-items: center; gap: 9px; padding: 8px 10px; border: none; background: transparent; color: var(--text-tertiary); font-size: 13px; font-weight: 500; border-radius: 8px; transition: all 0.15s; text-align: left; width: 100%; white-space: nowrap; }
        .nav-item:hover { background: var(--surface-hover); color: var(--text-secondary); }
        .nav-item.active { background: var(--sidebar-active); color: var(--sidebar-active-text); font-weight: 600; }
        .nav-icon { font-size: 14px; width: 18px; text-align: center; flex-shrink: 0; }
        .nav-label { flex: 1; overflow: hidden; text-overflow: ellipsis; }
        .nav-right { display: flex; align-items: center; gap: 5px; margin-left: auto; }
        .nav-pip { width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
        .nav-badge { font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 4px; color: #fff; }
        .nav-badge.hot { background: var(--short); }
        .nav-badge.ai { background: linear-gradient(135deg, var(--accent), var(--purple)); }
        .nav-badge.beta { background: var(--amber); }

        .sidebar-banner { margin: 8px; background: var(--accent-soft); border: 1px solid var(--accent-soft); border-radius: 10px; padding: 12px; flex-shrink: 0; }
        .banner-title { font-size: 12px; font-weight: 700; color: var(--accent); margin-bottom: 4px; }
        .banner-desc { font-size: 10px; color: var(--text-secondary); line-height: 1.4; }

        .sidebar-community { margin: 0 8px 8px; background: var(--surface-hover); border: 1px solid var(--border); border-radius: 10px; padding: 12px; position: relative; flex-shrink: 0; }
        .community-close { position: absolute; top: 8px; right: 8px; border: none; background: transparent; color: var(--text-tertiary); font-size: 12px; }
        .sc-title { font-size: 12px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .sc-desc { font-size: 10px; color: var(--text-secondary); margin-bottom: 10px; line-height: 1.4; }
        .sc-tg-btn { width: 100%; padding: 8px; background: #229ED9; color: #fff; border: none; border-radius: 7px; font-size: 12px; font-weight: 600; }

        .sidebar-bottom { padding: 10px 12px; border-top: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
        .scan-status { display: flex; align-items: center; gap: 7px; }
        .scan-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; flex-shrink: 0; }
        .scan-text { display: block; font-size: 10px; color: var(--text-secondary); font-weight: 500; }
        .scan-sub { display: block; font-size: 9px; color: var(--text-tertiary); }
        .sidebar-actions { display: flex; gap: 4px; }
        .theme-toggle { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); width: 28px; height: 28px; border-radius: 7px; font-size: 13px; display: flex; align-items: center; justify-content: center; }

        /* TOPBAR */
        .topbar { display: flex; align-items: center; justify-content: space-between; padding: 0 20px; height: 50px; background: var(--sidebar-bg); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 90; gap: 12px; }
        .topbar-left { display: flex; align-items: center; gap: 12px; }
        .burger { border: none; background: transparent; display: flex; flex-direction: column; gap: 4px; padding: 4px; }
        .burger span { display: block; width: 18px; height: 2px; background: var(--text); border-radius: 2px; }
        .topbar-prices { display: flex; align-items: center; gap: 14px; }
        .tp-item { display: flex; align-items: center; gap: 5px; }
        .tp-sym { font-size: 10px; color: var(--text-tertiary); font-weight: 600; }
        .tp-val { font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--text); }
        .tp-chg { font-family: var(--font-mono); font-size: 11px; font-weight: 600; }
        .tp-chg.pos { color: var(--long); } .tp-chg.neg { color: var(--short); }
        .tp-div { width: 1px; height: 14px; background: var(--border); }
        .topbar-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .btn-create { border: 1px solid var(--border); background: var(--surface); color: var(--text); font-size: 12px; font-weight: 600; padding: 6px 12px; border-radius: 7px; transition: all 0.2s; white-space: nowrap; }
        .btn-create:hover { background: var(--surface-hover); }
        .btn-trial { background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; border: none; font-size: 12px; font-weight: 600; padding: 6px 14px; border-radius: 7px; box-shadow: 0 3px 10px rgba(77,140,245,0.3); white-space: nowrap; }
        .plan-badge { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; font-weight: 500; padding: 5px 10px; border-radius: 7px; white-space: nowrap; }
        .theme-toggle-sm { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); width: 30px; height: 30px; border-radius: 7px; font-size: 14px; }

        /* CONTENT */
        .sidebar-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 99; }
        .main-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; }
        .content { flex: 1; max-width: 1000px; width: 100%; margin: 0 auto; padding: 24px 24px 80px; display: flex; flex-direction: column; gap: 0; }
        .section { display: flex; flex-direction: column; gap: 14px; }
        .section-title { font-size: 10px; font-weight: 700; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.1em; display: flex; align-items: center; gap: 8px; }
        .section-title::after { content: ''; flex: 1; height: 1px; background: var(--border); }
        .page-header { margin-bottom: 4px; }
        .page-title { font-size: 22px; font-weight: 800; color: var(--text); letter-spacing: -0.02em; display: flex; align-items: center; gap: 10px; }
        .beta-tag { font-size: 10px; font-weight: 700; background: var(--amber); color: #fff; padding: 2px 7px; border-radius: 4px; }
        .hot-tag { font-size: 10px; font-weight: 700; background: var(--short); color: #fff; padding: 2px 7px; border-radius: 4px; }
        .page-tabs-row { display: flex; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
        .page-tab { padding: 8px 0; margin-right: 24px; font-size: 13px; font-weight: 500; color: var(--text-tertiary); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; transition: all 0.2s; }
        .page-tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
        .error-banner { padding: 12px 16px; background: var(--short-soft); color: var(--short); border: 1px solid var(--short-soft); border-radius: var(--radius-md); font-size: 13px; margin-bottom: 20px; }
        .signals-grid { display: grid; gap: 16px; }
        .pos { color: var(--long) !important; } .neg { color: var(--short) !important; }

        /* STEPS */
        .steps-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 24px; }
        .step-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px; box-shadow: var(--shadow-card); position: relative; transition: all 0.2s; }
        .step-card.done { border-color: rgba(0,229,168,0.3); }
        .step-card.active-step { border-color: var(--accent); }
        .step-icon-wrap { width: 32px; height: 32px; border-radius: 8px; background: var(--surface-hover); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; font-size: 14px; margin-bottom: 10px; color: var(--text-tertiary); }
        .step-icon-wrap.done { background: var(--long-soft); border-color: transparent; color: var(--long); }
        .step-icon-wrap.act { background: var(--accent-soft); border-color: transparent; color: var(--accent); }
        .step-title { font-size: 12px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .step-desc { font-size: 10px; color: var(--text-tertiary); line-height: 1.5; }
        .step-check { position: absolute; top: 10px; right: 10px; width: 16px; height: 16px; border-radius: 50%; background: var(--long); display: flex; align-items: center; justify-content: center; font-size: 9px; color: #fff; font-weight: 700; }
        .step-btn { margin-top: 8px; border: none; background: var(--accent); color: #fff; font-size: 10px; font-weight: 600; padding: 4px 9px; border-radius: 5px; }

        /* STRATEGY GALLERY */
        .sg-filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }
        .sg-filter { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; padding: 6px 12px; border-radius: 8px; transition: all 0.2s; }
        .sg-filter.active { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
        .sg-filter-btn { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; padding: 6px 12px; border-radius: 8px; }
        .sg-clear { border: none; background: transparent; color: var(--text-tertiary); font-size: 12px; padding: 6px 8px; }
        .sg-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; }
        .sg-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; box-shadow: var(--shadow-card); transition: all 0.2s; }
        .sg-card:hover { border-color: var(--accent); transform: translateY(-2px); box-shadow: var(--shadow-lg); }
        .sg-card-header { padding: 14px 14px 0; }
        .sg-coin { display: flex; align-items: center; gap: 10px; }
        .sg-coin-icon { width: 34px; height: 34px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--purple)); display: flex; align-items: center; justify-content: center; color: #fff; font-size: 14px; font-weight: 800; flex-shrink: 0; }
        .sg-symbol { font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .sg-tags { display: flex; gap: 4px; }
        .sg-tag { font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); }
        .sg-tag.long { background: var(--long-soft); color: var(--long); }
        .sg-tag.short { background: var(--short-soft); color: var(--short); }
        .sg-tag.rev { background: var(--amber-soft); color: var(--amber); }
        .sg-tag.neutral { background: var(--surface-hover); color: var(--text-secondary); }
        .sg-chart { padding: 8px 0; }
        .sg-roi-block { padding: 0 14px 8px; }
        .sg-roi-label { font-size: 10px; color: var(--text-tertiary); margin-bottom: 2px; }
        .sg-roi-val { font-family: var(--font-mono); font-size: 24px; font-weight: 800; }
        .sg-stats { border-top: 1px solid var(--border); }
        .sg-stat { display: flex; justify-content: space-between; padding: 7px 14px; border-bottom: 1px solid var(--border); font-size: 11px; color: var(--text-secondary); }
        .sg-stat span:last-child { font-family: var(--font-mono); font-weight: 600; color: var(--text); }
        .sg-actions { display: flex; gap: 0; }
        .sg-copy-btn { flex: 1; padding: 11px; background: var(--accent); color: #fff; border: none; font-size: 12px; font-weight: 600; }
        .sg-info-btn { width: 40px; background: var(--surface-hover); border: none; border-left: 1px solid var(--border); color: var(--text-tertiary); font-size: 14px; }

        /* TOP STRATEGIES */
        .top-strategies { margin: 24px 0; }
        .ts-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }
        .ts-title { font-size: 17px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .ts-sub { font-size: 12px; color: var(--text-tertiary); }
        .ts-more { border: 1px solid var(--border); background: transparent; color: var(--text-secondary); font-size: 12px; padding: 6px 12px; border-radius: 7px; white-space: nowrap; }
        .ts-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; }
        .ts-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; box-shadow: var(--shadow-card); transition: all 0.2s; }
        .ts-card:hover { border-color: var(--border-strong); transform: translateY(-2px); box-shadow: var(--shadow-lg); }
        .ts-card-header { padding: 14px 14px 0; }
        .ts-coin { display: flex; align-items: center; gap: 10px; }
        .ts-coin-icon { width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--purple)); display: flex; align-items: center; justify-content: center; color: #fff; font-size: 14px; font-weight: 800; flex-shrink: 0; }
        .ts-symbol { font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
        .ts-tags { display: flex; gap: 4px; }
        .ts-chart { padding: 6px 0; }
        .ts-roi-row { padding: 0 14px 8px; }
        .ts-roi-label { font-size: 10px; color: var(--text-tertiary); display: block; margin-bottom: 2px; }
        .ts-roi-val { font-family: var(--font-mono); font-size: 22px; font-weight: 800; display: block; }
        .ts-stats { border-top: 1px solid var(--border); }
        .ts-stat { display: flex; justify-content: space-between; padding: 6px 14px; border-bottom: 1px solid var(--border); }
        .ts-stat-label { font-size: 11px; color: var(--text-secondary); }
        .ts-stat-val { font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: var(--text); }
        .ts-btn { width: 100%; padding: 11px; background: var(--accent); color: #fff; border: none; font-size: 12px; font-weight: 600; }

        /* BOT PAGES */
        .bot-page { height: calc(100vh - 50px - 48px); display: flex; flex-direction: column; margin: -24px -24px 0; }
        .bot-layout { flex: 1; display: flex; overflow: hidden; }
        .bot-chart-area { flex: 1; display: flex; flex-direction: column; border-right: 1px solid var(--border); min-width: 0; }
        .bot-chart-header { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; background: var(--surface); }
        .bot-chart-title { font-size: 14px; font-weight: 700; color: var(--text); }
        .bot-chart-tabs { display: flex; gap: 4px; }
        .bct { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; padding: 5px 10px; border-radius: 6px; }
        .bct.active { background: var(--accent-soft); color: var(--accent); border-color: var(--accent-soft); }
        .bot-chart-placeholder { flex: 1; background: var(--surface); display: flex; flex-direction: column; align-items: center; justify-content: flex-end; padding: 20px; gap: 4px; position: relative; overflow: hidden; }
        .bcp-label { position: absolute; top: 12px; left: 16px; font-size: 12px; color: var(--text-tertiary); font-family: var(--font-mono); }
        .bcp-candles { display: flex; align-items: flex-end; gap: 3px; height: 60%; width: 90%; }
        .bcp-candle { flex-shrink: 0; border-radius: 2px; }
        .grid-lines { position: absolute; inset: 0; pointer-events: none; }
        .grid-line { position: absolute; left: 0; right: 0; height: 1px; background: var(--border); opacity: 0.5; }
        .grid-no-bots { padding: 20px; text-align: center; border-top: 1px solid var(--border); }
        .gnb-icon { font-size: 32px; margin-bottom: 8px; }
        .gnb-title { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
        .gnb-sub { font-size: 12px; color: var(--text-tertiary); }
        .bot-form-area { width: 320px; flex-shrink: 0; overflow-y: auto; padding: 16px; background: var(--surface); }
        .bot-form-title { font-size: 16px; font-weight: 700; color: var(--text); margin-bottom: 16px; }
        .bot-form { display: flex; flex-direction: column; gap: 12px; }
        .bf-group { display: flex; flex-direction: column; gap: 5px; }
        .bf-label { font-size: 11px; color: var(--text-secondary); font-weight: 500; }
        .bf-input { padding: 8px 12px; background: var(--surface-hover); border: 1px solid var(--border); border-radius: 7px; color: var(--text); font-size: 13px; font-family: var(--font-ui); outline: none; width: 100%; }
        .bf-input:focus { border-color: var(--accent); }
        .bf-input-row { display: flex; align-items: center; gap: 0; }
        .bf-input-row .bf-input { border-radius: 7px 0 0 7px; flex: 1; }
        .bf-unit { padding: 8px 10px; background: var(--surface-hover); border: 1px solid var(--border); border-left: none; border-radius: 0 7px 7px 0; font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
        .bf-row { display: flex; gap: 10px; }
        .bf-row .bf-group { flex: 1; }
        .bf-select-mock { padding: 8px 12px; background: var(--surface-hover); border: 1px solid var(--border); border-radius: 7px; font-size: 12px; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }
        .bf-connect { color: var(--accent); font-size: 11px; font-weight: 600; cursor: pointer; margin-left: auto; }
        .bf-toggle { display: flex; background: var(--surface-hover); border-radius: 7px; padding: 2px; gap: 2px; }
        .bft { flex: 1; padding: 5px 8px; border: none; background: transparent; color: var(--text-secondary); font-size: 12px; border-radius: 5px; transition: all 0.15s; }
        .bft.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-weight: 600; }
        .bf-section { padding-top: 10px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 10px; }
        .bf-section-title { font-size: 12px; font-weight: 700; color: var(--text); display: flex; justify-content: space-between; }
        .bf-video { font-size: 11px; color: var(--accent); font-weight: 400; }
        .bf-backtest-btn { padding: 8px 14px; border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; border-radius: 7px; width: 100%; }
        .bf-backtest-btn2 { padding: 8px 14px; border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; border-radius: 7px; }
        .bf-trial-btn { padding: 10px 20px; background: linear-gradient(135deg, var(--accent), var(--purple)); color: #fff; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; }
        .bot-form-footer { display: flex; gap: 8px; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
        .bf-summary-btn { flex: 1; padding: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; border-radius: 7px; }

        /* GRID BOT */
        .grid-presets { display: flex; flex-direction: column; gap: 8px; }
        .gp-item { border: 1px solid var(--border); background: var(--surface-hover); border-radius: 10px; padding: 12px; cursor: pointer; transition: all 0.15s; }
        .gp-item.active { border-color: var(--accent); background: var(--accent-soft); }
        .gp-item:hover { border-color: var(--border-strong); }
        .gp-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
        .gp-name { font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 3px; }
        .gp-desc { font-size: 11px; color: var(--text-secondary); }
        .gp-tags { display: flex; gap: 4px; flex-wrap: wrap; }
        .gp-stats { font-size: 11px; color: var(--text-tertiary); display: flex; gap: 12px; }

        /* SIGNAL BOT */
        .signal-page { max-width: 100%; }
        .signal-layout { display: flex; gap: 20px; align-items: flex-start; }
        .signal-main { flex: 1; display: flex; flex-direction: column; gap: 16px; }
        .signal-section { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px; }
        .ss-title { font-size: 14px; font-weight: 700; color: var(--text); display: flex; justify-content: space-between; align-items: center; }
        .ss-video { font-size: 11px; color: var(--accent); font-weight: 400; }
        .alert-types { display: flex; gap: 10px; margin-top: 10px; }
        .alert-type { flex: 1; border: 1px solid var(--border); border-radius: 10px; padding: 14px; display: flex; gap: 12px; align-items: flex-start; cursor: pointer; transition: all 0.15s; }
        .alert-type.active { border-color: var(--accent); background: var(--accent-soft); }
        .at-icon { font-size: 20px; }
        .at-title { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
        .at-desc { font-size: 11px; color: var(--text-secondary); }
        .webhook-row { display: flex; gap: 8px; align-items: center; }
        .webhook-row .bf-input { flex: 1; font-size: 11px; font-family: var(--font-mono); }
        .signal-summary { width: 240px; flex-shrink: 0; }
        .ss-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px; position: sticky; top: 80px; }
        .ss-card-title { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 12px; }
        .ss-row { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-secondary); padding: 6px 0; border-bottom: 1px solid var(--border); }

        /* TERMINAL */
        .terminal-page { margin: -24px -24px 0; height: calc(100vh - 50px - 48px); display: flex; flex-direction: column; }
        .term-toggles { display: flex; gap: 16px; padding: 10px 20px; border-bottom: 1px solid var(--border); background: var(--surface); flex-wrap: wrap; flex-shrink: 0; }
        .term-toggle { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-secondary); cursor: pointer; }
        .tt-switch { width: 32px; height: 16px; border-radius: 8px; background: var(--accent); position: relative; }
        .tt-switch::after { content: ''; position: absolute; top: 2px; right: 2px; width: 12px; height: 12px; border-radius: 50%; background: #fff; }
        .tt-switch:not(.on) { background: var(--border); }
        .tt-switch:not(.on)::after { left: 2px; right: auto; }
        .term-header { display: flex; gap: 24px; padding: 10px 20px; border-bottom: 1px solid var(--border); background: var(--surface); align-items: center; flex-shrink: 0; flex-wrap: wrap; }
        .th-exchange { font-size: 12px; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }
        .th-market, .th-pair { display: flex; flex-direction: column; gap: 2px; }
        .th-market-label { font-size: 10px; color: var(--text-tertiary); }
        .th-market-val { font-size: 13px; font-weight: 600; color: var(--text); }
        .term-layout { flex: 1; display: flex; overflow: hidden; }
        .term-chart { flex: 1; min-width: 0; }
        .term-chart .bot-chart-placeholder { height: 100%; }
        .term-orderbook { width: 220px; flex-shrink: 0; border-left: 1px solid var(--border); overflow-y: auto; }
        .tob-title { padding: 10px 12px; font-size: 11px; font-weight: 700; color: var(--text-secondary); border-bottom: 1px solid var(--border); text-transform: uppercase; letter-spacing: 0.06em; }
        .tob-row { display: flex; gap: 8px; padding: 4px 12px; font-size: 10px; font-family: var(--font-mono); }
        .tob-row.ask .tob-price { color: var(--short); }
        .tob-row.bid .tob-price { color: var(--long); }
        .tob-size, .tob-total { color: var(--text-secondary); flex: 1; text-align: right; }
        .tob-spread { padding: 6px 12px; font-size: 12px; font-weight: 700; color: var(--text); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); font-family: var(--font-mono); }

        /* PORTFOLIO */
        .portfolio-page { max-width: 100%; }
        .port-tabs { display: flex; border-bottom: 1px solid var(--border); margin-bottom: 24px; }
        .port-tab { padding: 8px 0; margin-right: 24px; font-size: 13px; color: var(--text-tertiary); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; }
        .port-tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
        .port-block { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; margin-bottom: 16px; }
        .port-block.alt { background: var(--long-soft); border-color: rgba(0,229,168,0.2); }
        .port-block-inner { display: flex; justify-content: space-between; align-items: center; padding: 32px; gap: 24px; }
        .port-block-title { font-size: 20px; font-weight: 700; color: var(--text); margin-bottom: 8px; }
        .port-block-desc { font-size: 14px; color: var(--text-secondary); margin-bottom: 20px; line-height: 1.5; max-width: 400px; }
        .port-btn { padding: 10px 20px; background: var(--accent); color: #fff; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; }
        .port-block-visual { display: flex; align-items: center; justify-content: center; }
        .port-exchange-icons { display: flex; gap: -8px; }
        .port-exc-icon { width: 48px; height: 48px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 20px; border: 2px solid var(--surface); margin-left: -12px; }
        .port-exc-icon:first-child { margin-left: 0; }
        .port-bybit-logo { font-size: 24px; font-weight: 900; color: var(--accent); letter-spacing: 0.05em; }
        .port-soon { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
        .port-soon-title { font-size: 16px; font-weight: 700; color: var(--text); padding: 20px 24px 0; margin-bottom: 12px; }
        .port-exchanges-table { padding: 0 0 16px; }
        .pet-header { display: flex; padding: 10px 24px; border-bottom: 1px solid var(--border); font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.06em; gap: 16px; }
        .pet-header span, .pet-row span { flex: 1; }
        .pet-row { display: flex; align-items: center; padding: 12px 24px; border-bottom: 1px solid var(--border); gap: 16px; font-size: 13px; }
        .pet-row:last-child { border-bottom: none; }
        .pet-name { font-weight: 600; color: var(--text); }
        .pet-val { color: var(--text-secondary); }
        .pet-btn { padding: 6px 14px; border: 1px solid var(--accent); background: transparent; color: var(--accent); font-size: 12px; border-radius: 6px; white-space: nowrap; }
        .pet-btn.outline { border-color: var(--border); color: var(--text-secondary); }

        /* AI PAGE */
        .ai-page { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 60vh; gap: 24px; }
        .aip-hero { text-align: center; max-width: 600px; }
        .aip-title { font-size: clamp(24px, 4vw, 40px); font-weight: 900; color: var(--text); line-height: 1.2; margin-bottom: 12px; }
        .aip-sub { font-size: 15px; color: var(--text-secondary); margin-bottom: 24px; }
        .aip-input-wrap { display: flex; align-items: center; background: var(--surface); border: 1px solid var(--border); border-radius: 50px; padding: 6px 6px 6px 20px; box-shadow: var(--shadow-lg); max-width: 600px; margin: 0 auto; }
        .aip-input { flex: 1; border: none; background: transparent; color: var(--text); font-size: 15px; font-family: var(--font-ui); outline: none; }
        .aip-input::placeholder { color: var(--text-tertiary); }
        .aip-send { width: 38px; height: 38px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--purple)); border: none; color: #fff; font-size: 18px; flex-shrink: 0; }
        .aip-disclaimer { font-size: 11px; color: var(--text-tertiary); margin-top: 10px; }
        .aip-suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; max-width: 700px; }
        .aip-sug { border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 12px; padding: 8px 14px; border-radius: 20px; transition: all 0.15s; text-align: left; }
        .aip-sug:hover { border-color: var(--accent); color: var(--accent); }

        /* COMING SOON */
        .coming-soon-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 64px 32px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 14px; }
        .cs-icon { font-size: 48px; opacity: 0.3; }
        .cs-title { font-size: 22px; font-weight: 700; color: var(--text); }
        .cs-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; max-width: 400px; }
        .cs-badge { background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent-soft); padding: 6px 16px; border-radius: 20px; font-size: 13px; font-weight: 600; }

        /* SKELETON & EMPTY */
        .signal-skeleton { border-radius: var(--radius-lg); overflow: hidden; background: var(--surface); border: 1px solid var(--border); }
        .sk-bar { height: 4px; } .sk-content { padding: 22px; display: flex; flex-direction: column; gap: 14px; }
        .sk-row { display: flex; gap: 12px; align-items: center; } .sk-circle { width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0; }
        .sk-line { height: 14px; border-radius: 6px; flex: 1; } .sk-chart { height: 180px; border-radius: 8px; }
        .empty-signal { padding: 48px 32px; text-align: center; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); display: flex; flex-direction: column; align-items: center; gap: 14px; }
        .empty-icon { font-size: 40px; opacity: 0.4; } .empty-title { font-size: 16px; font-weight: 600; color: var(--text-secondary); }
        .empty-desc { font-size: 13px; color: var(--text-tertiary); line-height: 1.6; max-width: 320px; }
        .empty-pulse { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--long); background: var(--long-soft); padding: 8px 16px; border-radius: 20px; }

        @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(0,229,168,0.4)} 70%{box-shadow:0 0 0 8px rgba(0,229,168,0)} 100%{box-shadow:0 0 0 0 rgba(0,229,168,0)} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        .animate-in { animation: fadeIn 0.35s ease forwards; }

        @media (max-width: 1100px) { .sg-grid { grid-template-columns: repeat(2,1fr); } .ts-grid { grid-template-columns: repeat(2,1fr); } }
        @media (max-width: 900px) { .steps-grid { grid-template-columns: repeat(2,1fr); } }
        @media (max-width: 768px) {
          .sidebar { position: fixed; left: -240px; top: 0; height: 100vh; transition: left 0.3s ease; z-index: 100; }
          .layout.sidebar-open .sidebar { left: 0; }
          .burger { display: flex; }
          .content { padding: 16px 14px 80px; }
          .topbar-prices { display: none; }
          .sg-grid, .ts-grid { grid-template-columns: 1fr; }
          .bot-layout { flex-direction: column; }
          .bot-chart-area { height: 250px; flex: none; }
          .bot-form-area { width: 100%; }
          .signal-layout { flex-direction: column; }
          .signal-summary { width: 100%; }
          .term-orderbook { display: none; }
          .port-block-inner { flex-direction: column; }
        }
      `}</style>
    </div>
  )
}

function SignalSkeleton() {
  return (
    <div className="signal-skeleton animate-in">
      <div className="sk-bar skeleton" />
      <div className="sk-content">
        <div className="sk-row"><div className="sk-circle skeleton" /><div style={{flex:1,display:'flex',flexDirection:'column',gap:8}}><div className="sk-line skeleton" style={{width:'40%'}} /><div className="sk-line skeleton" style={{width:'25%',height:10}} /></div></div>
        <div className="sk-line skeleton" style={{height:8}} />
        <div className="sk-chart skeleton" />
      </div>
    </div>
  )
}

function EmptySignal() {
  return (
    <div className="empty-signal animate-in">
      <div className="empty-icon">🔍</div>
      <div className="empty-title">Сигналов нет</div>
      <div className="empty-desc">Сканер анализирует 32 пары на Bybit. Когда найдёт точку входа — сигнал появится здесь автоматически.</div>
      <div className="empty-pulse"><span style={{width:7,height:7,borderRadius:'50%',background:'var(--long)',animation:'pulse 2s infinite',display:'inline-block'}} />Сканирование каждые 2 минуты</div>
    </div>
  )
}
