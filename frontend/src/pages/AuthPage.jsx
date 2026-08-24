import { useState } from 'react';
import { Activity, User, Stethoscope, Shield, Zap, Lock } from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';

const ROLES = [
  { id: 'patient', label: 'Patient', icon: <User size={20} /> },
  { id: 'doctor', label: 'Doctor', icon: <Stethoscope size={20} /> },
  { id: 'admin', label: 'Admin', icon: <Shield size={20} /> },
];

const DEMO_ACCOUNTS = [
  {
    role: 'patient',
    label: 'Patient',
    name: 'Rahul Verma',
    email: 'rahul@example.com',
    password: 'Password123!',
    Icon: User,
    gradient: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)',
    description: 'Book appointments, track live queue position, AI symptom triage',
    badge: 'Token #7 • Waiting',
    badgeColor: '#3b82f6',
  },
  {
    role: 'doctor',
    label: 'Doctor',
    name: 'Dr. Priya Sharma',
    email: 'dr.sharma@clinic.com',
    password: 'Password123!',
    Icon: Stethoscope,
    gradient: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
    description: 'View queue, complete consultations, add clinical notes',
    badge: 'Cardiology • 12 Waiting',
    badgeColor: '#10b981',
  },
  {
    role: 'admin',
    label: 'Admin',
    name: 'System Admin',
    email: 'admin@clinic.com',
    password: 'Password123!',
    Icon: Shield,
    gradient: 'linear-gradient(135deg, #f59e0b 0%, #ef4444 100%)',
    description: 'System stats, doctor management, leave & reschedule control',
    badge: 'All Access',
    badgeColor: '#f59e0b',
  },
];

export default function AuthPage({ onToast }) {
  const { login } = useAuth();
  const [tab, setTab] = useState('login');
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(null);

  const [loginForm, setLoginForm] = useState({ email: '', password: '' });
  const [loginError, setLoginError] = useState('');

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

  const handleDemoLogin = async (account) => {
    setDemoLoading(account.role);
    setLoginError('');
    try {
      const data = await api.auth.login(account.email, account.password);
      login(data);
      onToast('success', `Welcome, ${account.name}!`, `Demo ${account.label} session started`);
    } catch {
      // Demo data may not be seeded yet — pre-fill login form for manual entry
      setTab('login');
      setLoginForm({ email: account.email, password: account.password });
      setLoginError(`Demo account not found. Use: ${account.email} / ${account.password}  — or ask admin to run /api/v1/admin/seed-demo`);
    } finally {
      setDemoLoading(null);
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
      <div className="auth-panel auth-panel-wide">
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

        {/* ── QUICK DEMO ACCESS ── */}
        <div className="demo-section">
          <div className="demo-section-label">
            <Zap size={13} />
            <span>Quick Demo Access</span>
            <span className="demo-section-hint">Click any card to sign in instantly</span>
          </div>
          <div className="demo-cards">
            {DEMO_ACCOUNTS.map((account) => {
              const { Icon } = account;
              const isLoading = demoLoading === account.role;
              return (
                <button
                  key={account.role}
                  id={`demo-${account.role}`}
                  className="demo-card"
                  onClick={() => handleDemoLogin(account)}
                  disabled={demoLoading !== null}
                  aria-label={`Sign in as demo ${account.label}`}
                >
                  <div className="demo-card-header">
                    <div className="demo-card-avatar" style={{ background: account.gradient }}>
                      {isLoading ? <span className="spinner spinner-sm" /> : <Icon size={17} />}
                    </div>
                    <span className="demo-card-badge" style={{ background: account.badgeColor + '22', color: account.badgeColor }}>
                      {account.badge}
                    </span>
                  </div>
                  <div className="demo-card-role">{account.label}</div>
                  <div className="demo-card-name">{account.name}</div>
                  <p className="demo-card-desc">{account.description}</p>
                  <div className="demo-card-email">
                    <Lock size={9} />
                    <span>{account.email}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="auth-or-divider"><span>or sign in manually</span></div>

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
