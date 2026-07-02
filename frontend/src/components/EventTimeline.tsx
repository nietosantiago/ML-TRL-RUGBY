'use client';

import { useRef } from 'react';
import type { MatchEvent, EventType } from '@/lib/types';
import { EVENT_META, EVENT_TYPES, formatClock } from '@/lib/events';

interface Props {
  events: MatchEvent[];
  duration: number;             // segundos totales del video
  currentTime?: number;
  activeTypes: Set<EventType>;
  onSeek?: (t: number) => void;
}

/**
 * Timeline horizontal con una banda por tipo de evento.
 * Los rucks (con t_end) se dibujan como rangos; el resto como marcadores.
 * Click en cualquier punto busca ese instante en el video.
 */
export default function EventTimeline({
  events, duration, currentTime = 0, activeTypes, onSeek,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);

  if (duration <= 0) return null;

  const handleClick = (e: React.MouseEvent) => {
    if (!onSeek || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const frac = (e.clientX - rect.left) / rect.width;
    onSeek(Math.max(0, Math.min(1, frac)) * duration);
  };

  const pct = (t: number) => `${(t / duration) * 100}%`;

  return (
    <div className="space-y-1">
      <div
        ref={ref}
        onClick={handleClick}
        className="relative w-full rounded-lg bg-gray-900 border border-gray-800 cursor-pointer select-none"
      >
        {EVENT_TYPES.map((type) => (
          <div key={type} className="relative h-6 border-b border-gray-800/60 last:border-b-0">
            <span className="absolute left-1 top-0.5 text-[10px] text-gray-500 pointer-events-none z-10">
              {EVENT_META[type].plural}
            </span>
            {activeTypes.has(type) && events
              .filter((ev) => ev.event_type === type)
              .map((ev) => {
                const isRange = ev.t_end != null && ev.t_end - ev.t_start > 1;
                return (
                  <div
                    key={ev.id}
                    title={`${EVENT_META[type].label} · ${formatClock(ev.t_start)}`}
                    onClick={(e) => { e.stopPropagation(); onSeek?.(ev.t_start); }}
                    className="absolute top-1 h-4 rounded-sm hover:opacity-100 opacity-80 transition-opacity"
                    style={{
                      left: pct(ev.t_start),
                      width: isRange
                        ? `max(${((ev.t_end! - ev.t_start) / duration) * 100}%, 3px)`
                        : '3px',
                      backgroundColor: EVENT_META[type].color,
                    }}
                  />
                );
              })}
          </div>
        ))}

        {/* Playhead */}
        {currentTime > 0 && (
          <div
            className="absolute top-0 bottom-0 w-px bg-white/80 pointer-events-none"
            style={{ left: pct(Math.min(currentTime, duration)) }}
          />
        )}
      </div>

      <div className="flex justify-between text-[10px] text-gray-500">
        <span>0:00</span>
        <span>{formatClock(duration / 2)}</span>
        <span>{formatClock(duration)}</span>
      </div>
    </div>
  );
}
