import { useEffect } from 'react';
import { MapPinOff, X } from 'lucide-react';
import type { LocationProblem } from '../lib/location';

const COPY: Record<LocationProblem, { title: string; body: string }> = {
  denied: {
    title: 'צריך להפעיל שירותי מיקום',
    body: 'הגישה למיקום חסומה. כדי לסנן לפי המיקום הנוכחי, אפשרו גישה למיקום לאתר בהגדרות הדפדפן (סמל המנעול ליד הכתובת) ונסו שוב.',
  },
  unavailable: {
    title: 'שירותי המיקום כבויים',
    body: 'לא הצלחנו לקבל את המיקום. הפעילו את שירותי המיקום (GPS) בהגדרות המכשיר ונסו שוב.',
  },
  timeout: {
    title: 'איתור המיקום לקח יותר מדי זמן',
    body: 'ודאו ששירותי המיקום מופעלים במכשיר ונסו שוב.',
  },
  unsupported: {
    title: 'המכשיר לא תומך באיתור מיקום',
    body: 'אפשר לבחור עיר ידנית במקום.',
  },
  'no-city': {
    title: 'לא זיהינו את העיר',
    body: 'מצאנו את המיקום אבל לא הצלחנו לזהות באיזו עיר. אפשר לבחור עיר ידנית.',
  },
};

export function LocationPrompt({ problem, onRetry, onClose }: {
  problem: LocationProblem | null;
  onRetry: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!problem) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [problem, onClose]);

  if (!problem) return null;
  const { title, body } = COPY[problem];
  const canRetry = problem !== 'unsupported';

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-card"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="location-prompt-title"
        onClick={e => e.stopPropagation()}
      >
        <button className="modal-close" onClick={onClose} aria-label="סגור">
          <X size={18} strokeWidth={2} />
        </button>
        <div className="modal-icon"><MapPinOff size={26} strokeWidth={1.8} /></div>
        <div id="location-prompt-title" className="modal-title">{title}</div>
        <div className="modal-body">{body}</div>
        <div className="modal-actions">
          {canRetry && (
            <button className="btn btn-primary btn-full" onClick={onRetry}>נסו שוב</button>
          )}
          <button className="btn btn-secondary btn-full" onClick={onClose}>סגור</button>
        </div>
      </div>
    </div>
  );
}
