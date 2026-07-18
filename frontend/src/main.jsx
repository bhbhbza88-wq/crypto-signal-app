import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
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
  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', color: 'var(--text-tertiary)', fontFamily: 'var(--font-ui)' }}>
      Загрузка…
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
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
  </React.StrictMode>,
)
