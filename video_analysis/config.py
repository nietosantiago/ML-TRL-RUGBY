"""
Parámetros del pipeline de detección de eventos.

Las distancias se expresan en unidades de "altura mediana de jugador" (H)
para ser invariantes al zoom de la cámara, y las velocidades en H/segundo.
La velocidad se compensa por el paneo de la cámara (se resta el desplazamiento
mediano de todos los jugadores en cada frame).
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class AnalysisConfig:
    # ── Muestreo y detección ────────────────────────────────────────────────
    sample_fps: float = 8.0          # frames analizados por segundo de video
    max_width: int = 1280            # se reescala el frame si es más ancho
    model_name: str = "yolov8n.pt"   # yolov8s.pt mejora precisión si hay GPU
    person_conf: float = 0.35
    ball_conf: float = 0.20
    device: Optional[str] = None     # None = auto (cuda si está disponible)

    # ── Escala ──────────────────────────────────────────────────────────────
    # Si un frame no tiene suficientes jugadores para estimar la altura
    # mediana, se usa esta fracción de la altura del frame como fallback.
    fallback_scale_frac: float = 0.12
    velocity_smooth_window: int = 3  # frames para suavizar velocidades

    # ── Ruck ────────────────────────────────────────────────────────────────
    cluster_link_dist: float = 0.9   # H — distancia máxima entre centros para agrupar
    ruck_min_players: int = 4
    ruck_max_speed: float = 1.2      # H/s — velocidad media máxima del grupo
    ruck_min_duration: float = 1.5   # s
    ruck_gap_tolerance: float = 0.6  # s sin ver el grupo antes de cerrarlo

    # ── Tackle ──────────────────────────────────────────────────────────────
    tackle_contact_dist: float = 0.55    # H — contacto entre dos jugadores
    tackle_approach_speed: float = 2.0   # H/s — velocidad de aproximación previa
    tackle_fall_window: float = 1.2      # s para confirmar la caída tras el contacto
    tackle_fall_aspect: float = 1.0      # w/h ≥ esto = jugador en el piso
    tackle_fall_height_ratio: float = 0.65  # o altura < 65% de su mediana reciente
    tackle_cooldown: float = 2.5         # s — anti-duplicados
    tackle_cooldown_dist: float = 2.0    # H

    # ── Carry ───────────────────────────────────────────────────────────────
    possession_dist: float = 0.8     # H — pelota "en manos" de un jugador
    carry_min_speed: float = 1.8     # H/s — con pelota detectada
    carry_min_duration: float = 0.8  # s
    breakaway_speed: float = 3.0     # H/s — fallback sin pelota (corte de línea)
    breakaway_min_duration: float = 1.0   # s
    breakaway_isolation: float = 1.2      # H — sin rivales cerca
    carry_cooldown: float = 2.0      # s entre carries del mismo jugador

    # ── Kick ────────────────────────────────────────────────────────────────
    kick_speed_min: float = 6.0      # H/s — pico de velocidad de la pelota
    kick_near_player_dist: float = 1.2   # H — la pelota estaba junto a alguien
    kick_separation_dist: float = 2.0    # H — y se aleja de todos
    kick_separation_window: float = 0.6  # s
    kick_cooldown: float = 3.0       # s

    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("extra", None)
        return d
