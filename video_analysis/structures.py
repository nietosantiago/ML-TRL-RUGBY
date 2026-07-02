"""Estructuras de datos compartidas entre detector, pipeline y heurísticas."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TrackedPlayer:
    """Jugador detectado en un frame, con ID persistente de tracking."""
    track_id: int
    cx: float       # centro del bbox en píxeles
    cy: float
    w: float
    h: float
    conf: float


@dataclass
class BallDetection:
    """Pelota detectada en un frame (clase 'sports ball' de COCO)."""
    cx: float
    cy: float
    conf: float


@dataclass
class FrameData:
    """Detecciones de un frame muestreado del video."""
    index: int              # índice del frame muestreado (no del video original)
    t: float                # segundos desde el inicio del video
    frame_w: int
    frame_h: int
    players: list[TrackedPlayer] = field(default_factory=list)
    ball: Optional[BallDetection] = None


@dataclass
class Event:
    """Situación de juego detectada: ruck | tackle | kick | carry."""
    event_type: str
    t_start: float
    t_end: Optional[float] = None
    confidence: float = 0.5
    n_players: Optional[int] = None
    x_norm: Optional[float] = None   # posición normalizada [0,1] en el frame
    y_norm: Optional[float] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "t_start": round(self.t_start, 2),
            "t_end": round(self.t_end, 2) if self.t_end is not None else None,
            "confidence": round(self.confidence, 3),
            "n_players": self.n_players,
            "x_norm": round(self.x_norm, 4) if self.x_norm is not None else None,
            "y_norm": round(self.y_norm, 4) if self.y_norm is not None else None,
            "meta": self.meta,
        }
