"""
Simulación Monte Carlo de la temporada TRL.

Algoritmo:
1. Tomar la tabla actual y los partidos restantes
2. Para cada iteración:
   a. Simular cada partido pendiente usando probabilidades del modelo
   b. Aplicar puntos de bonus (4 tries, perder por <=7)
   c. Calcular posiciones finales
3. Agregar distribuciones a lo largo de las iteraciones

Features:
- 10.000+ iteraciones (configurable)
- Soporte para ELO, Logística y XGBoost como fuente de probabilidades
- Intervalos de confianza (p5, p25, p50, p75, p95) para puntos finales
- Distribución de posiciones por equipo
- Probabilidad de cada posición, top 4 (semis), campeón
- Simulación personalizada (usuario fija algunos resultados)
- Paralelización con numpy vectorizada (sin multiprocessing para compatibilidad)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Any, Callable

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Estructuras de datos
# ---------------------------------------------------------------------------

@dataclass
class MatchOdds:
    """Probabilidades de un partido pendiente."""
    match_id:    int
    home_team_id: int
    away_team_id: int
    p_home_win:  float
    p_draw:      float
    p_away_win:  float
    # Resultado fijado por el usuario (None = simular)
    fixed_result: Optional[str] = None   # 'home', 'draw', 'away'


@dataclass
class TeamStanding:
    """Estado de un equipo en la tabla."""
    team_id:     int
    team_name:   str
    total_points: int
    point_diff:  int    # diferencia de puntos acumulada (desempate)
    tries_for:   int    # tries anotados (segundo criterio de desempate)


@dataclass
class SimulationConfig:
    n_iterations:       int   = 10_000
    semifinal_spots:    int   = 4        # cuántos equipos clasifican a semis
    include_bonus_try:  float = 0.35     # probabilidad de que un equipo anote 4+ tries
    include_bonus_loss: float = 0.30     # prob. de que el perdedor pierda por <= 7
    random_seed:        Optional[int] = 42


@dataclass
class SimulationResult:
    """Resultados agregados de la simulación."""
    team_ids:           list[int]
    team_names:         dict[int, str]
    n_iterations:       int

    # Matrices de resultados: shape (n_teams, n_positions)
    position_counts:    np.ndarray       # veces que cada equipo terminó en cada posición
    champion_count:     np.ndarray       # veces que cada equipo fue campeón
    semifinal_count:    np.ndarray       # veces que cada equipo clasificó a semis

    # Distribución de puntos: shape (n_teams, n_iterations)
    points_distribution: np.ndarray

    # --- Propiedades calculadas ---
    @property
    def n_teams(self) -> int:
        return len(self.team_ids)

    @property
    def position_probs(self) -> np.ndarray:
        """Probabilidad de cada posición. Shape: (n_teams, n_positions)."""
        return self.position_counts / self.n_iterations

    @property
    def champion_probs(self) -> np.ndarray:
        return self.champion_count / self.n_iterations

    @property
    def semifinal_probs(self) -> np.ndarray:
        return self.semifinal_count / self.n_iterations

    def points_percentiles(self, team_idx: int) -> dict[str, float]:
        pts = self.points_distribution[team_idx]
        return {
            "mean": float(np.mean(pts)),
            "std":  float(np.std(pts)),
            "p5":   float(np.percentile(pts, 5)),
            "p25":  float(np.percentile(pts, 25)),
            "p50":  float(np.percentile(pts, 50)),
            "p75":  float(np.percentile(pts, 75)),
            "p95":  float(np.percentile(pts, 95)),
        }

    def to_dict(self) -> dict:
        """Serializa para guardar en DB o devolver por API."""
        result = {
            "n_iterations": self.n_iterations,
            "teams": {},
        }
        for i, tid in enumerate(self.team_ids):
            name = self.team_names.get(tid, str(tid))
            pos_probs = {
                f"pos_{j+1}": float(self.position_probs[i, j])
                for j in range(self.n_teams)
            }
            result["teams"][str(tid)] = {
                "team_id":        tid,
                "team_name":      name,
                "champion_prob":  float(self.champion_probs[i]),
                "semifinal_prob": float(self.semifinal_probs[i]),
                "position_probs": pos_probs,
                "points":         self.points_percentiles(i),
            }
        return result


# ---------------------------------------------------------------------------
#  Motor de simulación vectorizado
# ---------------------------------------------------------------------------

class MonteCarloSimulator:
    """
    Simula la temporada restante N veces usando numpy para eficiencia.
    """

    def __init__(
        self,
        config: Optional[SimulationConfig] = None,
    ):
        self.config = config or SimulationConfig()
        if self.config.random_seed is not None:
            np.random.seed(self.config.random_seed)

    def simulate(
        self,
        current_standings: list[TeamStanding],
        pending_matches: list[MatchOdds],
        semifinal_spots: Optional[int] = None,
    ) -> SimulationResult:
        """
        Ejecuta la simulación completa.

        Args:
            current_standings: tabla actual con puntos acumulados hasta hoy
            pending_matches: partidos restantes con sus probabilidades
            semifinal_spots: cuántos equipos clasifican (default: config.semifinal_spots)

        Returns:
            SimulationResult con distribuciones completas
        """
        n_iter    = self.config.n_iterations
        n_teams   = len(current_standings)
        semi_n    = semifinal_spots or self.config.semifinal_spots
        n_matches = len(pending_matches)

        team_ids  = [ts.team_id for ts in current_standings]
        team_names = {ts.team_id: ts.team_name for ts in current_standings}
        team_idx  = {tid: i for i, tid in enumerate(team_ids)}

        logger.info(
            f"Monte Carlo: {n_iter} iteraciones, "
            f"{n_teams} equipos, {n_matches} partidos pendientes"
        )

        # --- Estado inicial (puntos y diferencia de puntos) ---
        base_points = np.array([ts.total_points for ts in current_standings], dtype=np.float32)
        base_pd     = np.array([ts.point_diff   for ts in current_standings], dtype=np.float32)
        base_tries  = np.array([ts.tries_for    for ts in current_standings], dtype=np.float32)

        # Matrices que acumulan resultados: (n_teams, n_iter)
        sim_points = np.tile(base_points.reshape(-1, 1), (1, n_iter))     # (n_teams, n_iter)
        sim_pd     = np.tile(base_pd.reshape(-1, 1),     (1, n_iter))
        sim_tries  = np.tile(base_tries.reshape(-1, 1),  (1, n_iter))

        # --- Separar partidos fijos de partidos a simular ---
        fixed_matches = [(m, m.fixed_result) for m in pending_matches if m.fixed_result]
        free_matches  = [m for m in pending_matches if not m.fixed_result]

        # Aplicar partidos fijos a TODAS las iteraciones
        for match, result in fixed_matches:
            self._apply_fixed_match(
                match, result,
                team_idx, sim_points, sim_pd, sim_tries,
            )

        # --- Simular partidos libres en batch (vectorizado) ---
        if free_matches:
            self._simulate_free_matches(
                free_matches, team_idx, sim_points, sim_pd, sim_tries, n_iter
            )

        # --- Calcular posiciones finales en cada iteración ---
        position_counts  = np.zeros((n_teams, n_teams), dtype=np.int32)
        champion_count   = np.zeros(n_teams, dtype=np.int32)
        semifinal_count  = np.zeros(n_teams, dtype=np.int32)

        for it in range(n_iter):
            pts    = sim_points[:, it]
            pd_col = sim_pd[:, it]
            tries  = sim_tries[:, it]

            # Ordenar por: puntos desc, diferencia de puntos desc, tries desc
            order = np.lexsort((-tries, -pd_col, -pts))

            for rank, team_idx_sorted in enumerate(order):
                position_counts[team_idx_sorted, rank] += 1
                if rank == 0:
                    champion_count[team_idx_sorted] += 1
                if rank < semi_n:
                    semifinal_count[team_idx_sorted] += 1

        return SimulationResult(
            team_ids=team_ids,
            team_names=team_names,
            n_iterations=n_iter,
            position_counts=position_counts,
            champion_count=champion_count,
            semifinal_count=semifinal_count,
            points_distribution=sim_points,
        )

    def _simulate_free_matches(
        self,
        matches: list[MatchOdds],
        team_idx: dict[int, int],
        sim_points: np.ndarray,
        sim_pd: np.ndarray,
        sim_tries: np.ndarray,
        n_iter: int,
    ) -> None:
        """
        Simula todos los partidos libres de forma vectorizada.
        Para cada partido, genera n_iter resultados aleatorios simultáneamente.
        """
        for match in matches:
            h_idx = team_idx.get(match.home_team_id)
            a_idx = team_idx.get(match.away_team_id)
            if h_idx is None or a_idx is None:
                continue

            # Generar resultado: 0=home, 1=draw, 2=away usando multinomial
            probs = np.array([match.p_home_win, match.p_draw, match.p_away_win])
            probs = np.clip(probs, 0, 1)
            probs /= probs.sum()    # normalizar por si acaso

            outcomes = np.random.choice([0, 1, 2], size=n_iter, p=probs)

            home_wins = outcomes == 0
            draws     = outcomes == 1
            away_wins = outcomes == 2

            # Puntos de partido
            # Home win: home +4, away +0
            # Draw: home +2, away +2
            # Away win: home +0, away +4
            sim_points[h_idx] += np.where(home_wins, 4, np.where(draws, 2, 0))
            sim_points[a_idx] += np.where(away_wins, 4, np.where(draws, 2, 0))

            # Bonus try (independiente del resultado)
            h_bonus_try = np.random.random(n_iter) < self.config.include_bonus_try
            a_bonus_try = np.random.random(n_iter) < self.config.include_bonus_try
            sim_points[h_idx] += h_bonus_try.astype(np.float32)
            sim_points[a_idx] += a_bonus_try.astype(np.float32)

            # Bonus losing (solo para el perdedor, si pierde por <= 7)
            h_bonus_loss = away_wins & (np.random.random(n_iter) < self.config.include_bonus_loss)
            a_bonus_loss = home_wins & (np.random.random(n_iter) < self.config.include_bonus_loss)
            sim_points[h_idx] += h_bonus_loss.astype(np.float32)
            sim_points[a_idx] += a_bonus_loss.astype(np.float32)

            # Diferencia de puntos estimada (para desempate)
            # Usamos una diferencia esperada basada en la probabilidad
            # Un equipo que tiene 90% de ganar probablemente gane por más puntos
            expected_margin_h = (match.p_home_win - match.p_away_win) * 20
            noise = np.random.normal(0, 8, n_iter).astype(np.float32)
            sim_match_margin = np.where(
                home_wins,
                np.abs(expected_margin_h + noise) + 1,
                np.where(
                    away_wins,
                    -(np.abs(expected_margin_h + noise) + 1),
                    noise * 0.1,    # empate: cerca de 0
                )
            ).astype(np.float32)

            sim_pd[h_idx] += sim_match_margin
            sim_pd[a_idx] -= sim_match_margin

            # Tries estimados
            mean_tries = 3.0
            h_tries = np.random.poisson(mean_tries, n_iter).astype(np.float32)
            a_tries = np.random.poisson(mean_tries, n_iter).astype(np.float32)
            sim_tries[h_idx] += h_tries
            sim_tries[a_idx] += a_tries

    def _apply_fixed_match(
        self,
        match: MatchOdds,
        result: str,
        team_idx: dict[int, int],
        sim_points: np.ndarray,
        sim_pd: np.ndarray,
        sim_tries: np.ndarray,
    ) -> None:
        """Aplica un partido con resultado fijo a todas las iteraciones."""
        h_idx = team_idx.get(match.home_team_id)
        a_idx = team_idx.get(match.away_team_id)
        if h_idx is None or a_idx is None:
            return

        n_iter = sim_points.shape[1]

        if result == "home":
            sim_points[h_idx] += 4
            sim_pd[h_idx] += 10
            sim_pd[a_idx] -= 10
        elif result == "away":
            sim_points[a_idx] += 4
            sim_pd[a_idx] += 10
            sim_pd[h_idx] -= 10
        elif result == "draw":
            sim_points[h_idx] += 2
            sim_points[a_idx] += 2

        # Tries medios para partidos fijos
        mean_tries = 3
        sim_tries[h_idx] += mean_tries
        sim_tries[a_idx] += mean_tries


# ---------------------------------------------------------------------------
#  Helpers para cargar datos desde DB
# ---------------------------------------------------------------------------

def load_current_standings_from_db(
    conn, season_id: int
) -> list[TeamStanding]:
    """Carga la tabla de posiciones actual desde la DB."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT cs.team_id, t.name,
                   cs.total_points,
                   (cs.points_for - cs.points_against) AS point_diff,
                   cs.tries_for
            FROM current_standings cs
            JOIN teams t ON t.id = cs.team_id
            WHERE cs.season_id = %s
            ORDER BY cs.position
        """, (season_id,))
        rows = cur.fetchall()

    return [
        TeamStanding(
            team_id=row[0],
            team_name=row[1],
            total_points=row[2] or 0,
            point_diff=row[3] or 0,
            tries_for=row[4] or 0,
        )
        for row in rows
    ]


def load_pending_matches_from_db(
    conn,
    season_id: int,
    predictor,       # objeto con método predict_single(features) -> dict
    get_features,    # función (conn, team_id, season_id) -> TeamFeatures
    build_features,  # función (home_feat, away_feat) -> np.ndarray
) -> list[MatchOdds]:
    """
    Carga los partidos pendientes y calcula las probabilidades usando el predictor.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.id, m.home_team_id, m.away_team_id
            FROM matches m
            WHERE m.season_id = %s AND m.is_played = FALSE
            ORDER BY m.round, m.match_date
        """, (season_id,))
        rows = cur.fetchall()

    odds_list = []
    for m_id, h_id, a_id in rows:
        h_feat = get_features(conn, h_id, season_id)
        a_feat = get_features(conn, a_id, season_id)
        features = build_features(h_feat, a_feat)
        pred = predictor.predict_single(features)

        odds_list.append(MatchOdds(
            match_id=m_id,
            home_team_id=h_id,
            away_team_id=a_id,
            p_home_win=pred.get("home_win", 0.4),
            p_draw=pred.get("draw", 0.15),
            p_away_win=pred.get("away_win", 0.45),
        ))

    return odds_list
