import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { getBasicAuth, requestCredentials, setBasicAuth } from './auth.js'
import './index.css'

// The dashboard is a static shell with no sign-in screen, so this gate supplies
// the credentials the API asks for. It appears only when a request comes back
// 401, and disappears once they are stored.
function LoginGate({ onSuccess }) {
  const [user, setUser] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setError(null)
    setBusy(true)
    const header = `Basic ${btoa(`${user.trim()}:${password}`)}`
    try {
      const response = await fetch('/api/state', { headers: { Authorization: header } })
      if (response.ok) {
        setBasicAuth(user.trim(), password)
        onSuccess()
        return
      }
      setError(response.status === 401 ? 'Invalid username or password.' : `Sign-in failed (${response.status}).`)
    } catch {
      setError('Could not reach the server. Check your connection.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-sm"
      >
        <h1 className="text-lg font-semibold text-ink-900">Sign in</h1>
        <p className="mt-1 text-[13px] text-ink-500">
          This workspace is protected. Enter the dashboard credentials.
        </p>

        <label className="mt-5 block text-[12px] font-medium text-ink-600">
          Username
          <input
            autoFocus
            value={user}
            onChange={(e) => setUser(e.target.value)}
            className="mt-1 w-full rounded-md border border-border px-3 py-2 text-[13px]"
            autoComplete="username"
          />
        </label>

        <label className="mt-3 block text-[12px] font-medium text-ink-600">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-border px-3 py-2 text-[13px]"
            autoComplete="current-password"
          />
        </label>

        {error && <p className="mt-3 text-[12px] text-danger-600">{error}</p>}

        <button type="submit" disabled={busy} className="btn-primary btn mt-5 w-full">
          {busy ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

function Root() {
  const [needsAuth, setNeedsAuth] = useState(() => !getBasicAuth())

  useEffect(() => {
    const handler = () => setNeedsAuth(true)
    window.addEventListener('mailmatrix:auth-required', handler)
    return () => window.removeEventListener('mailmatrix:auth-required', handler)
  }, [])

  if (needsAuth) {
    return (
      <LoginGate
        onSuccess={() => {
          setNeedsAuth(false)
          // Remount the app so every request picks up the new credentials.
          window.location.reload()
        }}
      />
    )
  }

  return <App />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)