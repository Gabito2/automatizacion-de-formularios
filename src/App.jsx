import { useState, useEffect } from 'react'
import Login from './pages/Login'
import EstudianteDashboard from './pages/EstudianteDashboard'
import AdminDashboard from './pages/AdminDashboard'
import Preinscripcion from './pages/Preinscripcion'

function App() {
  const [user, setUser] = useState(null)
  const [checkingSession, setCheckingSession] = useState(true)
  const [showRegister, setShowRegister] = useState(false)

  useEffect(() => {
    // Verificar si hay una sesión activa guardada
    const savedUser = localStorage.getItem('user')
    const token = localStorage.getItem('token')
    if (savedUser && token) {
      try {
        setUser(JSON.parse(savedUser))
      } catch {
        localStorage.removeItem('user')
        localStorage.removeItem('token')
      }
    }
    setCheckingSession(false)
  }, [])

  const handleLoginSuccess = (loggedInUser) => {
    setUser(loggedInUser)
  }

  const handleLogout = () => {
    localStorage.removeItem('user')
    localStorage.removeItem('token')
    setUser(null)
  }

  if (checkingSession) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f8fafc',
        fontFamily: 'sans-serif'
      }}>
        <div style={{ textAlign: 'center' }}>
          <h3>Cargando sistema...</h3>
        </div>
      </div>
    )
  }

  if (!user) {
    if (showRegister) {
      return <Preinscripcion onBackToLogin={() => setShowRegister(false)} />
    }
    return <Login onLoginSuccess={handleLoginSuccess} />
  }

  if (user.rol === 'administrador' || user.rol === 'validador') {
    return <AdminDashboard user={user} onLogout={handleLogout} />
  }

  const handleUpdateUser = (updatedUser) => {
    localStorage.setItem('user', JSON.stringify(updatedUser))
    setUser(updatedUser)
  }

  // Por defecto, rol de estudiante
  return <EstudianteDashboard user={user} onLogout={handleLogout} onUpdateUser={handleUpdateUser} />
}

export default App

