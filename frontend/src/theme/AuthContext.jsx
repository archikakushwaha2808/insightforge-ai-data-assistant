import { createContext, useContext, useState, useCallback } from 'react'
import client from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('insightforge-token'))
  const [user, setUser] = useState(null)

  const login = useCallback(async (email, password) => {
    const form = new URLSearchParams()
    form.append('username', email)
    form.append('password', password)
    const res = await client.post('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    localStorage.setItem('insightforge-token', res.data.access_token)
    setToken(res.data.access_token)
    return res.data
  }, [])

  const signup = useCallback(async (email, password, fullName) => {
    const res = await client.post('/auth/signup', { email, password, full_name: fullName })
    localStorage.setItem('insightforge-token', res.data.access_token)
    setToken(res.data.access_token)
    return res.data
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('insightforge-token')
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ token, user, setUser, setToken, login, signup, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
