'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchMatches, predictMatch } from '@/lib/api';
import MatchCard from '@/components/MatchCard';
import ProbabilityBar from '@/components/ProbabilityBar';
import type { Match, MatchPrediction } from '@/lib/types';

export default function MatchesPage() {
  const [activeRound, setActiveRound] = useState<number | null>(null);
  const [selectedMatch, setSelectedMatch] = useState<Match | null>(null);

  const { data: allMatches = [], isLoading } = useQuery({
    queryKey: ['matches', 'all'],
    queryFn: () => fetchMatches(),
  });

  const rounds = [...new Set(allMatches.map((m) => m.round))].sort((a, b) => a - b);
  const filtered = activeRound
    ? allMatches.filter((m) => m.round === activeRound)
    : allMatches;

  const played   = filtered.filter((m) => m.is_played);
  const upcoming = filtered.filter((m) => !m.is_played);

  const { data: prediction } = useQuery<MatchPrediction>({
    queryKey: ['prediction', selectedMatch?.id],
    queryFn: () =>
      predictMatch(selectedMatch!.home_team_id, selectedMatch!.away_team_id, 'elo'),
    enabled: selectedMatch != null && !selectedMatch.is_played,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Partidos</h1>

      {/* Filtro por fecha */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setActiveRound(null)}
          className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
            activeRound == null
              ? 'bg-rugby-green border-rugby-green text-white'
              : 'border-gray-700 text-gray-400 hover:border-gray-500'
          }`}
        >
          Todas
        </button>
        {rounds.map((r) => (
          <button
            key={r}
            onClick={() => setActiveRound(r === activeRound ? null : r)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              activeRound === r
                ? 'bg-rugby-green border-rugby-green text-white'
                : 'border-gray-700 text-gray-400 hover:border-gray-500'
            }`}
          >
            Fecha {r}
          </button>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Lista de partidos */}
        <div className="lg:col-span-2 space-y-6">
          {upcoming.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
                Próximos partidos
              </h2>
              <div className="grid sm:grid-cols-2 gap-3">
                {upcoming.map((m) => (
                  <MatchCard
                    key={m.id}
                    match={m}
                    onSelect={setSelectedMatch}
                    selected={selectedMatch?.id === m.id}
                  />
                ))}
              </div>
            </div>
          )}

          {played.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
                Resultados
              </h2>
              <div className="grid sm:grid-cols-2 gap-3">
                {played.map((m) => (
                  <MatchCard key={m.id} match={m} />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Panel de predicción */}
        <div className="space-y-3">
          {selectedMatch && !selectedMatch.is_played ? (
            <div className="card space-y-4">
              <h2 className="font-semibold text-white">Predicción</h2>
              <div className="text-center text-sm">
                <p className="text-green-400 font-medium">{selectedMatch.home_team_name}</p>
                <p className="text-gray-500 text-xs my-1">vs</p>
                <p className="text-blue-400 font-medium">{selectedMatch.away_team_name}</p>
              </div>
              {prediction ? (
                <ProbabilityBar
                  homeProb={prediction.home_win_prob}
                  drawProb={prediction.draw_prob}
                  awayProb={prediction.away_win_prob}
                  homeLabel={selectedMatch.home_team_name ?? 'Local'}
                  awayLabel={selectedMatch.away_team_name ?? 'Visitante'}
                />
              ) : (
                <div className="h-8 animate-pulse bg-gray-800 rounded" />
              )}
              {prediction && (
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-gray-800 rounded p-2">
                    <p className="text-gray-400">ELO Local</p>
                    <p className="text-white font-bold">{Math.round(prediction.home_elo)}</p>
                  </div>
                  <div className="bg-gray-800 rounded p-2">
                    <p className="text-gray-400">ELO Visitante</p>
                    <p className="text-white font-bold">{Math.round(prediction.away_elo)}</p>
                  </div>
                  <div className="col-span-2 bg-gray-800 rounded p-2">
                    <p className="text-gray-400">Diferencia ELO</p>
                    <p className={`font-bold ${prediction.elo_diff > 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {prediction.elo_diff > 0 ? '+' : ''}{Math.round(prediction.elo_diff)} (local)
                    </p>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="card text-center text-gray-500 text-sm py-8">
              Hacé click en un partido pendiente para ver la predicción
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
