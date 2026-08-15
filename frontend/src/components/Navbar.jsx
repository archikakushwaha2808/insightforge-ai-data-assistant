import { Link, useNavigate } from 'react-router-dom'
import { Moon, Sun, Sparkles, LogOut } from 'lucide-react'
import { useTheme } from '../theme/ThemeContext'
import { useAuth } from '../theme/AuthContext'

export default function Navbar() {
  const { isDark, toggleTheme } = useTheme()
  const { isAuthenticated, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <header
      className="sticky top-0 z-50 border-b backdrop-blur-xl transition-colors"
      style={{
        borderColor: isDark ? 'rgba(231,234,243,0.08)' : 'rgba(20,24,38,0.08)',
        backgroundColor: isDark ? 'rgba(10,14,26,0.7)' : 'rgba(246,247,251,0.7)',
      }}
    >
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 group">
          <Sparkles size={20} className="text-signal-cyan group-hover:rotate-12 transition-transform" />
          <span className="font-display font-semibold text-lg tracking-tight">
            Insight<span className="text-gradient">Forge</span>
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-8 font-body text-sm text-muted">
          <Link to="/dashboard" className="hover:text-ink dark:hover:text-ink transition-colors">Workspace</Link>
          <Link to="/chat" className="hover:text-ink transition-colors">Assistant</Link>
        </nav>

        <div className="flex items-center gap-3">
          <button
            onClick={toggleTheme}
            aria-label="Toggle color theme"
            className="w-9 h-9 rounded-full flex items-center justify-center border border-border hover:border-signal-cyan transition-colors"
          >
            {isDark ? <Sun size={16} /> : <Moon size={16} />}
          </button>

          {isAuthenticated ? (
            <button
              onClick={() => { logout(); navigate('/') }}
              className="flex items-center gap-1.5 text-sm font-medium px-4 py-2 rounded-full border border-border hover:border-signal-magenta transition-colors"
            >
              <LogOut size={14} /> Sign out
            </button>
          ) : (
            <Link
              to="/login"
              className="text-sm font-medium px-5 py-2 rounded-full bg-signal-gradient text-black hover:opacity-90 transition-opacity"
            >
              Sign in
            </Link>
          )}
        </div>
      </div>
    </header>
  )
}
