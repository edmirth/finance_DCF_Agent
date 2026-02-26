import { useEffect, useState } from 'react';
import { CheckCircle } from 'lucide-react';

interface ToastNotificationProps {
  message: string;
  visible: boolean;
  onDismiss: () => void;
  duration?: number; // ms, default 3000
}

export default function ToastNotification({
  message,
  visible,
  onDismiss,
  duration = 3000,
}: ToastNotificationProps) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (visible) {
      setShow(true);
      const timer = setTimeout(() => {
        setShow(false);
        // Give fade-out animation time to finish before calling onDismiss
        setTimeout(onDismiss, 300);
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [visible, duration, onDismiss]);

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-3 rounded-xl shadow-lg border border-emerald-200 bg-white transition-all duration-300 ${
        show ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none'
      }`}
      style={{ minWidth: '220px' }}
    >
      <CheckCircle className="w-4 h-4 text-emerald-500 flex-shrink-0" />
      <span
        style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: '0.875rem',
          color: '#1A1A1A',
          fontWeight: 500,
        }}
      >
        {message}
      </span>
    </div>
  );
}
