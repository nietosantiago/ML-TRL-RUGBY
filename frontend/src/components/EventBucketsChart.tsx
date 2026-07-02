'use client';

import {
  Bar, BarChart, CartesianGrid, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { TimelineBucket } from '@/lib/types';
import { EVENT_META, EVENT_TYPES } from '@/lib/events';

interface Props {
  timeline: TimelineBucket[];
  bucketSeconds: number;
}

/** Barras apiladas de eventos por bloque de tiempo (intensidad del partido). */
export default function EventBucketsChart({ timeline, bucketSeconds }: Props) {
  if (timeline.length === 0) return null;

  const data = timeline.map((b) => ({
    label: `${Math.round(b.t_start / 60)}'`,
    ...Object.fromEntries(EVENT_TYPES.map((t) => [t, b.counts[t] ?? 0])),
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -24 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
        <XAxis dataKey="label" tick={{ fill: '#9ca3af', fontSize: 11 }} />
        <YAxis allowDecimals={false} tick={{ fill: '#9ca3af', fontSize: 11 }} />
        <Tooltip
          contentStyle={{
            backgroundColor: '#111827',
            border: '1px solid #374151',
            borderRadius: 8,
            fontSize: 12,
          }}
          labelFormatter={(label) => `Minuto ${label} (+${Math.round(bucketSeconds / 60)}')`}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {EVENT_TYPES.map((t) => (
          <Bar
            key={t}
            dataKey={t}
            stackId="events"
            name={EVENT_META[t].plural}
            fill={EVENT_META[t].color}
            radius={t === 'carry' ? [3, 3, 0, 0] : undefined}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
