import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './theme/AuthContext'
import Navbar from './components/Navbar'
import Landing from './pages/Landing'
import AuthPage from './pages/AuthPage'
import Workspace from './pages/Workspace'
import ChatPage from './pages/ChatPage'

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? children : <Navigate to="/login" replace />
}

function AppRoutes() {
  return (
    <div className="min-h-screen font-body">
      <Navbar />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />
        <Route path="/dashboard" element={<ProtectedRoute><Workspace /></ProtectedRoute>} />
        <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
      </Routes>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
