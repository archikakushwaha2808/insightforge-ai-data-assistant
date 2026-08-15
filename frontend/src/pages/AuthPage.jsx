import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Check, X } from 'lucide-react'
import { useAuth } from '../theme/AuthContext'

const RULES = [
  { key: 'length', label: 'At least 8 characters', test: (p) => p.length >= 8 },
  { key: 'upper', label: 'One uppercase letter', test: (p) => /[A-Z]/.test(p) },
  { key: 'lower', label: 'One lowercase letter', test: (p) => /[a-z]/.test(p) },
  { key: 'number', label: 'One number', test: (p) => /\d/.test(p) },
  { key: 'special', label: 'One special character (!@#$%…)', test: (p) => /[^\w\s]/.test(p) },
]

export default function AuthPage({ mode = 'login' }) {
  const isLogin = mode === 'login'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showRules, setShowRules] = useState(false)
  const { login, signup } = useAuth()
  const navigate = useNavigate()

  const ruleResults = useMemo(() => RULES.map((r) => ({ ...r, passed: r.test(password) })), [password])
  const allPassed = ruleResults.every((r) => r.passed)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (!isLogin && !allPassed) {
      setError('Please meet all password requirements below.')
      return
    }

    setLoading(true)
    try {
      if (isLogin) {
        await login(email, password)
      } else {
        await signup(email, password, fullName)
      }
      navigate('/dashboard')
    } catch (err) {
      const detail = err.response?.data?.detail
      if (Array.isArray(detail)) {
        setError(detail.map((d) => d.msg).join(' '))
      } else if (detail) {
        setError(detail)
      } else if (err.code === 'ECONNABORTED') {
        setError('The request timed out. Please try again.')
      } else {
        setError(err.message || 'Something went wrong. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-6">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md p-8 rounded-2xl border border-border bg-surface/50"
      >
        <h1 className="font-display text-2xl font-semibold mb-1">
          {isLogin ? 'Welcome back' : 'Create your account'}
        </h1>
        <p className="text-muted text-sm mb-8">
          {isLogin ? 'Sign in to reach your workspace.' : 'Start analyzing data in minutes.'}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {!isLogin && (
            <div>
              <label className="text-xs font-mono uppercase tracking-wider text-muted">Full name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full mt-1.5 px-4 py-3 rounded-xl bg-base/50 border border-border focus:border-signal-cyan outline-none transition-colors"
                placeholder="Jane Doe"
              />
            </div>
          )}
          <div>
            <label className="text-xs font-mono uppercase tracking-wider text-muted">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full mt-1.5 px-4 py-3 rounded-xl bg-base/50 border border-border focus:border-signal-cyan outline-none transition-colors"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="text-xs font-mono uppercase tracking-wider text-muted">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onFocus={() => setShowRules(true)}
              className="w-full mt-1.5 px-4 py-3 rounded-xl bg-base/50 border border-border focus:border-signal-cyan outline-none transition-colors"
              placeholder="••••••••"
            />
          </div>

          {!isLogin && showRules && (
            <ul className="space-y-1.5 pt-1">
              {ruleResults.map((r) => (
                <li key={r.key} className={`flex items-center gap-2 text-xs transition-colors ${r.passed ? 'text-signal-cyan' : 'text-muted'}`}>
                  {r.passed ? <Check size={13} /> : <X size={13} />} {r.label}
                </li>
              ))}
            </ul>
          )}

          {error && <p className="text-sm text-signal-magenta">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 rounded-xl bg-signal-gradient text-black font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? 'Please wait…' : isLogin ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <p className="text-sm text-muted text-center mt-6">
          {isLogin ? "Don't have an account? " : 'Already have an account? '}
          <a href={isLogin ? '/signup' : '/login'} className="text-signal-cyan hover:underline">
            {isLogin ? 'Sign up' : 'Sign in'}
          </a>
        </p>
      </motion.div>
    </div>
  )
}
