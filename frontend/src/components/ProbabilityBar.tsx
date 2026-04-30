'use client';

interface Props {
  homeProb:    number;
  drawProb:    number;
  awayProb:    number;
  homeLabel?:  string;
  awayLabel?:  string;
  showLabels?: boolean;
}

export default function ProbabilityBar({
  homeProb,
  drawProb,
  awayProb,
  homeLabel = 'Local',
  awayLabel = 'Visitante',
  showLabels = true,
}: Props) {
  const hp = (homeProb * 100).toFixed(0);
  const dp = (drawProb * 100).toFixed(0);
  const ap = (awayProb * 100).toFixed(0);

  return (
    <div className="space-y-1">
      {showLabels && (
        <div className="flex justify-between text-xs text-gray-400">
          <span className="font-medium text-green-400">{homeLabel}</span>
          <span className="text-gray-500">Empate</span>
          <span className="font-medium text-blue-400">{awayLabel}</span>
        </div>
      )}
      <div className="flex h-6 rounded-lg overflow-hidden text-xs font-bold">
        <div
          className="flex items-center justify-center bg-green-700 transition-all"
          style={{ width: `${hp}%` }}
        >
          {Number(hp) > 10 && <span>{hp}%</span>}
        </div>
        <div
          className="flex items-center justify-center bg-gray-600 transition-all"
          style={{ width: `${dp}%` }}
        >
          {Number(dp) > 8 && <span>{dp}%</span>}
        </div>
        <div
          className="flex items-center justify-center bg-blue-700 transition-all"
          style={{ width: `${ap}%` }}
        >
          {Number(ap) > 10 && <span>{ap}%</span>}
        </div>
      </div>
      {!showLabels && (
        <div className="flex justify-between text-xs text-gray-400">
          <span className="text-green-400">{hp}%</span>
          <span className="text-gray-500">{dp}%</span>
          <span className="text-blue-400">{ap}%</span>
        </div>
      )}
    </div>
  );
}
