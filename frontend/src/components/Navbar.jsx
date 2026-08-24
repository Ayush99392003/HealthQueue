import { Activity, Sun, Moon, Settings, LogOut, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function Navbar({ darkMode, onToggleDark, onOpenSettings }) {
  const { user, logout } = useAuth();

  const roleLabel = user?.role
    ? user.role.charAt(0).toUpperCase() + user.role.slice(1)
    : '';

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <div className="navbar-brand-icon">
          <Activity size={20} />
        </div>
        <div>
          <div className="navbar-brand-name">HealthQueue</div>
          <div className="navbar-brand-sub">Smart Clinical Manager</div>
        </div>
      </div>

      <div className="navbar-right">
        {user && (
          <span className={`navbar-role-badge ${user.role}`}>
            {roleLabel}
          </span>
        )}

        <button
          className="btn btn-ghost btn-icon"
          onClick={onToggleDark}
          title={darkMode ? 'Light mode' : 'Dark mode'}
        >
          {darkMode ? <Sun size={18} /> : <Moon size={18} />}
        </button>

        {user && (
          <>
            <button
              className="btn btn-ghost btn-icon"
              onClick={onOpenSettings}
              title="Settings & Profile"
            >
              <Settings size={18} />
            </button>

            <button
              className="btn btn-ghost btn-icon"
              onClick={logout}
              title="Logout"
            >
              <LogOut size={18} />
            </button>
          </>
        )}
      </div>
    </nav>
  );
}
