import { useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';

const ICONS = {
  success: <CheckCircle size={18} color="var(--success)" />,
  error: <XCircle size={18} color="var(--danger)" />,
  warning: <AlertTriangle size={18} color="var(--warning)" />,
  info: <Info size={18} color="var(--primary)" />,
};

export function ToastContainer({ toasts, onRemove }) {
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <Toast key={t.id} toast={t} onRemove={onRemove} />
      ))}
    </div>
  );
}

function Toast({ toast, onRemove }) {
  useEffect(() => {
    const timer = setTimeout(() => onRemove(toast.id), toast.duration || 4000);
    return () => clearTimeout(timer);
  }, [toast.id, toast.duration, onRemove]);

  return (
    <div className={`toast ${toast.type}`}>
      <span className="toast-icon">{ICONS[toast.type] || ICONS.info}</span>
      <div className="toast-content">
        {toast.title && <div className="toast-title">{toast.title}</div>}
        {toast.message && <div className="toast-desc">{toast.message}</div>}
      </div>
      <button className="toast-close" onClick={() => onRemove(toast.id)}>
        <X size={14} />
      </button>
    </div>
  );
}

let _toastId = 0;
export function makeToast(type, title, message, duration) {
  return { id: ++_toastId, type, title, message, duration };
}
