'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';
import { fetchStandings, fetchStandingsEvolution, fetchTeamEloHistory } from '@/lib/api';
import StandingsTable from '@/components/StandingsTable';
import EloChart from '@/components/EloChart';
import { TrendingUp, Activity } from 'lucide-react';

const TEAM_COLORS = [
  '#d4af37', '#4ade80', '#60a5fa', '#f472b6',
  '#a78bfa', '#fb923c', '#34d399', '#f87171',
  '#fbbf24', '#22d3ee',
];

export default function StandingsPage() {
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null);

  const { data: standings = [], isLoading } = useQuery({
    queryKey: ['standings'],
    queryFn: () => fetchStandings(),
  });

  const { data: evolution } = useQuery({
    queryKey: ['standings-evolution'],
    queryFn: () => fetchStandingsEvolution(),
  });

  const { data: eloHistory } = useQuery({
    queryKey: ['elo-history', selectedTeamId],
    queryFn: () => fetchTeamEloHistory(selectedTeamId!),
    enabled: selectedTeamId != null,
  });

  // Construir datos para gráfico de evolución de posiciones
  const evolutionData = evolution
    ? Object.entries(evolution.rounds).map(([round, teams]) => {
        const entry: Record<string, number | string> = { round: `R${round}` };
        teams.forEach((t) => {
          entry[t.team_name] = t.position;
        });
        return entry;
      })
    : [];

  const teamNames = standings.map((s) => s.team_name);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Posiciones</h1>

      {/* Tabla principal */}
      {isLoading ? (
        <div className="card animate-pulse h-64" />
      ) : (
        <StandingsTable
          standings={standings}
          semifinalSpots={4}
          showElo
        />
      )}

      {/* Evolución de posiciones */}
      {evolutionData.length > 1 && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <TrendingUp size={18} className="text-rugby-gold" />
            Evolución de posiciones
          </h2>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={evolutionData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="round" tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <YAxis
                reversed
                tick={{ fill: '#9ca3af', fontSize: 11 }}
                domain={[1, standings.length]}
                tickCount={standings.length}
              />
              <Tooltip
                contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                labelStyle={{ color: '#fff' }}
                formatter={(v: any) => [`Pos. ${v}`, '']}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {teamNames.map((name, i) => (
                <Line
                  key={name}
                  type="monotone"
                  dataKey={name}
                  stroke={TEAM_COLORS[i % TEAM_COLORS.length]}
                  strokeWidth={selectedTeamId === standings[i]?.team_id ? 3 : 1.5}
                  dot={false}
                  opacity={selectedTeamId == null || selectedTeamId === standings[i]?.team_id ? 1 : 0.2}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Histórico ELO por equipo */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Activity size={18} className="text-rugby-gold" />
          Evolución ELO por equipo
        </h2>
        <div className="flex flex-wrap gap-2 mb-4">
          {standings.map((s) => (
            <button
              key={s.team_id}
              onClick={() =>
                setSelectedTeamId(s.team_id === selectedTeamId ? null : s.team_id)
              }
              className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                selectedTeamId === s.team_id
                  ? 'bg-rugby-green border-rugby-green text-white'
                  : 'border-gray-700 text-gray-400 hover:border-gray-500'
              }`}
            >
              {s.team_short_name ?? s.team_name}
            </button>
          ))}
        </div>

        {selectedTeamId && eloHistory ? (
          <EloChart
            history={eloHistory.history}
            teamName={eloHistory.team_name}
          />
        ) : (
          <p className="text-gray-500 text-sm text-center py-8">
            Seleccioná un equipo para ver su evolución ELO
          </p>
        )}
      </div>
    </div>
  );
}
