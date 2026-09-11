import React, { createContext, useContext, useState, useCallback } from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
  duration: number;
}

interface ToastContextType {
  showToast: (message: string, type?: ToastType, duration?: number) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const showToast = useCallback((message: string, type: ToastType = 'info', duration: number = 3500) => {
    const id = Math.random().toString(36).substring(2, 9);
    const item: ToastItem = { id, message, type, duration };

    setToasts(prev => [...prev.slice(-4), item]); // keep maximum 5 active toasts

    if (duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }
  }, [removeToast]);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="xennex-toast-container" aria-live="polite">
        {toasts.map(toast => {
          const icons = {
            success: <CheckCircle2 size={18} className="toast-icon success" />,
            error: <XCircle size={18} className="toast-icon error" />,
            warning: <AlertTriangle size={18} className="toast-icon warning" />,
            info: <Info size={18} className="toast-icon info" />
          };

          return (
            <div key={toast.id} className={`xennex-toast toast-${toast.type}`}>
              <div className="toast-content">
                {icons[toast.type]}
                <span className="toast-message">{toast.message}</span>
              </div>
              <button
                className="toast-close-btn"
                onClick={() => removeToast(toast.id)}
                title="Fechar notificação"
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export default ToastProvider;
