"""
Pipeline completo: video → detecciones trackeadas → eventos de juego.

analyze_video() devuelve un dict listo para serializar a JSON e importar
al backend vía POST /api/v1/analysis/import.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Optional

from .config import AnalysisConfig
from .events import extract_events
from .structures import FrameData

logger = logging.getLogger("video_analysis.pipeline")

EVENT_COLORS = {   # BGR, para el video anotado de debug
    "player": (80, 200, 80),
    "ball": (0, 220, 255),
}


def analyze_video(
    video_path: str | Path,
    cfg: Optional[AnalysisConfig] = None,
    annotate_path: Optional[str | Path] = None,
    progress: Optional[Callable[[float], None]] = None,
) -> dict:
    """
    Analiza un video de partido y devuelve los eventos detectados.

    Args:
        video_path: ruta al video (mp4, mkv, etc.)
        cfg: parámetros del pipeline (AnalysisConfig)
        annotate_path: si se pasa, escribe un video con las detecciones
            dibujadas (útil para calibrar umbrales)
        progress: callback opcional con la fracción [0,1] procesada
    """
    try:
        import cv2
    except ImportError as e:
        raise ImportError(
            "El pipeline de video requiere opencv. Instalá las dependencias "
            "con: pip install -r video_analysis/requirements.txt"
        ) from e

    from .detector import PlayerBallDetector
    from . import __version__

    cfg = cfg or AnalysisConfig()
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video no encontrado: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total_frames / native_fps if native_fps > 0 else 0.0
    stride = max(1, round(native_fps / cfg.sample_fps))

    logger.info(
        f"Video: {video_path.name} | {duration:.0f}s @ {native_fps:.1f}fps "
        f"| muestreando 1 de cada {stride} frames"
    )

    detector = PlayerBallDetector(cfg)
    writer = None
    frames: list[FrameData] = []
    t0 = time.time()

    frame_idx = -1
    sample_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        if frame_idx % stride != 0:
            continue

        # Reescalar para acelerar la inferencia
        h, w = frame.shape[:2]
        if w > cfg.max_width:
            scale = cfg.max_width / w
            frame = cv2.resize(frame, (cfg.max_width, int(h * scale)))

        t = frame_idx / native_fps
        data = detector.process(frame, sample_idx, t)
        frames.append(data)
        sample_idx += 1

        if annotate_path is not None:
            if writer is None:
                fh, fw = frame.shape[:2]
                writer = cv2.VideoWriter(
                    str(annotate_path),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    native_fps / stride,
                    (fw, fh),
                )
            _draw_detections(cv2, frame, data)
            writer.write(frame)

        if progress and total_frames > 0 and sample_idx % 50 == 0:
            progress(min(frame_idx / total_frames, 1.0))

    cap.release()
    if writer is not None:
        writer.release()

    elapsed = time.time() - t0
    logger.info(f"Detección: {len(frames)} frames procesados en {elapsed:.0f}s")

    events = extract_events(frames, cfg)
    logger.info(f"Eventos detectados: {len(events)}")

    n_ball = sum(1 for f in frames if f.ball is not None)
    return {
        "video_name": video_path.name,
        "duration_seconds": round(duration, 1),
        "fps": round(native_fps, 2),
        "pipeline_version": __version__,
        "params": {
            **cfg.to_dict(),
            "frames_analyzed": len(frames),
            "ball_detection_rate": round(n_ball / len(frames), 3) if frames else 0,
            "processing_seconds": round(elapsed, 1),
        },
        "events": [e.to_dict() for e in events],
    }


def _draw_detections(cv2, frame, data: FrameData) -> None:
    for p in data.players:
        x1, y1 = int(p.cx - p.w / 2), int(p.cy - p.h / 2)
        x2, y2 = int(p.cx + p.w / 2), int(p.cy + p.h / 2)
        cv2.rectangle(frame, (x1, y1), (x2, y2), EVENT_COLORS["player"], 1)
        cv2.putText(frame, str(p.track_id), (x1, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, EVENT_COLORS["player"], 1)
    if data.ball is not None:
        cv2.circle(frame, (int(data.ball.cx), int(data.ball.cy)),
                   8, EVENT_COLORS["ball"], 2)
    cv2.putText(frame, f"t={data.t:.1f}s", (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
