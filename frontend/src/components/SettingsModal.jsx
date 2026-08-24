import { useState } from 'react';
import {
  User, Mail, Phone, MessageSquare, Moon, Sun,
  Bell, BellOff, Wifi, WifiOff, Shield, ChevronRight
} from 'lucide-react';
import Modal from './Modal';
import { useAuth } from '../context/AuthContext';

export default function SettingsModal({ onClose, darkMode, onToggleDark, onToast }) {
  const { user } = useAuth();
  const [tab, setTab] = useState('profile');

  // Profile form state — seeded from localStorage if available
  const [profile, setProfile] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('hq_profile') || '{}');
    } catch {
      return {};
    }
  });

  const [notifs, setNotifs] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('hq_notifs') || '{"whatsapp":true,"email":true}');
    } catch {
      return { whatsapp: true, email: true };
    }
  });

  const handleProfileSave = () => {
    localStorage.setItem('hq_profile', JSON.stringify(profile));
    onToast('success', 'Profile saved', 'Your profile has been updated.');
    onClose();
  };

  const toggleNotif = (key) => {
    const updated = { ...notifs, [key]: !notifs[key] };
    setNotifs(updated);
    localStorage.setItem('hq_notifs', JSON.stringify(updated));
  };

  const tabs = [
    { id: 'profile', label: 'Profile' },
    { id: 'notifications', label: 'Notifications' },
    { id: 'appearance', label: 'Appearance' },
    { id: 'system', label: 'System' },
  ];

  return (
    <Modal
      title="Settings & Profile"
      subtitle="Manage your account and preferences"
      onClose={onClose}
      footer={
        tab === 'profile' ? (
          <>
            <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button className="btn btn-primary" onClick={handleProfileSave}>Save Changes</button>
          </>
        ) : (
          <button className="btn btn-secondary" onClick={onClose}>Close</button>
        )
      }
    >
      {/* Tabs */}
      <div className="flex gap-2" style={{ borderBottom: '1px solid var(--border)', marginBottom: 20, paddingBottom: 4 }}>
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className="btn btn-ghost btn-sm"
            style={tab === t.id ? { color: 'var(--primary)', borderBottom: '2px solid var(--primary)', borderRadius: 0 } : {}}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Profile Tab */}
      {tab === 'profile' && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3" style={{ background: 'var(--bg-sidebar)', padding: '16px', borderRadius: 'var(--radius-lg)' }}>
            <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'linear-gradient(135deg, var(--primary), #60a5fa)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '1.25rem', fontWeight: 700 }}>
              {(profile.first_name?.[0] || user?.role?.[0] || 'U').toUpperCase()}
            </div>
            <div>
              <div className="font-600">{profile.first_name ? `${profile.first_name} ${profile.last_name || ''}` : 'Your Name'}</div>
              <div className="text-sm text-muted">Role: {user?.role || '—'} · ID: {user?.id || '—'}</div>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">First Name</label>
              <input className="form-input" value={profile.first_name || ''} onChange={e => setProfile(p => ({ ...p, first_name: e.target.value }))} placeholder="First name" />
            </div>
            <div className="form-group">
              <label className="form-label">Last Name</label>
              <input className="form-input" value={profile.last_name || ''} onChange={e => setProfile(p => ({ ...p, last_name: e.target.value }))} placeholder="Last name" />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Email Address</label>
            <input className="form-input" type="email" value={profile.email || ''} onChange={e => setProfile(p => ({ ...p, email: e.target.value }))} placeholder="you@example.com" />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Phone Number</label>
              <input className="form-input" value={profile.phone || ''} onChange={e => setProfile(p => ({ ...p, phone: e.target.value }))} placeholder="+91 XXXXX XXXXX" />
            </div>
            <div className="form-group">
              <label className="form-label">WhatsApp Number</label>
              <input className="form-input" value={profile.whatsapp || ''} onChange={e => setProfile(p => ({ ...p, whatsapp: e.target.value }))} placeholder="+91 XXXXX XXXXX" />
            </div>
          </div>
        </div>
      )}

      {/* Notifications Tab */}
      {tab === 'notifications' && (
        <div className="settings-section">
          <div className="settings-label">Notification Channels</div>
          <div className="settings-item" onClick={() => toggleNotif('whatsapp')}>
            <div className="settings-item-left">
              <span className="settings-item-icon"><MessageSquare size={18} /></span>
              <div className="settings-item-info">
                <h4>WhatsApp Alerts</h4>
                <p>Real-time queue delay updates and token approach pings</p>
              </div>
            </div>
            <button className={`toggle ${notifs.whatsapp ? 'on' : ''}`} />
          </div>
          <div className="settings-item" onClick={() => toggleNotif('email')}>
            <div className="settings-item-left">
              <span className="settings-item-icon"><Mail size={18} /></span>
              <div className="settings-item-info">
                <h4>Email Notifications</h4>
                <p>Booking confirmations, post-visit reports, cancellations</p>
              </div>
            </div>
            <button className={`toggle ${notifs.email ? 'on' : ''}`} />
          </div>
        </div>
      )}

      {/* Appearance Tab */}
      {tab === 'appearance' && (
        <div className="settings-section">
          <div className="settings-label">Theme</div>
          <div className="settings-item" onClick={onToggleDark}>
            <div className="settings-item-left">
              <span className="settings-item-icon">{darkMode ? <Moon size={18} /> : <Sun size={18} />}</span>
              <div className="settings-item-info">
                <h4>{darkMode ? 'Dark Mode' : 'Light Mode'}</h4>
                <p>Click to switch to {darkMode ? 'light' : 'dark'} mode</p>
              </div>
            </div>
            <div className={`toggle ${darkMode ? 'on' : ''}`} />
          </div>
        </div>
      )}

      {/* System Tab */}
      {tab === 'system' && (
        <div className="flex flex-col gap-3">
          <div className="settings-label">System Information</div>
          <div style={{ background: 'var(--bg-sidebar)', borderRadius: 'var(--radius-lg)', padding: 16, display: 'flex', flexDirection: 'column', gap: 10, fontSize: 'var(--text-sm)' }}>
            <div className="flex justify-between"><span className="text-muted">Backend API</span><code style={{ fontSize: 'var(--text-xs)', color: 'var(--primary)' }}>http://localhost:8000</code></div>
            <div className="divider" />
            <div className="flex justify-between"><span className="text-muted">Version</span><span>0.1.0</span></div>
            <div className="divider" />
            <div className="flex justify-between"><span className="text-muted">User ID</span><span>{user?.id || '—'}</span></div>
            <div className="divider" />
            <div className="flex justify-between"><span className="text-muted">Role</span><span className={`badge badge-${user?.role === 'admin' ? 'warning' : user?.role === 'doctor' ? 'success' : 'regular'}`}>{user?.role || '—'}</span></div>
          </div>
          <div className="info-banner info" style={{ marginTop: 4 }}>
            <Shield size={16} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>Your session is protected with JWT tokens. Tokens expire after 30 minutes of inactivity.</span>
          </div>

          <div style={{ marginTop: 8 }}>
            <button
              className="btn btn-secondary w-full"
              type="button"
              onClick={async () => {
                try {
                  const res = await (await import('../services/api')).api.admin.seedDemo();
                  onToast('success', 'Demo data loaded!', res.message);
                } catch (err) {
                  onToast('error', 'Seeding failed', err.message);
                }
              }}
            >
              ⚡ Load Clinical Demo Data
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
