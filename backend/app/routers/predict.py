"""Endpoints de predicción de partidos."""

import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.schemas import MatchPredictionRequest, MatchPredictionOut
from ..config import get_settings

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

router = APIRouter(prefix="/predict", tags=["prediction"])
settings = get_settings()


async def _get_season_id(db: AsyncSession, season_id: Optional[int]) -> int:
    if season_id:
        return season_id
    result = await db.execute(text("SELECT id FROM seasons WHERE is_current = TRUE LIMIT 1"))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No hay temporada activa")
    return row[0]


@router.post("/match", response_model=MatchPredictionOut)
async def predict_match(
    req: MatchPredictionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Predice el resultado de un partido entre dos equipos.
    Soporta modelos: 'elo', 'logistic', 'xgboost'.
    """
    season_id = await _get_season_id(db, req.season_id)

    # Obtener nombres de equipos
    result = await db.execute(
        text("SELECT id, name FROM teams WHERE id IN (:h, :a)"),
        {"h": req.home_team_id, "a": req.away_team_id},
    )
    teams = {r.id: r.name for r in result.fetchall()}

    if req.home_team_id not in teams or req.away_team_id not in teams:
        raise HTTPException(status_code=404, detail="Equipo(s) no encontrado(s)")

    model_type = req.model.lower()

    if model_type == "elo":
        prediction = await _predict_elo(db, req.home_team_id, req.away_team_id, season_id)
    elif model_type in ("logistic", "xgboost"):
        prediction = await _predict_ml(db, req.home_team_id, req.away_team_id, season_id, model_type)
    else:
        raise HTTPException(status_code=400, detail=f"Modelo desconocido: {model_type}")

    return MatchPredictionOut(
        home_team_id=req.home_team_id,
        away_team_id=req.away_team_id,
        home_team_name=teams.get(req.home_team_id),
        away_team_name=teams.get(req.away_team_id),
        home_win_prob=prediction["home_win"],
        draw_prob=prediction["draw"],
        away_win_prob=prediction["away_win"],
        home_elo=prediction.get("home_elo", 1500.0),
        away_elo=prediction.get("away_elo", 1500.0),
        elo_diff=prediction.get("elo_diff", 0.0),
        model_used=model_type,
    )


async def _predict_elo(
    db: AsyncSession,
    home_id: int,
    away_id: int,
    season_id: int,
) -> dict:
    """Predicción usando ELO ratings almacenados."""
    from models.elo_model import EloSystem

    result = await db.execute(
        text("""
            SELECT ts.team_id, ts.elo_rating
            FROM team_stats ts
            WHERE ts.team_id IN (:h, :a) AND ts.season_id = :sid
        """),
        {"h": home_id, "a": away_id, "sid": season_id},
    )
    elo_rows = {r.team_id: r.elo_rating for r in result.fetchall()}

    elo = EloSystem()
    elo.set_rating(home_id, elo_rows.get(home_id, 1500.0))
    elo.set_rating(away_id, elo_rows.get(away_id, 1500.0))

    return elo.predict(home_id, away_id)


async def _predict_ml(
    db: AsyncSession,
    home_id: int,
    away_id: int,
    season_id: int,
    model_type: str,
) -> dict:
    """Predicción usando modelo ML entrenado."""
    import numpy as np
    from models.feature_engineering import (
        get_current_team_features, build_match_features,
    )

    # No podemos pasar async conn a funciones sync; usamos psycopg2 directamente
    import psycopg2
    sync_conn = psycopg2.connect(settings.database_url)

    try:
        home_feat = get_current_team_features(sync_conn, home_id, season_id)
        away_feat = get_current_team_features(sync_conn, away_id, season_id)
        features  = build_match_features(home_feat, away_feat)
    finally:
        sync_conn.close()

    _repo_root = Path(__file__).parent.parent.parent.parent
    model_path = _repo_root / "data" / "models" / f"{model_type}_model.pkl"
    if not model_path.exists():
        # Fallback a ELO si el modelo no está entrenado
        return await _predict_elo(db, home_id, away_id, season_id)

    if model_type == "logistic":
        from models.logistic_model import LogisticMatchPredictor
        model = LogisticMatchPredictor.load(str(model_path))
    else:
        from models.xgboost_model import XGBoostMatchPredictor
        model = XGBoostMatchPredictor.load(str(model_path))

    pred = model.predict_single(features)
    # Añadir ELO info para el frontend
    result = await db.execute(
        text("""
            SELECT ts.team_id, ts.elo_rating
            FROM team_stats ts
            WHERE ts.team_id IN (:h, :a) AND ts.season_id = :sid
        """),
        {"h": home_id, "a": away_id, "sid": season_id},
    )
    elos = {r.team_id: r.elo_rating for r in result.fetchall()}
    pred["home_elo"]  = elos.get(home_id, 1500.0)
    pred["away_elo"]  = elos.get(away_id, 1500.0)
    pred["elo_diff"]  = pred["home_elo"] - pred["away_elo"]
    return pred
