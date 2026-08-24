import { useState } from 'react';
import { Activity, User, Stethoscope, Shield } from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';

const ROLES = [
  { id: 'patient', label: 'Patient', icon: <User size={20} /> },
  { id: 'doctor', label: 'Doctor', icon: <Stethoscope size={20} /> },
  { id: 'admin', label: 'Admin', icon: <Shield size={20} /> },
];

export default function AuthPage({ onToast }) {
  const { login } = useAuth();
  const [tab, setTab] = useState('login');
  const [loading, setLoading] = useState(false);

  // Login form
  const [loginForm, setLoginForm] = useState({ email: '', password: '' });
  const [loginError, setLoginError] = useState('');

  // Register form
  const [regForm, setRegForm] = useState({
    email: '', password: '', role: 'patient',
    first_name: '', last_name: '', phone: '', whatsapp_number: '',
  });
  const [regError, setRegError] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginError('');
    setLoading(true);
    try {
      const data = await api.auth.login(loginForm.email, loginForm.password);
      login(data);
      onToast('success', 'Welcome back!', `Logged in as ${data.role}`);
    } catch (err) {
      setLoginError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setRegError('');
    if (!regForm.first_name || !regForm.last_name) {
      setRegError('First and last name are required.');
      return;
    }
    setLoading(true);
    try {
      const data = await api.auth.register(regForm);
      login(data);
      onToast('success', 'Account created!', `Welcome to HealthQueue, ${regForm.first_name}!`);
    } catch (err) {
      setRegError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-panel">
        {/* Logo */}
        <div className="auth-logo">
          <div className="auth-logo-icon">
            <Activity size={24} />
          </div>
          <div className="auth-logo-text">
            <h1>HealthQueue</h1>
            <p>Smart Clinical Appointment Manager</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="auth-tabs">
          <button className={`auth-tab ${tab === 'login' ? 'active' : ''}`} onClick={() => setTab('login')}>
            Sign In
          </button>
          <button className={`auth-tab ${tab === 'register' ? 'active' : ''}`} onClick={() => setTab('register')}>
            Create Account
          </button>
        </div>

        {/* Login Form */}
        {tab === 'login' && (
          <form className="auth-form" onSubmit={handleLogin}>
            <div className="form-group">
              <label className="form-label">Email Address</label>
              <input
                id="login-email"
                className="form-input"
                type="email"
                required
                value={loginForm.email}
                onChange={(e) => setLoginForm((p) => ({ ...p, email: e.target.value }))}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                id="login-password"
                className="form-input"
                type="password"
                required
                value={loginForm.password}
                onChange={(e) => setLoginForm((p) => ({ ...p, password: e.target.value }))}
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </div>
            {loginError && <div className="form-error">{loginError}</div>}
            <button id="login-submit" className="btn btn-primary btn-lg w-full" type="submit" disabled={loading}>
              {loading ? <><span className="spinner spinner-sm" /> Signing in…</> : 'Sign In'}
            </button>
          </form>
        )}

        {/* Register Form */}
        {tab === 'register' && (
          <form className="auth-form" onSubmit={handleRegister}>
            {/* Role picker */}
            <div className="form-group">
              <label className="form-label">I am a…</label>
              <div className="role-picker">
                {ROLES.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    className={`role-option ${regForm.role === r.id ? 'selected' : ''}`}
                    onClick={() => setRegForm((p) => ({
                      ...p,
                      role: r.id,
                      admin_secret: (r.id === 'admin' || r.id === 'doctor') ? (p.admin_secret || 'admin2026') : '',
                    }))}
                  >
                    {r.icon}
                    {r.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">First Name</label>
                <input className="form-input" required value={regForm.first_name} onChange={(e) => setRegForm((p) => ({ ...p, first_name: e.target.value }))} placeholder="First name" />
              </div>
              <div className="form-group">
                <label className="form-label">Last Name</label>
                <input className="form-input" required value={regForm.last_name} onChange={(e) => setRegForm((p) => ({ ...p, last_name: e.target.value }))} placeholder="Last name" />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Email Address</label>
              <input className="form-input" type="email" required value={regForm.email} onChange={(e) => setRegForm((p) => ({ ...p, email: e.target.value }))} placeholder="you@example.com" autoComplete="email" />
            </div>
            <div className="form-group">
              <label className="form-label">Password</label>
              <input className="form-input" type="password" required value={regForm.password} onChange={(e) => setRegForm((p) => ({ ...p, password: e.target.value }))} placeholder="At least 8 characters" autoComplete="new-password" />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Phone (optional)</label>
                <input className="form-input" value={regForm.phone} onChange={(e) => setRegForm((p) => ({ ...p, phone: e.target.value }))} placeholder="+91 XXXXX XXXXX" />
              </div>
              <div className="form-group">
                <label className="form-label">WhatsApp (optional)</label>
                <input className="form-input" value={regForm.whatsapp_number} onChange={(e) => setRegForm((p) => ({ ...p, whatsapp_number: e.target.value }))} placeholder="+91 XXXXX XXXXX" />
              </div>
            </div>

            {/* Staff Passcode for Admin / Doctor roles */}
            {(regForm.role === 'admin' || regForm.role === 'doctor') && (
              <div className="form-group">
                <label className="form-label">Staff Security Passcode (Default: admin2026)</label>
                <input
                  className="form-input"
                  type="password"
                  required
                  value={regForm.admin_secret || ''}
                  onChange={(e) => setRegForm((p) => ({ ...p, admin_secret: e.target.value }))}
                  placeholder="Enter staff security passcode"
                  autoComplete="off"
                />
              </div>
            )}

            {regError && <div className="form-error">{regError}</div>}
            <button id="register-submit" className="btn btn-primary btn-lg w-full" type="submit" disabled={loading}>
              {loading ? <><span className="spinner spinner-sm" /> Creating account…</> : 'Create Account'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
