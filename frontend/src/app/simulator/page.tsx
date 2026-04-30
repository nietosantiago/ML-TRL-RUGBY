'use client';

import { useState, useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { fetchMatches, fetchStandings, customSimulation } from '@/lib/api';
import StandingsTable from '@/components/StandingsTable';
import PositionDistribution from '@/components/PositionDistribution';
import type { Match, SimulationResult, MatchResult, ModelType } from '@/lib/types';
import { Play, RotateCcw, Target } from 'lucide-react';

type FixedResults = Record<number, MatchResult>;

export default function SimulatorPage() {
  const [fixedResults, setFixedResults] = useState<FixedResults>({});
  const [model, setModel] = useState<ModelType>('elo');
  const [nIter, setNIter] = useState(10_000);

  const { data: standings = [] } = useQuery({
    queryKey: ['standings'],
    queryFn: () => fetchStandings(),
  });

  const { data: pendingMatches = [] } = useQuery({
    queryKey: ['matches', 'pending'],
    queryFn: () => fetchMatches({ played: false }),
  });

  const simulation = useMutation({
    mutationFn: (params: {
      fixed_results: Array<{ match_id: number; result: MatchResult }>;
      model: ModelType;
      n_iterations: number;
    }) => customSimulation(params),
  });

  const handleFixResult = useCallback(
    (matchId: number, result: MatchResult | null) => {
      setFixedResults((prev) => {
        const next = { ...prev };
        if (result == null) delete next[matchId];
        else next[matchId] = result;
        return next;
      });
    },
    []
  );

  const handleRun = () => {
    simulation.mutate({
      fixed_results: Object.entries(fixedResults).map(([id, result]) => ({
        match_id: Number(id),
        result,
      })),
      model,
      n_iterations: nIter,
    });
  };

  const nFixed = Object.keys(fixedResults).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Target size={24} className="text-rugby-gold" />
          Simulador de Temporada
        </h1>
        <p className="text-gray-400 text-sm mt-1">
          Fijá resultados de partidos pendientes y corré {nIter.toLocaleString()} simulaciones
          para ver cómo impactan en las probabilidades de clasificación.
        </p>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Configuración */}
        <div className="space-y-4">
          <div className="card space-y-4">
            <h2 className="font-semibold">Configuración</h2>

            <div>
              <label className="text-xs text-gray-400 block mb-1">Modelo predictivo</label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value as ModelType)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
              >
                <option value="elo">ELO (recomendado)</option>
                <option value="logistic">Regresión Logística</option>
                <option value="xgboost">XGBoost</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">
                Iteraciones: {nIter.toLocaleString()}
              </label>
              <input
                type="range"
                min={1000}
                max={50000}
                step={1000}
                value={nIter}
                onChange={(e) => setNIter(Number(e.target.value))}
                className="w-full accent-rugby-green"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-0.5">
                <span>1k (rápido)</span>
                <span>50k (preciso)</span>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={handleRun}
                disabled={simulation.isPending}
                className="flex-1 flex items-center justify-center gap-2 bg-rugby-green hover:bg-rugby-green-light disabled:opacity-50 text-white rounded-lg py-2 text-sm font-medium transition-colors"
              >
                <Play size={15} />
                {simulation.isPending ? 'Simulando...' : 'Simular'}
              </button>
              <button
                onClick={() => setFixedResults({})}
                className="p-2 border border-gray-700 rounded-lg hover:border-gray-500 transition-colors"
                title="Limpiar resultados fijados"
              >
                <RotateCcw size={15} className="text-gray-400" />
              </button>
            </div>

            {nFixed > 0 && (
              <p className="text-xs text-green-400">
                {nFixed} resultado{nFixed > 1 ? 's' : ''} fijado{nFixed > 1 ? 's' : ''}
              </p>
            )}
          </div>

          {/* Partidos pendientes con selector de resultado */}
          <div className="card space-y-3">
            <h2 className="font-semibold text-sm">Fijar resultados</h2>
            <p className="text-xs text-gray-500">
              Dejá en blanco para que el modelo calcule la probabilidad.
            </p>
            <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
              {pendingMatches.map((m) => (
                <MatchResultSelector
                  key={m.id}
                  match={m}
                  value={fixedResults[m.id] ?? null}
                  onChange={(v) => handleFixResult(m.id, v)}
                />
              ))}
              {pendingMatches.length === 0 && (
                <p className="text-xs text-gray-500 text-center py-4">
                  No hay partidos pendientes
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Resultados de simulación */}
        <div className="lg:col-span-2 space-y-4">
          {simulation.data ? (
            <>
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">
                  Resultados — {simulation.data.n_iterations.toLocaleString()} iteraciones
                </h2>
                <span className="text-xs text-gray-500">
                  modelo: {simulation.data.model_used}
                  {simulation.data.fixed_results_applied
                    ? ` · ${simulation.data.fixed_results_applied} fijados`
                    : ''}
                </span>
              </div>

              {/* Tabla de probabilidades */}
              <div className="card">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-gray-400 border-b border-gray-800">
                      <th className="pb-2 text-left">Equipo</th>
                      <th className="pb-2 text-center">Campeón</th>
                      <th className="pb-2 text-center">Semis</th>
                      <th className="pb-2 text-center">Pts media</th>
                      <th className="pb-2 text-center w-32">IC 90%</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {simulation.data.teams.map((t) => (
                      <tr key={t.team_id} className="hover:bg-gray-800/50">
                        <td className="py-2 font-medium text-sm">{t.team_name}</td>
                        <td className="py-2 text-center">
                          <span className={`font-bold text-sm ${
                            t.champion_prob > 0.3
                              ? 'text-yellow-400'
                              : t.champion_prob > 0.1
                              ? 'text-yellow-600'
                              : 'text-gray-500'
                          }`}>
                            {(t.champion_prob * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="py-2 text-center">
                          <span className={`text-sm ${
                            t.semifinal_prob > 0.5 ? 'text-green-400' : 'text-gray-400'
                          }`}>
                            {(t.semifinal_prob * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="py-2 text-center text-gray-300 text-sm">
                          {t.points_mean.toFixed(1)}
                        </td>
                        <td className="py-2 text-center text-xs text-gray-500">
                          [{t.points_p5.toFixed(0)} – {t.points_p95.toFixed(0)}]
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Distribución de posiciones */}
              <div className="card space-y-6">
                <h3 className="font-semibold text-sm">Distribución de posiciones finales</h3>
                {simulation.data.teams.map((t) => (
                  <PositionDistribution
                    key={t.team_id}
                    team={t}
                    nTeams={simulation.data!.teams.length}
                  />
                ))}
              </div>
            </>
          ) : (
            <div className="card flex flex-col items-center justify-center py-16 text-gray-500 space-y-3">
              <Target size={48} className="opacity-30" />
              <p>Configurá la simulación y hacé click en "Simular"</p>
              <p className="text-xs">
                La primera ejecución puede tardar ~10 segundos (10.000 iteraciones)
              </p>
            </div>
          )}

          {simulation.isError && (
            <div className="card border-red-900 text-red-400 text-sm">
              Error al ejecutar la simulación. Verificá que el backend esté corriendo.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MatchResultSelector({
  match,
  value,
  onChange,
}: {
  match: Match;
  value: MatchResult | null;
  onChange: (v: MatchResult | null) => void;
}) {
  const opts: Array<{ label: string; value: MatchResult; color: string }> = [
    { label: 'L', value: 'home', color: 'text-green-400 border-green-700' },
    { label: 'E', value: 'draw', color: 'text-gray-300 border-gray-600' },
    { label: 'V', value: 'away', color: 'text-blue-400 border-blue-700' },
  ];

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 min-w-0">
        <p className="text-xs text-gray-300 truncate">
          <span className="text-green-400">{match.home_team_name}</span>
          {' vs '}
          <span className="text-blue-400">{match.away_team_name}</span>
        </p>
        <p className="text-xs text-gray-600">Fecha {match.round}</p>
      </div>
      <div className="flex gap-1 shrink-0">
        {opts.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onChange(value === opt.value ? null : opt.value)}
            className={`w-7 h-7 text-xs border rounded font-bold transition-colors ${
              value === opt.value
                ? `bg-gray-700 ${opt.color}`
                : 'border-gray-800 text-gray-600 hover:border-gray-600'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
