"""Endpoints de simulación Monte Carlo."""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.schemas import (
    SimulationRequest, SimulationOut, TeamSimResult,
    CustomSimulationRequest, CustomSimulationOut,
    FixedResult,
)
from ..config import get_settings

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

router = APIRouter(prefix="/simulate", tags=["simulation"])
settings = get_settings()


async def _get_season_id(db: AsyncSession, season_id: Optional[int]) -> int:
    if season_id:
        return season_id
    result = await db.execute(text("SELECT id FROM seasons WHERE is_current = TRUE LIMIT 1"))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No hay temporada activa")
    return row[0]


def _run_simulation_sync(
    season_id: int,
    n_iterations: int,
    model_type: str,
    fixed_results: list[FixedResult] = None,
) -> dict:
    """
    Ejecuta la simulación Monte Carlo en modo síncrono.
    Se llama desde el endpoint usando run_in_executor para no bloquear.
    """
    import os
    import psycopg2
    from models.elo_model import EloSystem
    from models.feature_engineering import (
        get_current_team_features, build_match_features,
    )
    from models.monte_carlo import (
        MonteCarloSimulator, SimulationConfig,
        load_current_standings_from_db,
        load_pending_matches_from_db,
        MatchOdds,
    )

    conn = psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )

    try:
        standings = load_current_standings_from_db(conn, season_id)
        if not standings:
            raise ValueError("No hay datos en la tabla de posiciones")

        # Construir predictor
        if model_type == "elo":
            elo = EloSystem()
            elo.load_ratings_from_db(conn)

            class EloPredictor:
                def predict_single(self, features):
                    # Para ELO usamos los ratings directamente (features[1]=home_elo, [2]=away_elo)
                    from models.feature_engineering import FEATURE_NAMES
                    h_elo = features[FEATURE_NAMES.index("elo_home")]
                    a_elo = features[FEATURE_NAMES.index("elo_away")]
                    elo.set_rating(-1, h_elo)
                    elo.set_rating(-2, a_elo)
                    return elo.predict(-1, -2)

            predictor = EloPredictor()
        else:
            model_path = Path("data/models") / f"{model_type}_model.pkl"
            if not model_path.exists():
                elo = EloSystem()
                elo.load_ratings_from_db(conn)
                from models.elo_model import EloSystem as ES
                class FallbackPredictor:
                    def predict_single(self, features):
                        from models.feature_engineering import FEATURE_NAMES
                        h_elo = features[FEATURE_NAMES.index("elo_home")]
                        a_elo = features[FEATURE_NAMES.index("elo_away")]
                        elo.set_rating(-1, h_elo)
                        elo.set_rating(-2, a_elo)
                        return elo.predict(-1, -2)
                predictor = FallbackPredictor()
            elif model_type == "logistic":
                from models.logistic_model import LogisticMatchPredictor
                predictor = LogisticMatchPredictor.load(str(model_path))
            else:
                from models.xgboost_model import XGBoostMatchPredictor
                predictor = XGBoostMatchPredictor.load(str(model_path))

        pending = load_pending_matches_from_db(
            conn, season_id, predictor,
            get_current_team_features,
            build_match_features,
        )

        # Aplicar resultados fijos si existen
        if fixed_results:
            fixed_map = {fr.match_id: fr.result for fr in fixed_results}
            for m in pending:
                if m.match_id in fixed_map:
                    m.fixed_result = fixed_map[m.match_id]

        config = SimulationConfig(
            n_iterations=n_iterations,
            semifinal_spots=settings.semifinal_spots,
        )
        simulator = MonteCarloSimulator(config)
        sim_result = simulator.simulate(standings, pending)

        return sim_result.to_dict()
    finally:
        conn.close()


@router.post("/season", response_model=SimulationOut)
async def simulate_season(
    req: SimulationRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Simula el resto de la temporada N veces y retorna distribuciones
    de posición, puntos y probabilidades de clasificación.
    """
    import asyncio
    season_id = await _get_season_id(db, req.season_id)

    loop = asyncio.get_event_loop()
    sim_data = await loop.run_in_executor(
        None,
        _run_simulation_sync,
        season_id,
        req.n_iterations,
        req.model,
        None,
    )

    teams_out = []
    for tid_str, team_data in sim_data["teams"].items():
        pts = team_data["points"]
        teams_out.append(TeamSimResult(
            team_id=team_data["team_id"],
            team_name=team_data["team_name"],
            champion_prob=team_data["champion_prob"],
            semifinal_prob=team_data["semifinal_prob"],
            position_probs=team_data["position_probs"],
            points_mean=pts["mean"],
            points_p5=pts["p5"],
            points_p50=pts["p50"],
            points_p95=pts["p95"],
        ))

    # Ordenar por probabilidad de ser campeón desc
    teams_out.sort(key=lambda t: -t.champion_prob)

    return SimulationOut(
        season_id=season_id,
        n_iterations=sim_data["n_iterations"],
        model_used=req.model,
        computed_at=datetime.now(),
        teams=teams_out,
    )


@router.post("/custom", response_model=CustomSimulationOut)
async def custom_simulation(
    req: CustomSimulationRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Simulación con resultados fijados por el usuario.
    El usuario puede fijar el resultado de partidos específicos
    y ver cómo cambian las probabilidades.
    """
    import asyncio
    season_id = await _get_season_id(db, req.season_id)

    loop = asyncio.get_event_loop()
    sim_data = await loop.run_in_executor(
        None,
        _run_simulation_sync,
        season_id,
        req.n_iterations,
        req.model,
        req.fixed_results,
    )

    teams_out = []
    for tid_str, team_data in sim_data["teams"].items():
        pts = team_data["points"]
        teams_out.append(TeamSimResult(
            team_id=team_data["team_id"],
            team_name=team_data["team_name"],
            champion_prob=team_data["champion_prob"],
            semifinal_prob=team_data["semifinal_prob"],
            position_probs=team_data["position_probs"],
            points_mean=pts["mean"],
            points_p5=pts["p5"],
            points_p50=pts["p50"],
            points_p95=pts["p95"],
        ))

    teams_out.sort(key=lambda t: -t.champion_prob)

    return CustomSimulationOut(
        season_id=season_id,
        n_iterations=sim_data["n_iterations"],
        model_used=req.model,
        computed_at=datetime.now(),
        teams=teams_out,
        fixed_results_applied=len(req.fixed_results),
    )
