import { useState } from 'react';
import { authAPI } from '../services/api';
import { GraduationCap, ShieldAlert, Key, Mail, Lock, User, CheckCircle, ArrowRight } from 'lucide-react';

export default function Login({ onLoginSuccess, onRegisterClick }) {
  const [dni, setDni] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Estados de flujo alternativos
  const [view, setView] = useState('login'); // 'login', 'recovery', 'change_password'
  
  // Datos para cambio de clave obligatorio
  const [tempUser, setTempUser] = useState(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  
  // Datos para recuperación
  const [recoveryEmail, setRecoveryEmail] = useState('');
  const [recoverySuccess, setRecoverySuccess] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!dni || !password) {
      setError('Por favor complete todos los campos.');
      return;
    }
    
    setError('');
    setLoading(true);
    try {
      const data = await authAPI.login(dni, password);
      const { access_token, user } = data;
      
      // Guardar token temporalmente
      localStorage.setItem('token', access_token);
      
      if (user.primer_ingreso) {
        setTempUser(user);
        setView('change_password');
      } else {
        localStorage.setItem('user', JSON.stringify(user));
        onLoginSuccess(user);
      }
    } catch (err) {
      localStorage.removeItem('token');
      setError(err.response?.data?.detail || 'DNI o contraseña incorrectos.');
    } finally {
      setLoading(false);
    }
  };

  const handleChangePasswordSubmit = async (e) => {
    e.preventDefault();
    if (!newPassword || !confirmPassword) {
      setError('Por favor complete todos los campos.');
      return;
    }
    if (newPassword.length < 6) {
      setError('La nueva contraseña debe tener al menos 6 caracteres.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Las contraseñas no coinciden.');
      return;
    }

    setError('');
    setLoading(true);
    try {
      await authAPI.changePassword(password, newPassword);
      
      // Contraseña cambiada, ahora guardamos el usuario definitivo y logueamos
      const updatedUser = { ...tempUser, primer_ingreso: false };
      localStorage.setItem('user', JSON.stringify(updatedUser));
      onLoginSuccess(updatedUser);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al cambiar la contraseña. Intente nuevamente.');
    } finally {
      setLoading(false);
    }
  };

  const handleRecoverySubmit = async (e) => {
    e.preventDefault();
    if (!dni || !recoveryEmail) {
      setError('Por favor complete todos los campos.');
      return;
    }

    setError('');
    setRecoverySuccess('');
    setLoading(true);
    try {
      const res = await authAPI.recover(dni, recoveryEmail);
      setRecoverySuccess(res.message || 'Se ha enviado la contraseña temporal a su correo electrónico.');
      setDni('');
      setRecoveryEmail('');
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo procesar la solicitud de recuperación.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, hsl(220, 85%, 15%) 0%, hsl(220, 85%, 25%) 50%, hsl(220, 85%, 35%) 100%)',
      padding: '2rem',
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Elementos Decorativos de Fondo */}
      <div style={{
        position: 'absolute',
        top: '-10%',
        left: '-10%',
        width: '400px',
        height: '400px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, var(--accent-glow) 0%, transparent 70%)',
        pointerEvents: 'none'
      }}></div>
      <div style={{
        position: 'absolute',
        bottom: '-10%',
        right: '-10%',
        width: '500px',
        height: '500px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(255,255,255,0.05) 0%, transparent 70%)',
        pointerEvents: 'none'
      }}></div>

      <div className="card animate-fade-in-up" style={{
        maxWidth: '450px',
        width: '100%',
        padding: '2.5rem',
        borderRadius: 'var(--radius-lg)',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
        border: 'none',
        backgroundColor: 'rgba(255, 255, 255, 0.98)',
        backdropFilter: 'blur(10px)'
      }}>
        {/* Encabezado */}
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '64px',
            height: '64px',
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'var(--primary-glow)',
            color: 'var(--primary)',
            marginBottom: '1rem'
          }}>
            <GraduationCap size={36} />
          </div>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--primary)', letterSpacing: '-0.5px' }}>
            UNdeC
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', fontWeight: 500 }}>
            {view === 'login' && 'Portal de Preinscripción a Distancia'}
            {view === 'recovery' && 'Recuperación de Contraseña'}
            {view === 'change_password' && 'Cambio Obligatorio de Contraseña'}
          </p>
        </div>

        {error && (
          <div className="alert alert-danger" style={{ marginBottom: '1.5rem' }}>
            <ShieldAlert size={20} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        {recoverySuccess && (
          <div className="alert alert-success" style={{ marginBottom: '1.5rem' }}>
            <CheckCircle size={20} style={{ flexShrink: 0 }} />
            <span>{recoverySuccess}</span>
          </div>
        )}

        {/* Vista: LOGIN ESTÁNDAR */}
        {view === 'login' && (
          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label className="form-label" htmlFor="login-dni">DNI</label>
              <div style={{ position: 'relative' }}>
                <User size={18} style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-muted)'
                }} />
                <input
                  id="login-dni"
                  type="text"
                  className="form-control"
                  style={{ paddingLeft: '2.5rem' }}
                  placeholder="Ingrese su DNI sin puntos"
                  value={dni}
                  onChange={(e) => setDni(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                <label className="form-label" htmlFor="login-password" style={{ marginBottom: 0 }}>Contraseña</label>
                <button
                  type="button"
                  onClick={() => { setView('recovery'); setError(''); }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--primary-light)',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    textDecoration: 'underline'
                  }}
                >
                  ¿Olvidó su contraseña?
                </button>
              </div>
              <div style={{ position: 'relative' }}>
                <Lock size={18} style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-muted)'
                }} />
                <input
                  id="login-password"
                  type="password"
                  className="form-control"
                  style={{ paddingLeft: '2.5rem' }}
                  placeholder="Ingrese su clave temporal"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', padding: '0.8rem', marginTop: '1rem' }}
              disabled={loading}
            >
              {loading ? <div className="spinner" /> : (
                <>
                  Ingresar al Portal <ArrowRight size={18} />
                </>
              )}
            </button>
            <div style={{ textAlign: 'center', marginTop: '1.25rem' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                ¿No tienes cuenta?{' '}
                <button
                  type="button"
                  onClick={onRegisterClick}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--primary)',
                    fontWeight: 700,
                    cursor: 'pointer',
                    textDecoration: 'underline',
                    padding: 0
                  }}
                >
                  Preinscríbete aquí
                </button>
              </span>
            </div>
          </form>
        )}

        {/* Vista: RECOVERY */}
        {view === 'recovery' && (
          <form onSubmit={handleRecoverySubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="recovery-dni">DNI</label>
              <div style={{ position: 'relative' }}>
                <User size={18} style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-muted)'
                }} />
                <input
                  id="recovery-dni"
                  type="text"
                  className="form-control"
                  style={{ paddingLeft: '2.5rem' }}
                  placeholder="Ingrese su DNI"
                  value={dni}
                  onChange={(e) => setDni(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="recovery-email">Correo Electrónico</label>
              <div style={{ position: 'relative' }}>
                <Mail size={18} style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-muted)'
                }} />
                <input
                  id="recovery-email"
                  type="email"
                  className="form-control"
                  style={{ paddingLeft: '2.5rem' }}
                  placeholder="ejemplo@correo.com"
                  value={recoveryEmail}
                  onChange={(e) => setRecoveryEmail(e.target.value)}
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', padding: '0.8rem', marginTop: '1.25rem' }}
              disabled={loading}
            >
              {loading ? <div className="spinner" /> : 'Generar Nueva Contraseña'}
            </button>

            <button
              type="button"
              className="btn btn-secondary"
              style={{ width: '100%', padding: '0.8rem', marginTop: '0.75rem' }}
              onClick={() => { setView('login'); setError(''); }}
              disabled={loading}
            >
              Volver al inicio
            </button>
          </form>
        )}

        {/* Vista: CAMBIO OBLIGATORIO DE CONTRASEÑA */}
        {view === 'change_password' && (
          <form onSubmit={handleChangePasswordSubmit}>
            <div className="alert alert-warning">
              <Key size={20} style={{ flexShrink: 0 }} />
              <span>Por seguridad, al ingresar por primera vez debe cambiar su contraseña temporal.</span>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="new-password">Nueva Contraseña</label>
              <div style={{ position: 'relative' }}>
                <Lock size={18} style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-muted)'
                }} />
                <input
                  id="new-password"
                  type="password"
                  className="form-control"
                  style={{ paddingLeft: '2.5rem' }}
                  placeholder="Mínimo 6 caracteres"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="confirm-password">Confirmar Contraseña</label>
              <div style={{ position: 'relative' }}>
                <Lock size={18} style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-muted)'
                }} />
                <input
                  id="confirm-password"
                  type="password"
                  className="form-control"
                  style={{ paddingLeft: '2.5rem' }}
                  placeholder="Repita su nueva contraseña"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', padding: '0.8rem', marginTop: '1.25rem' }}
              disabled={loading}
            >
              {loading ? <div className="spinner" /> : 'Confirmar y Entrar'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
