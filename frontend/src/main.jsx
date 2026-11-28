import React, { useCallback, useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import LoginPage from './LoginPage.jsx'
import LandingPage from './LandingPage.jsx'
import { authHeader, clearSession, getLastUser, getSession, setSession } from './auth.js'
import './index.css'

// The app is a static SPA, so routing is the URL plus the History API. Keeping
// it this small avoids pulling in a router for three screens.
const normalize = (path) => {
  const clean = (path || '/').replace(/\/+$/, '')
  return clean || '/'
}

function useRoute() {
  const [path, setPath] = useState(() => normalize(window.location.pathname))

  useEffect(() => {
    const onPop = () => {
      setPath(normalize(window.location.pathname))
      window.scrollTo(0, 0)
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((to) => {
    const next = normalize(to)
    if (next !== normalize(window.location.pathname)) {
      window.history.pushState({}, '', next)
    }
    setPath(next)
    window.scrollTo(0, 0)
  }, [])

  return [path, navigate]
}

function Root() {
  const [path, navigate] = useRoute()
  const [session, setSessionState] = useState(() => getSession())
  const [verifying, setVerifying] = useState(() => Boolean(getSession()))
  const [reason, setReason] = useState(null)
  const [demoBusy, setDemoBusy] = useState(false)

  const isLogin = path === '/login'
  const isApp = path === '/app' || path.startsWith('/app/')

  // A stored session is verified once, so an expired or cleared credential
  // lands on the sign-in page instead of an empty dashboard.
  useEffect(() => {
    if (!session) {
      setVerifying(false)
      return undefined
    }
    let cancelled = false
    setVerifying(true)
    fetch('/api/state', { headers: { Authorization: authHeader() } })
      .then((response) => {
        if (cancelled || response.status !== 401) return
        clearSession()
        setSessionState(null)
        setReason('Your session expired. Sign in again to continue.')
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setVerifying(false)
      })
    return () => {
      cancelled = true
    }
  }, [session])

  // The API wrapper emits this when a request is rejected.
  useEffect(() => {
    const handler = () => {
      clearSession()
      setSessionState(null)
      setReason('Your session expired. Sign in again to continue.')
      navigate('/login')
    }
    window.addEventListener('mailmatrix:auth-required', handler)
    return () => window.removeEventListener('mailmatrix:auth-required', handler)
  }, [navigate])

  // Already signed in: /login is a dead end, send them to the product.
  useEffect(() => {
    if (isLogin && session && !verifying) navigate('/app')
  }, [isLogin, session, verifying, navigate])

  const openDemo = async () => {
    if (demoBusy) return
    setDemoBusy(true)
    try {
      const response = await fetch('/api/auth/demo', { method: 'POST' })
      if (!response.ok) throw new Error(`Demo unavailable (${response.status})`)
      const data = await response.json()
      if (!data.access_token) throw new Error('Demo unavailable')
      setSession({ token: data.access_token }, true)
      setSessionState(getSession())
      setReason(null)
      navigate('/app')
    } catch (error) {
      setReason(error?.message || 'The demo workspace could not be opened.')
      navigate('/login')
    } finally {
      setDemoBusy(false)
    }
  }

  const handleSignedIn = ({ token, user, password, remember }) => {
    setSession(token ? { token } : { user, password }, remember !== false)
    setSessionState(getSession())
    setReason(null)
    navigate('/app')
  }

  if (verifying) return <div className="min-h-screen bg-ink-50" />

  if (isApp && !session) {
    return (
      <LoginPage
        initialUser={getLastUser()}
        reason={reason || 'Sign in to open the control centre.'}
        onSuccess={handleSignedIn}
        onDemo={openDemo}
        demoBusy={demoBusy}
        onHome={() => navigate('/')}
      />
    )
  }

  if (isLogin) {
    return (
      <LoginPage
        initialUser={getLastUser()}
        reason={reason}
        onSuccess={handleSignedIn}
        onDemo={openDemo}
        demoBusy={demoBusy}
        onHome={() => navigate('/')}
      />
    )
  }

  if (isApp && session) {
    return <App />
  }

  return (
    <LandingPage
      onSignIn={() => navigate('/login')}
      onStart={() => navigate('/login')}
      onDemo={openDemo}
    />
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)