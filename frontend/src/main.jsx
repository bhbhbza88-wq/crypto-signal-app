import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { I18nProvider, useI18n } from './i18n'
import './index.css'

const Landing = lazy(() => import('./Landing.jsx'))
const App = lazy(() => import('./App.jsx'))
const VerifyEmailPage = lazy(() =>
  import('./AuthPages.jsx').then((m) => ({ default: m.VerifyEmailPage })),
)
const ResetPasswordPage = lazy(() =>
  import('./AuthPages.jsx').then((m) => ({ default: m.ResetPasswordPage })),
)

function Boot() {
  const { t } = useI18n()
  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', color: 'var(--text-tertiary)', fontFamily: 'var(--font-ui)' }}>
      {t('load.app')}
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <I18nProvider>
      <BrowserRouter>
        <Suspense fallback={<Boot />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/app" element={<Navigate to="/app/overview" replace />} />
            <Route path="/app/:section" element={<App />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </I18nProvider>
  </React.StrictMode>,
)
