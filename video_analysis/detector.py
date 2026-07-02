"""
Detección y tracking de jugadores y pelota con YOLOv8 + ByteTrack.

Import lazy de ultralytics: el resto del módulo (events, structures) funciona
sin las dependencias pesadas instaladas.
"""

from __future__ import annotations

import logging
from typing import Optional

from .config import AnalysisConfig
from .structures import BallDetection, FrameData, TrackedPlayer

logger = logging.getLogger("video_analysis.detector")

PERSON_CLASS = 0        # COCO
SPORTS_BALL_CLASS = 32  # COCO


class PlayerBallDetector:
    """Wrapper de YOLOv8 con tracking persistente entre frames."""

    def __init__(self, cfg: Optional[AnalysisConfig] = None):
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise ImportError(
                "El pipeline de video requiere ultralytics. Instalá las "
                "dependencias con: pip install -r video_analysis/requirements.txt"
            ) from e

        self.cfg = cfg or AnalysisConfig()
        logger.info(f"Cargando modelo {self.cfg.model_name}...")
        self.model = YOLO(self.cfg.model_name)

    def process(self, frame_bgr, index: int, t: float) -> FrameData:
        """Detecta y trackea jugadores/pelota en un frame BGR (numpy array)."""
        h, w = frame_bgr.shape[:2]
        results = self.model.track(
            frame_bgr,
            persist=True,
            classes=[PERSON_CLASS, SPORTS_BALL_CLASS],
            conf=min(self.cfg.person_conf, self.cfg.ball_conf),
            device=self.cfg.device,
            tracker="bytetrack.yaml",
            verbose=False,
        )

        data = FrameData(index=index, t=t, frame_w=w, frame_h=h)
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return data

        best_ball_conf = 0.0
        for k in range(len(boxes)):
            cls = int(boxes.cls[k])
            conf = float(boxes.conf[k])
            x1, y1, x2, y2 = (float(v) for v in boxes.xyxy[k])
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

            if cls == PERSON_CLASS and conf >= self.cfg.person_conf:
                tid = int(boxes.id[k]) if boxes.id is not None else -1
                if tid < 0:
                    continue   # sin track asignado todavía
                data.players.append(TrackedPlayer(
                    track_id=tid, cx=cx, cy=cy,
                    w=x2 - x1, h=y2 - y1, conf=conf,
                ))
            elif cls == SPORTS_BALL_CLASS and conf >= self.cfg.ball_conf:
                if conf > best_ball_conf:
                    best_ball_conf = conf
                    data.ball = BallDetection(cx=cx, cy=cy, conf=conf)

        return data
