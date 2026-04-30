'use client';

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts';
import type { EloHistoryPoint } from '@/lib/types';

interface Props {
  history: EloHistoryPoint[];
  teamName: string;
}

const RESULT_COLOR = { win: '#4ade80', loss: '#f87171', draw: '#fbbf24' };

export default function EloChart({ history, teamName }: Props) {
  const data = history.map((h, i) => ({
    label: `R${h.round ?? i + 1}`,
    rating: Math.round(h.rating_after),
    change: h.rating_change > 0 ? `+${h.rating_change.toFixed(1)}` : h.rating_change.toFixed(1),
    opponent: h.opponent_name ?? '?',
    result: h.result,
    isHome: h.is_home,
  }));

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 text-xs space-y-1">
        <p className="font-bold">{label}</p>
        <p>vs. <span className="text-white">{d.opponent}</span> {d.isHome ? '(L)' : '(V)'}</p>
        <p>ELO: <span className="text-yellow-400 font-bold">{d.rating}</span></p>
        <p className={d.change.startsWith('+') ? 'text-green-400' : 'text-red-400'}>
          Δ {d.change}
        </p>
        <p className={`font-medium ${RESULT_COLOR[d.result as keyof typeof RESULT_COLOR] ?? 'text-gray-400'}`}>
          {d.result === 'win' ? 'Victoria' : d.result === 'loss' ? 'Derrota' : 'Empate'}
        </p>
      </div>
    );
  };

  return (
    <div>
      <p className="text-sm font-medium mb-3 text-gray-300">{teamName} — Evolución ELO</p>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 12, left: -10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="label"
            tick={{ fill: '#9ca3af', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fill: '#9ca3af', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            domain={['auto', 'auto']}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={1500} stroke="#6b7280" strokeDasharray="4 4" label="" />
          <Line
            type="monotone"
            dataKey="rating"
            stroke="#d4af37"
            strokeWidth={2}
            dot={(props: any) => {
              const { cx, cy, payload } = props;
              const color = RESULT_COLOR[payload.result as keyof typeof RESULT_COLOR] ?? '#9ca3af';
              return <circle key={props.key} cx={cx} cy={cy} r={4} fill={color} stroke="#111827" strokeWidth={1.5} />;
            }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
