// Metadatos de presentación para los tipos de eventos detectados en video

import type { EventType } from './types';

export const EVENT_TYPES: EventType[] = ['ruck', 'tackle', 'kick', 'carry'];

export const EVENT_META: Record<EventType, { label: string; plural: string; color: string }> = {
  ruck:   { label: 'Ruck',   plural: 'Rucks',   color: '#f59e0b' },
  tackle: { label: 'Tackle', plural: 'Tackles', color: '#ef4444' },
  kick:   { label: 'Kick',   plural: 'Kicks',   color: '#38bdf8' },
  carry:  { label: 'Carry',  plural: 'Carries', color: '#22c55e' },
};

/** Formatea segundos como m:ss (o h:mm:ss si supera la hora). */
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${m}:${String(sec).padStart(2, '0')}`;
}
