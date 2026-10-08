import { useEffect, useState } from 'react';
import { MapPin, MapPinOff, X } from 'lucide-react';
import { fetchCities } from '../api/client';
import { CityPicker } from './CityPicker';
import type { LocationProblem } from '../lib/location';

const COPY: Record<LocationProblem, { title: string; body: string }> = {
  ask: {
    title: 'למצוא סופרים לידך?',
    body: 'נשתמש במיקום שלך רק כדי לסנן סניפים ולהראות מרחק. אחרי הלחיצה המכשיר ישאל אם לאשר.',
  },
  denied: {
    title: 'צריך להפעיל שירותי מיקום',
    body: 'הגישה למיקום חסומה במכשיר. אפשר לבחור עיר ידנית, או לאשר מיקום ולנסות שוב.',
  },
  unavailable: {
    title: 'שירותי המיקום כבויים',
    body: 'לא הצלחנו לקבל את המיקום. אפשר לבחור עיר ידנית או לנסות שוב.',
  },
  timeout: {
    title: 'איתור המיקום לקח יותר מדי זמן',
    body: 'אפשר לבחור עיר ידנית או לנסות שוב.',
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

export function LocationPrompt({ problem, onRetry, onConfirm, onPickCity, suggestedCity, onClose }: {
  problem: LocationProblem | null;
  onRetry: () => void;
  onConfirm: () => void;
  onPickCity: (city: string) => void;
  suggestedCity?: string;
  onClose: () => void;
}) {
  const [cities, setCities] = useState<string[]>([]);
  useEffect(() => {
    if (problem && cities.length === 0) fetchCities().then(setCities).catch(() => {});
  }, [problem, cities.length]);

  useEffect(() => {
    if (!problem) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [problem, onClose]);

  if (!problem) return null;
  const { title, body } = COPY[problem];
  const isAsk = problem === 'ask';
  const suggestion = suggestedCity && cities.includes(suggestedCity) ? suggestedCity : '';

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
        <div className="modal-icon">
          {isAsk ? <MapPin size={26} strokeWidth={1.8} /> : <MapPinOff size={26} strokeWidth={1.8} />}
        </div>
        <div id="location-prompt-title" className="modal-title">{title}</div>
        <div className="modal-body">{body}</div>
        <div className="modal-fields">
        {!isAsk && suggestion && (
          <button className="btn btn-secondary btn-full" onClick={() => onPickCity(suggestion)}>
            להשתמש ב{suggestion}?
          </button>
        )}
        <CityPicker value="" cities={cities} onChange={onPickCity} placeholder="בחרו עיר ידנית..." />
        </div>
        <div className="modal-actions">
          {isAsk ? (
            <button className="btn btn-primary btn-full" onClick={onConfirm}>אפשר מיקום</button>
          ) : problem !== 'unsupported' && (
            <button className="btn btn-primary btn-full" onClick={onRetry}>נסו שוב</button>
          )}
          <button className="btn btn-secondary btn-full" onClick={onClose}>{isAsk ? 'לא עכשיו' : 'סגור'}</button>
        </div>
      </div>
    </div>
  );
}
