/**
 * Yandex Metrika (primary analytics for RU/PL audience).
 * Set VITE_METRIKA_ID to the numeric counter ID from metrika.yandex.ru.
 * When unset, all helpers are no-ops (safe for local/dev).
 */

const RAW_ID = (import.meta.env.VITE_METRIKA_ID || '').trim()
const METRIKA_ID = /^\d+$/.test(RAW_ID) ? Number(RAW_ID) : null

let initialized = false

export function isAnalyticsEnabled() {
  return METRIKA_ID != null
}

export function initAnalytics() {
  if (!METRIKA_ID || initialized || typeof window === 'undefined') return
  initialized = true

  ;(function (m, e, t, r, i, k, a) {
    m[i] =
      m[i] ||
      function () {
        ;(m[i].a = m[i].a || []).push(arguments)
      }
    m[i].l = 1 * new Date()
    for (let j = 0; j < document.scripts.length; j++) {
      if (document.scripts[j].src === r) return
    }
    k = e.createElement(t)
    a = e.getElementsByTagName(t)[0]
    k.async = 1
    k.src = r
    a.parentNode.insertBefore(k, a)
  })(window, document, 'script', 'https://mc.yandex.ru/metrika/tag.js', 'ym')

  window.ym(METRIKA_ID, 'init', {
    clickmap: true,
    trackLinks: true,
    accurateTrackBounce: true,
    webvisor: true,
  })
}

/** SPA route change (skip first paint — init already counts it). */
export function trackPageView(pathWithSearch) {
  if (!METRIKA_ID || typeof window.ym !== 'function') return
  const url = pathWithSearch.startsWith('http')
    ? pathWithSearch
    : `${window.location.origin}${pathWithSearch}`
  window.ym(METRIKA_ID, 'hit', url, { title: document.title })
}

/** Named goal — create matching goals in Metrika UI (or rely on auto params). */
export function trackEvent(goal, params) {
  if (!METRIKA_ID || typeof window.ym !== 'function') return
  if (params && typeof params === 'object') {
    window.ym(METRIKA_ID, 'reachGoal', goal, params)
  } else {
    window.ym(METRIKA_ID, 'reachGoal', goal)
  }
}

export const Goals = {
  pricingClick: 'pricing_click',
  telegramBot: 'telegram_bot_click',
  login: 'login',
  register: 'register',
}
