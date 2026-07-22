/**
 * Sentry error tracking. Set VITE_SENTRY_DSN from sentry.io.
 * When unset, helpers are no-ops (safe for local/dev).
 */
import * as Sentry from '@sentry/react'

const DSN = (import.meta.env.VITE_SENTRY_DSN || '').trim()

export function initSentry() {
  if (!DSN || typeof window === 'undefined') return
  Sentry.init({
    dsn: DSN,
    environment: (import.meta.env.VITE_SENTRY_ENVIRONMENT || 'production').trim() || 'production',
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE || 0.1) || 0.1,
    integrations: [Sentry.browserTracingIntegration()],
  })
}

export const SentryErrorBoundary = Sentry.ErrorBoundary
export { Sentry }
