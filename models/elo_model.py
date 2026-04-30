"""
Sistema ELO avanzado para el TRL de Rugby.

Características:
- Ventaja de localía configurable
- K-factor dinámico (sensible a la diferencia de puntos y magnitud del partido)
- Ajuste por margen de victoria (margin of victory multiplier)
- Manejo correcto de empates
- Inicialización basada en historial inter-temporadas (partial decay)
- Devuelve probabilidades de victoria/empate/derrota

Referencias:
- Elo (1978) "The Rating of Chessplayers"
- Hvattum & Arntzen (2010) para adaptación al fútbol con MOV
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Configuración del sistema ELO
# ---------------------------------------------------------------------------

@dataclass
class EloConfig:
    initial_rating:      float = 1500.0   # rating inicial para equipo nuevo
    k_base:              float = 32.0     # K base (más alto = ajuste más rápido)
    home_advantage:      float = 60.0     # puntos de ventaja de localía en la escala ELO
    season_decay:        float = 0.3      # qué fracción del rating se regresa a la media entre temporadas
    max_mov_multiplier:  float = 2.5      # multiplicador máximo por margen de victoria
    draw_threshold:      float = 0.05     # probabilidad implícita de empate base
    scale:               float = 400.0    # escala (400 = estándar; 173.7 = logístico natural)


# ---------------------------------------------------------------------------
#  Dataclass de resultado individual
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    home_team_id:   int
    away_team_id:   int
    home_score:     int
    away_score:     int
    home_elo_before: float = 0.0
    away_elo_before: float = 0.0
    home_elo_after:  float = 0.0
    away_elo_after:  float = 0.0
    home_win_prob:   float = 0.0
    draw_prob:       float = 0.0
    away_win_prob:   float = 0.0


# ---------------------------------------------------------------------------
#  Sistema ELO principal
# ---------------------------------------------------------------------------

class EloSystem:
    def __init__(self, config: Optional[EloConfig] = None):
        self.config = config or EloConfig()
        self.ratings: dict[int, float] = {}       # team_id -> rating actual
        self.history:  list[MatchResult] = []

    # ------------------------------------------------------------------
    #  Ratings
    # ------------------------------------------------------------------

    def get_rating(self, team_id: int) -> float:
        return self.ratings.get(team_id, self.config.initial_rating)

    def set_rating(self, team_id: int, rating: float) -> None:
        self.ratings[team_id] = rating

    def load_ratings_from_db(self, conn, exclude_season: Optional[int] = None) -> None:
        """
        Carga los últimos ratings ELO de la DB, opcionalmente ignorando
        una temporada (útil para recalcular desde cero una temporada).
        """
        with conn.cursor() as cur:
            query = """
                SELECT DISTINCT ON (team_id)
                    team_id, rating_after
                FROM elo_ratings
            """
            if exclude_season is not None:
                query += " WHERE season_id != %s"
                query += " ORDER BY team_id, created_at DESC"
                cur.execute(query, (exclude_season,))
            else:
                query += " ORDER BY team_id, created_at DESC"
                cur.execute(query)

            for team_id, rating in cur.fetchall():
                self.ratings[team_id] = rating

        logger.info(f"ELO: cargados {len(self.ratings)} ratings desde DB")

    def apply_season_decay(self) -> None:
        """
        Al inicio de cada temporada, ajusta los ratings hacia la media
        (regresión a la media). Esto evita que equipos dominen indefinidamente
        solo por inercia histórica.
        """
        mean_rating = np.mean(list(self.ratings.values())) if self.ratings else self.config.initial_rating
        decay = self.config.season_decay
        for team_id in self.ratings:
            self.ratings[team_id] = (
                self.ratings[team_id] * (1 - decay) + mean_rating * decay
            )

    # ------------------------------------------------------------------
    #  Probabilidades
    # ------------------------------------------------------------------

    def expected_score(self, rating_a: float, rating_b: float, is_a_home: bool) -> float:
        """
        Probabilidad esperada de victoria de A contra B.
        Incluye ventaja de localía si is_a_home=True.
        """
        adj_rating_a = rating_a + (self.config.home_advantage if is_a_home else 0)
        exponent = (rating_b - adj_rating_a) / self.config.scale
        return 1.0 / (1.0 + math.pow(10, exponent))

    def win_draw_loss_probs(
        self, home_id: int, away_id: int
    ) -> tuple[float, float, float]:
        """
        Retorna (P(home win), P(draw), P(away win)).

        El modelo ELO puro da P(home) y 1-P(home).
        El empate se aproxima modelando que ocurre cuando el "verdadero"
        resultado cae en un rango estrecho de igual aptitud.
        La probabilidad de empate es máxima cuando los equipos son iguales
        y se distribuye simétricamente alrededor de P=0.5.
        """
        p_home_raw = self.expected_score(
            self.get_rating(home_id),
            self.get_rating(away_id),
            is_a_home=True,
        )

        # Función de empate: mayor cuando los equipos son equilibrados
        # draw_prob_max en p=0.5, se reduce hacia 0 en extremos
        draw_prob = self.config.draw_threshold * (
            1 - 4 * (p_home_raw - 0.5) ** 2
        )
        draw_prob = max(0.0, draw_prob)

        # Distribuir el empate proporcionalmente entre home y away
        p_home = p_home_raw * (1 - draw_prob)
        p_away = (1 - p_home_raw) * (1 - draw_prob)

        # Normalizar para garantizar suma = 1
        total = p_home + draw_prob + p_away
        return p_home / total, draw_prob / total, p_away / total

    # ------------------------------------------------------------------
    #  K-factor dinámico
    # ------------------------------------------------------------------

    def dynamic_k(self, point_diff: int) -> float:
        """
        K aumenta con la diferencia de puntos pero con rendimientos decrecientes.
        Fórmula inspirada en FiveThirtyEight NFL ELO:
        MOV_multiplier = ln(abs(point_diff) + 1) * (2.2 / (autocorr_factor + 2.2))
        Aquí simplificamos sin el factor de autocorrelación.
        """
        if point_diff == 0:
            return self.config.k_base

        mov_mult = math.log(abs(point_diff) + 1)
        mov_mult = min(mov_mult, math.log(self.config.max_mov_multiplier * 10 + 1))
        # Normalizar: log(1+1)=0.693... → queremos que un punto de diferencia no infle demasiado
        mov_mult_normalized = mov_mult / math.log(2)    # = 1 para diff=1
        mov_mult_normalized = min(mov_mult_normalized, self.config.max_mov_multiplier)

        return self.config.k_base * mov_mult_normalized

    # ------------------------------------------------------------------
    #  Actualización de un partido
    # ------------------------------------------------------------------

    def update(
        self,
        home_id: int,
        away_id: int,
        home_score: int,
        away_score: int,
        season_id: Optional[int] = None,
        round_num: Optional[int] = None,
        match_id: Optional[int] = None,
    ) -> MatchResult:
        """
        Procesa un partido y actualiza los ratings de ambos equipos.
        Retorna un MatchResult con los valores antes/después.
        """
        r_home_before = self.get_rating(home_id)
        r_away_before = self.get_rating(away_id)

        p_home, p_draw, p_away = self.win_draw_loss_probs(home_id, away_id)

        # Score observado
        point_diff = home_score - away_score
        if home_score > away_score:
            s_home, s_away = 1.0, 0.0
            result_home, result_away = "win", "loss"
        elif home_score < away_score:
            s_home, s_away = 0.0, 1.0
            result_home, result_away = "loss", "win"
        else:
            s_home, s_away = 0.5, 0.5
            result_home, result_away = "draw", "draw"

        k = self.dynamic_k(abs(point_diff))

        # Ajuste ELO: home usa p_home como expected; away usa p_away
        delta_home = k * (s_home - p_home)
        delta_away = k * (s_away - p_away)

        r_home_after = r_home_before + delta_home
        r_away_after = r_away_before + delta_away

        self.ratings[home_id] = r_home_after
        self.ratings[away_id] = r_away_after

        result = MatchResult(
            home_team_id=home_id,
            away_team_id=away_id,
            home_score=home_score,
            away_score=away_score,
            home_elo_before=r_home_before,
            away_elo_before=r_away_before,
            home_elo_after=r_home_after,
            away_elo_after=r_away_after,
            home_win_prob=p_home,
            draw_prob=p_draw,
            away_win_prob=p_away,
        )
        self.history.append(result)
        return result

    # ------------------------------------------------------------------
    #  Procesar temporada completa
    # ------------------------------------------------------------------

    def process_season(
        self,
        matches: list[tuple],
        season_id: int,
    ) -> list[tuple]:
        """
        Procesa todos los partidos de una temporada en orden cronológico.
        matches: lista de (match_id, round, date, home_id, away_id, home_score, away_score)

        Retorna lista de tuplas para insertar en elo_ratings:
        (team_id, season_id, round, match_id, rating_before, rating_after,
         opponent_id, result, is_home, score_diff)
        """
        records = []
        for match in matches:
            (m_id, rnd, m_date, h_id, a_id, hs, as_) = match
            if hs is None or as_ is None:
                continue

            r = self.update(h_id, a_id, hs, as_, season_id, rnd, m_id)

            records.append((
                h_id, season_id, rnd, m_id,
                r.home_elo_before, r.home_elo_after,
                a_id, r.home_win_prob > r.away_win_prob and "win" or
                      (r.home_win_prob < r.away_win_prob and "loss" or "draw"),
                True, hs - as_,
            ))
            records.append((
                a_id, season_id, rnd, m_id,
                r.away_elo_before, r.away_elo_after,
                h_id, r.away_win_prob > r.home_win_prob and "win" or
                      (r.away_win_prob < r.home_win_prob and "loss" or "draw"),
                False, as_ - hs,
            ))

        return records

    # ------------------------------------------------------------------
    #  Predicción sin actualizar ratings (solo lectura)
    # ------------------------------------------------------------------

    def predict(
        self, home_id: int, away_id: int
    ) -> dict[str, float]:
        """Devuelve probabilidades sin modificar los ratings actuales."""
        p_home, p_draw, p_away = self.win_draw_loss_probs(home_id, away_id)
        return {
            "home_win": round(p_home, 4),
            "draw":     round(p_draw, 4),
            "away_win": round(p_away, 4),
            "home_elo": round(self.get_rating(home_id), 1),
            "away_elo": round(self.get_rating(away_id), 1),
            "elo_diff": round(self.get_rating(home_id) - self.get_rating(away_id), 1),
        }

    def get_all_ratings(self) -> dict[int, float]:
        return dict(self.ratings)

    def get_ranking(self) -> list[tuple[int, float]]:
        return sorted(self.ratings.items(), key=lambda x: -x[1])
