'use client';

import { clsx } from 'clsx';
import type { Standing } from '@/lib/types';

interface Props {
  standings: Standing[];
  semifinalSpots?: number;
  showElo?: boolean;
}

export default function StandingsTable({
  standings,
  semifinalSpots = 4,
  showElo = true,
}: Props) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-900 text-gray-400 text-xs uppercase tracking-wide">
            <th className="px-3 py-2.5 text-center w-8">#</th>
            <th className="px-3 py-2.5 text-left">Equipo</th>
            <th className="px-3 py-2.5 text-center">J</th>
            <th className="px-3 py-2.5 text-center">G</th>
            <th className="px-3 py-2.5 text-center">E</th>
            <th className="px-3 py-2.5 text-center">P</th>
            <th className="px-3 py-2.5 text-center">PF</th>
            <th className="px-3 py-2.5 text-center">PC</th>
            <th className="px-3 py-2.5 text-center">DP</th>
            <th className="px-3 py-2.5 text-center">B+</th>
            <th className="px-3 py-2.5 text-center font-bold text-white">Pts</th>
            {showElo && (
              <th className="px-3 py-2.5 text-center text-yellow-500">ELO</th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {standings.map((row, idx) => {
            const pos = row.position ?? idx + 1;
            const inSemis = pos <= semifinalSpots;
            return (
              <tr
                key={row.team_id}
                className={clsx(
                  'transition-colors hover:bg-gray-800/50',
                  inSemis && 'bg-green-950/20',
                )}
              >
                <td className="px-3 py-2.5 text-center">
                  <span
                    className={clsx(
                      'inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold',
                      pos === 1
                        ? 'bg-yellow-500 text-black'
                        : inSemis
                        ? 'bg-green-900 text-green-300'
                        : 'text-gray-500',
                    )}
                  >
                    {pos}
                  </span>
                </td>
                <td className="px-3 py-2.5 font-medium">
                  {row.team_short_name
                    ? <span title={row.team_name}>{row.team_short_name}</span>
                    : row.team_name}
                </td>
                <td className="px-3 py-2.5 text-center text-gray-400">{row.played}</td>
                <td className="px-3 py-2.5 text-center text-green-400 font-medium">{row.won}</td>
                <td className="px-3 py-2.5 text-center text-gray-400">{row.drawn}</td>
                <td className="px-3 py-2.5 text-center text-red-400">{row.lost}</td>
                <td className="px-3 py-2.5 text-center">{row.points_for}</td>
                <td className="px-3 py-2.5 text-center">{row.points_against}</td>
                <td className={clsx(
                  'px-3 py-2.5 text-center font-medium',
                  row.point_diff > 0 ? 'text-green-400' : row.point_diff < 0 ? 'text-red-400' : 'text-gray-400',
                )}>
                  {row.point_diff > 0 ? `+${row.point_diff}` : row.point_diff}
                </td>
                <td className="px-3 py-2.5 text-center text-gray-400">
                  {row.bonus_try_points + row.bonus_losing_points}
                </td>
                <td className="px-3 py-2.5 text-center">
                  <span className="font-bold text-white bg-rugby-green px-2 py-0.5 rounded">
                    {row.total_points}
                  </span>
                </td>
                {showElo && (
                  <td className="px-3 py-2.5 text-center text-yellow-400 text-xs font-mono">
                    {row.elo_rating ? Math.round(row.elo_rating) : '—'}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="flex items-center gap-4 px-3 py-2 border-t border-gray-800 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-green-900 inline-block" />
          Clasifican a semifinales (top {semifinalSpots})
        </span>
        <span>J=Jugados G=Ganados E=Empates P=Perdidos PF=PuntosFavor PC=PuntosContra DP=Diferencia B+=Bonus</span>
      </div>
    </div>
  );
}
