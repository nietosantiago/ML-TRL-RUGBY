'use client';

import { useQuery } from '@tanstack/react-query';
import { fetchStandings, fetchMatches, simulateSeason } from '@/lib/api';
import StandingsTable from '@/components/StandingsTable';
import MatchCard from '@/components/MatchCard';
import ProbabilityBar from '@/components/ProbabilityBar';
import { TrendingUp, Target, Calendar, Activity } from 'lucide-react';

export default function Dashboard() {
  const { data: standings = [], isLoading: loadingStandings } = useQuery({
    queryKey: ['standings'],
    queryFn: () => fetchStandings(),
  });

  const { data: recentMatches = [] } = useQuery({
    queryKey: ['matches', 'recent'],
    queryFn: () => fetchMatches({ played: true }),
    select: (data) => data.slice(-6).reverse(),
  });

  const { data: upcomingMatches = [] } = useQuery({
    queryKey: ['matches', 'upcoming'],
    queryFn: () => fetchMatches({ played: false }),
    select: (data) => data.slice(0, 5),
  });

  const { data: simulation, isLoading: loadingSim } = useQuery({
    queryKey: ['simulation', 'quick'],
    queryFn: () => simulateSeason({ n_iterations: 5_000, model: 'elo' }),
    staleTime: 5 * 60 * 1000,
  });

  const leader = standings[0];
  const topSimTeams = simulation?.teams.slice(0, 4) ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Torneo Regional del Litoral</h1>
        <p className="text-gray-400 text-sm mt-0.5">
          Análisis en tiempo real · Predicciones basadas en ELO + ML
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          icon={<TrendingUp size={18} className="text-green-400" />}
          label="Líder actual"
          value={leader?.team_short_name ?? leader?.team_name ?? '—'}
          sub={`${leader?.total_points ?? 0} pts`}
          loading={loadingStandings}
        />
        <StatCard
          icon={<Activity size={18} className="text-yellow-400" />}
          label="ELO líder"
          value={leader?.elo_rating ? Math.round(leader.elo_rating).toString() : '—'}
          sub="rating actual"
          loading={loadingStandings}
        />
        <StatCard
          icon={<Calendar size={18} className="text-blue-400" />}
          label="Próximos"
          value={upcomingMatches.length.toString()}
          sub="partidos pendientes"
        />
        <StatCard
          icon={<Target size={18} className="text-purple-400" />}
          label="Simulaciones"
          value="10.000"
          sub="iteraciones Monte Carlo"
        />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Tabla de posiciones */}
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <TrendingUp size={18} className="text-rugby-gold" />
            Tabla de posiciones
          </h2>
          {loadingStandings ? (
            <div className="card animate-pulse h-48" />
          ) : (
            <StandingsTable standings={standings} showElo />
          )}
        </div>

        {/* Probabilidades de clasificación */}
        <div className="space-y-3">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Target size={18} className="text-rugby-gold" />
            P(Campeón) — Monte Carlo
          </h2>
          {loadingSim ? (
            <div className="card animate-pulse h-48" />
          ) : (
            <div className="card space-y-3">
              {topSimTeams.map((t) => (
                <div key={t.team_id}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-300">{t.team_name}</span>
                    <div className="flex gap-3 text-xs">
                      <span className="text-yellow-400 font-bold">
                        {(t.champion_prob * 100).toFixed(1)}%
                      </span>
                      <span className="text-green-400">
                        {(t.semifinal_prob * 100).toFixed(0)}% semis
                      </span>
                    </div>
                  </div>
                  <div className="h-1.5 rounded-full bg-gray-800">
                    <div
                      className="h-1.5 rounded-full bg-yellow-500 transition-all"
                      style={{ width: `${t.champion_prob * 100}%` }}
                    />
                  </div>
                </div>
              ))}
              <p className="text-xs text-gray-500 text-right mt-2">
                {simulation?.n_iterations.toLocaleString()} iteraciones · modelo {simulation?.model_used}
              </p>
            </div>
          )}

          {/* Próximos partidos */}
          <h2 className="text-lg font-semibold mt-4 flex items-center gap-2">
            <Calendar size={18} className="text-rugby-gold" />
            Próximos partidos
          </h2>
          <div className="space-y-2">
            {upcomingMatches.slice(0, 4).map((m) => (
              <MatchCard key={m.id} match={m} />
            ))}
          </div>
        </div>
      </div>

      {/* Últimos resultados */}
      <div>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Activity size={18} className="text-rugby-gold" />
          Últimos resultados
        </h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {recentMatches.map((m) => (
            <MatchCard key={m.id} match={m} />
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon, label, value, sub, loading,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  loading?: boolean;
}) {
  return (
    <div className={`card flex gap-3 items-start ${loading ? 'animate-pulse' : ''}`}>
      <div className="mt-0.5">{icon}</div>
      <div>
        <p className="text-xs text-gray-500">{label}</p>
        <p className="text-xl font-bold text-white">{value}</p>
        <p className="text-xs text-gray-400">{sub}</p>
      </div>
    </div>
  );
}
