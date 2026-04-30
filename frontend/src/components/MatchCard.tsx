'use client';

import { clsx } from 'clsx';
import type { Match } from '@/lib/types';

interface Props {
  match: Match;
  prediction?: { home_win_prob: number; draw_prob: number; away_win_prob: number } | null;
  onSelect?: (match: Match) => void;
  selected?: boolean;
}

export default function MatchCard({ match, prediction, onSelect, selected }: Props) {
  const isPlayed = match.is_played;
  const homeWon  = isPlayed && match.home_score! > match.away_score!;
  const awayWon  = isPlayed && match.away_score! > match.home_score!;

  return (
    <div
      onClick={() => onSelect?.(match)}
      className={clsx(
        'card transition-all',
        onSelect && 'cursor-pointer hover:border-gray-700',
        selected && 'border-rugby-green ring-1 ring-rugby-green',
      )}
    >
      <div className="text-xs text-gray-500 mb-2 flex justify-between">
        <span>Fecha {match.round}</span>
        {match.match_date && (
          <span>{new Date(match.match_date + 'T12:00:00').toLocaleDateString('es-AR', {
            day: '2-digit', month: 'short',
          })}</span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {/* Local */}
        <div className={clsx('flex-1 text-right', homeWon && 'text-green-400 font-bold')}>
          <span className="text-sm">{match.home_team_name}</span>
        </div>

        {/* Resultado / VS */}
        <div className="flex items-center gap-1 text-center min-w-[80px]">
          {isPlayed ? (
            <>
              <span className={clsx(
                'text-xl font-bold tabular-nums',
                homeWon ? 'text-green-400' : 'text-gray-400',
              )}>{match.home_score}</span>
              <span className="text-gray-600">—</span>
              <span className={clsx(
                'text-xl font-bold tabular-nums',
                awayWon ? 'text-green-400' : 'text-gray-400',
              )}>{match.away_score}</span>
            </>
          ) : (
            <span className="text-gray-600 font-medium text-sm">vs</span>
          )}
        </div>

        {/* Visitante */}
        <div className={clsx('flex-1 text-left', awayWon && 'text-green-400 font-bold')}>
          <span className="text-sm">{match.away_team_name}</span>
        </div>
      </div>

      {/* Tries */}
      {isPlayed && (match.home_tries != null || match.away_tries != null) && (
        <div className="mt-1 text-center text-xs text-gray-500">
          Tries: {match.home_tries ?? 0} — {match.away_tries ?? 0}
          {match.home_bonus_try && <span className="ml-1 text-yellow-500">★</span>}
          {match.away_bonus_try && <span className="ml-1 text-yellow-500">★</span>}
        </div>
      )}

      {/* Predicción */}
      {!isPlayed && prediction && (
        <div className="mt-2 flex h-2 rounded-full overflow-hidden">
          <div
            className="bg-green-600"
            style={{ width: `${prediction.home_win_prob * 100}%` }}
          />
          <div
            className="bg-gray-500"
            style={{ width: `${prediction.draw_prob * 100}%` }}
          />
          <div
            className="bg-blue-600"
            style={{ width: `${prediction.away_win_prob * 100}%` }}
          />
        </div>
      )}
    </div>
  );
}
