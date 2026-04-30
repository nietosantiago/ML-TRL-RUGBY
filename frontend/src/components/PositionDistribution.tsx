'use client';

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import type { TeamSimResult } from '@/lib/types';

const POSITION_COLORS = [
  '#d4af37', '#aaaaaa', '#c87532', '#4ade80',
  '#60a5fa', '#f472b6', '#a78bfa', '#fb923c',
  '#34d399', '#f87171',
];

interface Props {
  team: TeamSimResult;
  nTeams: number;
}

export default function PositionDistribution({ team, nTeams }: Props) {
  const data = Array.from({ length: nTeams }, (_, i) => ({
    position: i + 1,
    probability: (team.position_probs[`pos_${i + 1}`] ?? 0) * 100,
  }));

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    return (
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-2 text-xs">
        <p className="font-bold">Posición {label}</p>
        <p className="text-yellow-400">{payload[0].value.toFixed(1)}%</p>
      </div>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium">{team.team_name}</span>
        <div className="flex gap-3 text-xs text-gray-400">
          <span>
            Campeón:{' '}
            <span className="text-yellow-400 font-bold">
              {(team.champion_prob * 100).toFixed(1)}%
            </span>
          </span>
          <span>
            Semis:{' '}
            <span className="text-green-400 font-bold">
              {(team.semifinal_prob * 100).toFixed(1)}%
            </span>
          </span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
          <XAxis
            dataKey="position"
            tick={{ fill: '#9ca3af', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fill: '#9ca3af', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `${v.toFixed(0)}%`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="probability" radius={[2, 2, 0, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={index}
                fill={POSITION_COLORS[index % POSITION_COLORS.length]}
                opacity={entry.probability > 0 ? 1 : 0.2}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Intervalos de confianza de puntos */}
      <div className="mt-2 flex items-center gap-2 text-xs text-gray-400">
        <span>Puntos finales:</span>
        <span className="text-gray-500">p5={team.points_p5.toFixed(0)}</span>
        <span className="text-white font-medium">
          p50={team.points_p50.toFixed(0)}
          <span className="text-gray-400"> (media={team.points_mean.toFixed(1)})</span>
        </span>
        <span className="text-gray-500">p95={team.points_p95.toFixed(0)}</span>
      </div>
    </div>
  );
}
