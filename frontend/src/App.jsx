import { useState, useCallback } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import Navbar from './components/Navbar';
import { ToastContainer, makeToast } from './components/Toast';
import SettingsModal from './components/SettingsModal';
import AuthPage from './pages/AuthPage';
import PatientPortal from './pages/PatientPortal';
import DoctorDashboard from './pages/DoctorDashboard';
import AdminPortal from './pages/AdminPortal';
import './styles/index.css';

function AppContent() {
  const { user } = useAuth();
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('hq_dark') === 'true');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toasts, setToasts] = useState([]);

  const toggleDark = () => {
    setDarkMode((d) => {
      const next = !d;
      localStorage.setItem('hq_dark', String(next));
      return next;
    });
  };

  const addToast = useCallback((type, title, message, duration) => {
    setToasts((prev) => [...prev, makeToast(type, title, message, duration)]);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Render portal based on role
  const renderPortal = () => {
    if (!user) return <AuthPage onToast={addToast} />;
    switch (user.role) {
      case 'patient': return <PatientPortal onToast={addToast} />;
      case 'doctor': return <DoctorDashboard onToast={addToast} />;
      case 'admin': return <AdminPortal onToast={addToast} />;
      default: return (
        <div className="empty-state" style={{ marginTop: 80 }}>
          <h3>Unknown role: {user.role}</h3>
          <p>Please contact your administrator.</p>
        </div>
      );
    }
  };

  return (
    <div className={`app-layout ${darkMode ? 'dark' : ''}`}>
      {user && (
        <Navbar
          darkMode={darkMode}
          onToggleDark={toggleDark}
          onOpenSettings={() => setSettingsOpen(true)}
        />
      )}

      {user ? (
        <main className="page-content">{renderPortal()}</main>
      ) : (
        renderPortal()
      )}

      {settingsOpen && (
        <SettingsModal
          darkMode={darkMode}
          onToggleDark={toggleDark}
          onClose={() => setSettingsOpen(false)}
          onToast={addToast}
        />
      )}

      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
