"""
Módulo de análisis de video para detección de situaciones de juego.

Detecta rucks, tackles, kicks y carries a partir de video de partido usando
YOLOv8 (detección de jugadores y pelota) + tracking + heurísticas espaciales.

Uso típico (CLI):
    python scripts/analyze_video.py partido.mp4 --out eventos.json

El pipeline corre localmente (requiere ultralytics/torch, ver
video_analysis/requirements.txt). Los eventos resultantes se importan al
backend vía POST /api/v1/analysis/import.
"""

from .config import AnalysisConfig
from .structures import BallDetection, Event, FrameData, TrackedPlayer

__version__ = "0.1.0"

__all__ = [
    "AnalysisConfig",
    "BallDetection",
    "Event",
    "FrameData",
    "TrackedPlayer",
    "__version__",
]
