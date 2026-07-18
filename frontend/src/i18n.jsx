import { createContext, useContext, useEffect, useMemo, useState } from 'react'

export const LOCALES = [
  { code: 'ru', label: 'Русский', short: 'RU' },
  { code: 'en', label: 'English', short: 'EN' },
  { code: 'pl', label: 'Polski', short: 'PL' },
]

const MESSAGES = {
  ru: {
    'nav.main': 'Главное',
    'nav.account': 'Аккаунт',
    'nav.admin': 'Админ',
    'nav.dashboard': 'Дашборд',
    'nav.history': 'История',
    'nav.ai': 'AI Ассистент',
    'nav.pricing': 'Тарифы',
    'nav.adminPanel': 'Админка',
    'nav.channelAnalyzer': 'Channel Analyzer',
    'top.telegram': 'Telegram',
    'top.bot': 'Бот',
    'top.ai': 'AI Ассистент',
    'top.login': 'Войти',
    'top.logout': 'Выйти',
    'top.theme': 'Тема',
    'top.themeDark': 'Тёмная',
    'top.themeLight': 'Светлая',
    'top.language': 'Язык',
    'top.plan': 'Тариф',
    'top.account': 'Аккаунт',
    'scan.online': 'Сканер онлайн',
    'scan.sub': 'поиск точек входа 24/7',
    'trial.active': 'Premium-триал активен',
    'trial.left': 'осталось {n} {unit}. История и Premium-фичи открыты.',
    'trial.day': 'день',
    'trial.days': 'дн.',
    'trial.cta': 'Оформить Premium',
    'dash.live': 'Scanner live',
    'dash.title': 'Дашборд',
    'dash.sub': 'AI ищет точки входа. Открытые сетапы и свежий трек-рекорд — ниже.',
    'kpi.active': 'Активные',
    'kpi.activeSub': 'в работе',
    'kpi.wait': 'ожидание',
    'kpi.closed': 'Закрыто',
    'kpi.closedSub': 'всего сделок',
    'kpi.winrate': 'Винрейт',
    'kpi.winrateSub': 'за всё время',
    'kpi.avgPnl': 'Ср. PnL',
    'kpi.avgPnlSub': 'на сделку',
    'sec.active': 'Активные сигналы',
    'sec.recent': 'Последние сигналы',
    'recent.all': 'Вся история →',
    'recent.lock': 'Полная лента сделок и PnL по дням — на Premium',
    'recent.unlock': 'Открыть за Premium →',
    'empty.title': 'Сигналов нет',
    'empty.desc': 'AI-сканер ищет точки входа на рынке. Как только появится новый сигнал — он отобразится здесь.',
    'empty.pulse': 'Сканируем рынок каждые несколько минут',
    'load.section': 'Загрузка раздела…',
    'load.app': 'Загрузка…',
    'err.boundary': 'Что-то пошло не так',
    'err.boundarySub': 'Раздел не смог загрузиться. Попробуй обновить страницу — остальное приложение работает.',
    'err.reload': 'Обновить',
    'err.offline': 'Нет связи с сервером.',
    'hist.title': 'История сделок',
    'ai.title': 'AI Ассистент',
  },
  en: {
    'nav.main': 'Main',
    'nav.account': 'Account',
    'nav.admin': 'Admin',
    'nav.dashboard': 'Dashboard',
    'nav.history': 'History',
    'nav.ai': 'AI Assistant',
    'nav.pricing': 'Pricing',
    'nav.adminPanel': 'Admin',
    'nav.channelAnalyzer': 'Channel Analyzer',
    'top.telegram': 'Telegram',
    'top.bot': 'Bot',
    'top.ai': 'AI Assistant',
    'top.login': 'Sign in',
    'top.logout': 'Log out',
    'top.theme': 'Theme',
    'top.themeDark': 'Dark',
    'top.themeLight': 'Light',
    'top.language': 'Language',
    'top.plan': 'Plan',
    'top.account': 'Account',
    'scan.online': 'Scanner online',
    'scan.sub': 'hunting entries 24/7',
    'trial.active': 'Premium trial active',
    'trial.left': '{n} {unit} left. History and Premium features are unlocked.',
    'trial.day': 'day',
    'trial.days': 'days',
    'trial.cta': 'Get Premium',
    'dash.live': 'Scanner live',
    'dash.title': 'Dashboard',
    'dash.sub': 'AI hunts entries. Open setups and recent track record below.',
    'kpi.active': 'Active',
    'kpi.activeSub': 'in play',
    'kpi.wait': 'waiting',
    'kpi.closed': 'Closed',
    'kpi.closedSub': 'all trades',
    'kpi.winrate': 'Winrate',
    'kpi.winrateSub': 'all time',
    'kpi.avgPnl': 'Avg PnL',
    'kpi.avgPnlSub': 'per trade',
    'sec.active': 'Active signals',
    'sec.recent': 'Recent signals',
    'recent.all': 'Full history →',
    'recent.lock': 'Full trade feed and daily PnL — on Premium',
    'recent.unlock': 'Unlock with Premium →',
    'empty.title': 'No signals yet',
    'empty.desc': 'The AI scanner is looking for entries. New signals will show up here.',
    'empty.pulse': 'Scanning the market every few minutes',
    'load.section': 'Loading section…',
    'load.app': 'Loading…',
    'err.boundary': 'Something went wrong',
    'err.boundarySub': 'This section failed to load. Try refreshing — the rest of the app still works.',
    'err.reload': 'Reload',
    'err.offline': 'No connection to the server.',
    'hist.title': 'Trade history',
    'ai.title': 'AI Assistant',
  },
  pl: {
    'nav.main': 'Główne',
    'nav.account': 'Konto',
    'nav.admin': 'Admin',
    'nav.dashboard': 'Panel',
    'nav.history': 'Historia',
    'nav.ai': 'Asystent AI',
    'nav.pricing': 'Cennik',
    'nav.adminPanel': 'Admin',
    'nav.channelAnalyzer': 'Channel Analyzer',
    'top.telegram': 'Telegram',
    'top.bot': 'Bot',
    'top.ai': 'Asystent AI',
    'top.login': 'Zaloguj',
    'top.logout': 'Wyloguj',
    'top.theme': 'Motyw',
    'top.themeDark': 'Ciemny',
    'top.themeLight': 'Jasny',
    'top.language': 'Język',
    'top.plan': 'Plan',
    'top.account': 'Konto',
    'scan.online': 'Skaner online',
    'scan.sub': 'szuka wejść 24/7',
    'trial.active': 'Aktywny trial Premium',
    'trial.left': 'zostało {n} {unit}. Historia i funkcje Premium są otwarte.',
    'trial.day': 'dzień',
    'trial.days': 'dni',
    'trial.cta': 'Weź Premium',
    'dash.live': 'Scanner live',
    'dash.title': 'Panel',
    'dash.sub': 'AI szuka wejść. Otwarte setupy i świeży track record poniżej.',
    'kpi.active': 'Aktywne',
    'kpi.activeSub': 'w grze',
    'kpi.wait': 'oczekiwanie',
    'kpi.closed': 'Zamknięte',
    'kpi.closedSub': 'wszystkie transakcje',
    'kpi.winrate': 'Winrate',
    'kpi.winrateSub': 'cały okres',
    'kpi.avgPnl': 'Śr. PnL',
    'kpi.avgPnlSub': 'na transakcję',
    'sec.active': 'Aktywne sygnały',
    'sec.recent': 'Ostatnie sygnały',
    'recent.all': 'Pełna historia →',
    'recent.lock': 'Pełna taśma transakcji i PnL — w Premium',
    'recent.unlock': 'Odblokuj Premium →',
    'empty.title': 'Brak sygnałów',
    'empty.desc': 'Skaner AI szuka wejść na rynku. Nowe sygnały pojawią się tutaj.',
    'empty.pulse': 'Skanujemy rynek co kilka minut',
    'load.section': 'Ładowanie sekcji…',
    'load.app': 'Ładowanie…',
    'err.boundary': 'Coś poszło nie tak',
    'err.boundarySub': 'Sekcja nie wczytała się. Odśwież stronę — reszta aplikacji działa.',
    'err.reload': 'Odśwież',
    'err.offline': 'Brak połączenia z serwerem.',
    'hist.title': 'Historia transakcji',
    'ai.title': 'Asystent AI',
  },
}

const I18nContext = createContext(null)

function detectLang() {
  const saved = localStorage.getItem('lang')
  if (saved && MESSAGES[saved]) return saved
  const nav = (navigator.language || 'ru').slice(0, 2).toLowerCase()
  if (MESSAGES[nav]) return nav
  return 'ru'
}

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(detectLang)

  const setLang = (code) => {
    if (!MESSAGES[code]) return
    setLangState(code)
    localStorage.setItem('lang', code)
  }

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const value = useMemo(() => {
    const table = MESSAGES[lang] || MESSAGES.ru
    const t = (key, vars) => {
      let s = table[key] ?? MESSAGES.ru[key] ?? key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          s = s.replaceAll(`{${k}}`, String(v))
        })
      }
      return s
    }
    return { lang, setLang, t, locales: LOCALES }
  }, [lang])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n outside I18nProvider')
  return ctx
}
