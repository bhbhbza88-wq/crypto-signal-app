import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { initAnalytics, trackPageView } from './analytics'

/**
 * Loads Metrika once and sends hit() on every client-side route change.
 */
export default function AnalyticsListener() {
  const location = useLocation()
  const isFirst = useRef(true)

  useEffect(() => {
    initAnalytics()
  }, [])

  useEffect(() => {
    if (isFirst.current) {
      isFirst.current = false
      return
    }
    trackPageView(`${location.pathname}${location.search}`)
  }, [location.pathname, location.search])

  return null
}
