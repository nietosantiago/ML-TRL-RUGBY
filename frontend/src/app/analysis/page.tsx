'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { clsx } from 'clsx';
import { Film, Trash2, Upload } from 'lucide-react';

import { deleteAnalysis, fetchAnalyses, fetchAnalysis, fetchAnalysisSummary } from '@/lib/api';
import { EVENT_META, EVENT_TYPES, formatClock } from '@/lib/events';
import EventTimeline from '@/components/EventTimeline';
import EventBucketsChart from '@/components/EventBucketsChart';
import type { EventType, MatchEvent } from '@/lib/types';

export default function AnalysisPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [activeTypes, setActiveTypes] = useState<Set<EventType>>(new Set(EVENT_TYPES));
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);

  const { data: analyses = [], isLoading } = useQuery({
    queryKey: ['analyses'],
    queryFn: fetchAnalyses,
  });

  // Auto-seleccionar el análisis más reciente
  useEffect(() => {
    if (selectedId == null && analyses.length > 0) setSelectedId(analyses[0].id);
  }, [analyses, selectedId]);

  const { data: detail } = useQuery({
    queryKey: ['analysis', selectedId],
    queryFn: () => fetchAnalysis(selectedId!),
    enabled: selectedId != null,
  });

  const { data: summary } = useQuery({
    queryKey: ['analysis-summary', selectedId],
    queryFn: () => fetchAnalysisSummary(selectedId!),
    enabled: selectedId != null,
  });

  const events = detail?.events ?? [];
  const duration = useMemo(() => {
    if (detail?.duration_seconds) return detail.duration_seconds;
    return events.reduce((max, e) => Math.max(max, e.t_end ?? e.t_start), 0);
  }, [detail, events]);

  const visibleEvents = events.filter((e) => activeTypes.has(e.event_type));

  const seek = (t: number) => {
    const v = videoRef.current;
    if (v) {
      v.currentTime = t;
      v.play().catch(() => {});
    }
  };

  const toggleType = (type: EventType) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const loadVideoFile = (file: File | undefined) => {
    if (!file) return;
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    setVideoUrl(URL.createObjectURL(file));
  };

  const handleDelete = async () => {
    if (selectedId == null || detail == null) return;
    if (!window.confirm(`¿Eliminar el análisis de "${detail.video_name}" y sus ${detail.n_events} eventos?`)) return;
    await deleteAnalysis(selectedId);
    setSelectedId(null);
    queryClient.invalidateQueries({ queryKey: ['analyses'] });
  };

  const isCurrent = (e: MatchEvent) =>
    currentTime >= e.t_start && currentTime <= (e.t_end ?? e.t_start + 3);

  if (isLoading) {
    return <div className="h-40 animate-pulse bg-gray-900 rounded-xl" />;
  }

  if (analyses.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Análisis de video</h1>
        <div className="card space-y-4 max-w-2xl">
          <div className="flex items-center gap-2 text-gray-300">
            <Film size={18} />
            <h2 className="font-semibold">Todavía no hay videos analizados</h2>
          </div>
          <p className="text-sm text-gray-400">
            El pipeline de detección corre localmente sobre el video del partido y detecta
            <span className="text-amber-400"> rucks</span>,
            <span className="text-red-400"> tackles</span>,
            <span className="text-sky-400"> kicks</span> y
            <span className="text-green-400"> carries</span>. Después importa los eventos
            a la plataforma para visualizarlos acá.
          </p>
          <div className="bg-gray-900 rounded-lg p-4 text-xs font-mono text-gray-300 space-y-1">
            <p className="text-gray-500"># 1. Instalar dependencias del pipeline (una vez)</p>
            <p>pip install -r video_analysis/requirements.txt</p>
            <p className="text-gray-500 pt-2"># 2. Analizar el video e importar los eventos</p>
            <p>python scripts/analyze_video.py partido.mp4 --match-id 42 \</p>
            <p className="pl-4">--api-url {process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Análisis de video</h1>

      {/* Selector de análisis */}
      <div className="flex flex-wrap gap-2">
        {analyses.map((a) => (
          <button
            key={a.id}
            onClick={() => setSelectedId(a.id)}
            className={clsx(
              'text-xs px-3 py-1.5 rounded-full border transition-colors',
              selectedId === a.id
                ? 'bg-rugby-green border-rugby-green text-white'
                : 'border-gray-700 text-gray-400 hover:border-gray-500',
            )}
          >
            {a.match_label ?? a.video_name}
            <span className="ml-1.5 opacity-70">({a.n_events})</span>
          </button>
        ))}
      </div>

      {detail && (
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Columna principal: video + timeline + intensidad */}
          <div className="lg:col-span-2 space-y-4">
            <div className="card space-y-3">
              {videoUrl ? (
                <video
                  ref={videoRef}
                  src={videoUrl}
                  controls
                  className="w-full rounded-lg bg-black"
                  onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                />
              ) : (
                <label className="flex flex-col items-center justify-center gap-2 h-48 rounded-lg border-2 border-dashed border-gray-700 text-gray-500 cursor-pointer hover:border-gray-500 hover:text-gray-400 transition-colors">
                  <Upload size={22} />
                  <span className="text-sm">
                    Cargá el video local <span className="font-mono">{detail.video_name}</span> para
                    sincronizarlo con los eventos
                  </span>
                  <span className="text-xs text-gray-600">
                    El video no se sube a ningún servidor — se reproduce desde tu máquina
                  </span>
                  <input
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={(e) => loadVideoFile(e.target.files?.[0])}
                  />
                </label>
              )}

              <EventTimeline
                events={visibleEvents}
                duration={duration}
                currentTime={currentTime}
                activeTypes={activeTypes}
                onSeek={seek}
              />
            </div>

            {summary && summary.timeline.length > 1 && (
              <div className="card">
                <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
                  Intensidad del partido
                </h2>
                <EventBucketsChart
                  timeline={summary.timeline}
                  bucketSeconds={summary.bucket_seconds}
                />
              </div>
            )}
          </div>

          {/* Columna lateral: resumen + lista de eventos */}
          <div className="space-y-4">
            {/* Tarjetas de conteo por tipo (también filtran) */}
            <div className="grid grid-cols-2 gap-2">
              {EVENT_TYPES.map((type) => {
                const count = detail.events_by_type[type] ?? 0;
                const active = activeTypes.has(type);
                return (
                  <button
                    key={type}
                    onClick={() => toggleType(type)}
                    className={clsx(
                      'card text-left py-3 transition-opacity',
                      !active && 'opacity-40',
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: EVENT_META[type].color }}
                      />
                      <span className="text-xs text-gray-400">{EVENT_META[type].plural}</span>
                    </div>
                    <p className="text-2xl font-bold text-white mt-1">{count}</p>
                    {summary?.avg_confidence[type] != null && (
                      <p className="text-[10px] text-gray-500">
                        conf. media {(summary.avg_confidence[type] * 100).toFixed(0)}%
                      </p>
                    )}
                  </button>
                );
              })}
            </div>

            {summary && summary.ruck_total_seconds > 0 && (
              <div className="card py-3">
                <p className="text-xs text-gray-400">Tiempo total en ruck</p>
                <p className="text-xl font-bold text-amber-400">
                  {formatClock(summary.ruck_total_seconds)}
                </p>
              </div>
            )}

            {/* Lista de eventos */}
            <div className="card p-0 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800">
                <h2 className="text-sm font-semibold text-gray-300">
                  Eventos ({visibleEvents.length})
                </h2>
                <button
                  onClick={handleDelete}
                  title="Eliminar este análisis"
                  className="text-gray-600 hover:text-red-400 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <div className="max-h-[28rem] overflow-y-auto divide-y divide-gray-800/60">
                {visibleEvents.map((e) => (
                  <button
                    key={e.id}
                    onClick={() => seek(e.t_start)}
                    className={clsx(
                      'w-full flex items-center gap-3 px-4 py-2 text-left hover:bg-gray-800/60 transition-colors',
                      isCurrent(e) && 'bg-gray-800',
                    )}
                  >
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: EVENT_META[e.event_type].color }}
                    />
                    <span className="text-xs font-mono text-gray-400 w-12">
                      {formatClock(e.t_start)}
                    </span>
                    <span className="text-sm text-gray-200 flex-1">
                      {EVENT_META[e.event_type].label}
                      {e.event_type === 'ruck' && e.n_players != null && (
                        <span className="text-gray-500"> · {e.n_players} jug.</span>
                      )}
                      {e.event_type === 'ruck' && e.t_end != null && (
                        <span className="text-gray-500"> · {(e.t_end - e.t_start).toFixed(1)}s</span>
                      )}
                    </span>
                    {e.confidence != null && (
                      <span className="text-[10px] text-gray-500">
                        {(e.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </button>
                ))}
                {visibleEvents.length === 0 && (
                  <p className="text-sm text-gray-500 text-center py-6">
                    No hay eventos para los filtros activos
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
