"""Endpoints de posiciones."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.schemas import StandingOut
from ..config import get_settings

router = APIRouter(prefix="/standings", tags=["standings"])
settings = get_settings()


@router.get("/", response_model=list[StandingOut])
async def get_standings(
    season_id: Optional[int] = Query(None, description="ID de temporada (default: actual)"),
    round:     Optional[int] = Query(None, description="Número de ronda (default: última)"),
    db: AsyncSession = Depends(get_db),
):
    if season_id is None:
        result = await db.execute(
            text("SELECT id FROM seasons WHERE is_current = TRUE LIMIT 1")
        )
        row = result.fetchone()
        season_id = row[0] if row else None

    # Si no se especifica ronda, usar la última disponible
    if round is None:
        result = await db.execute(
            text("SELECT MAX(round) FROM standings WHERE season_id = :sid"),
            {"sid": season_id},
        )
        row = result.fetchone()
        round = row[0] if row and row[0] is not None else 0

    query = text("""
        SELECT
            s.team_id,
            t.name AS team_name,
            t.short_name AS team_short_name,
            s.played,
            s.won,
            s.drawn,
            s.lost,
            s.points_for,
            s.points_against,
            (s.points_for - s.points_against) AS point_diff,
            s.tries_for,
            s.tries_against,
            s.match_points,
            s.bonus_try_points,
            s.bonus_losing_points,
            s.total_points,
            s.position,
            ts.elo_rating
        FROM standings s
        JOIN teams t ON t.id = s.team_id
        LEFT JOIN team_stats ts ON ts.team_id = s.team_id AND ts.season_id = s.season_id
        WHERE s.season_id = :sid AND s.round = :rnd
        ORDER BY s.position, s.total_points DESC, (s.points_for - s.points_against) DESC
    """)

    result = await db.execute(query, {"sid": season_id, "rnd": round})
    rows = result.fetchall()

    return [
        StandingOut(
            team_id=r.team_id,
            team_name=r.team_name,
            team_short_name=r.team_short_name,
            played=r.played,
            won=r.won,
            drawn=r.drawn,
            lost=r.lost,
            points_for=r.points_for,
            points_against=r.points_against,
            point_diff=r.point_diff,
            tries_for=r.tries_for,
            tries_against=r.tries_against,
            match_points=r.match_points,
            bonus_try_points=r.bonus_try_points,
            bonus_losing_points=r.bonus_losing_points,
            total_points=r.total_points,
            position=r.position,
            elo_rating=r.elo_rating,
        )
        for r in rows
    ]


@router.get("/evolution")
async def get_standings_evolution(
    season_id: Optional[int] = Query(None),
    team_id:   Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna la evolución de posiciones ronda a ronda.
    Útil para el gráfico de líneas en el frontend.
    """
    if season_id is None:
        result = await db.execute(
            text("SELECT id FROM seasons WHERE is_current = TRUE LIMIT 1")
        )
        row = result.fetchone()
        season_id = row[0] if row else None

    params = {"sid": season_id}
    team_filter = ""
    if team_id:
        team_filter = "AND s.team_id = :tid"
        params["tid"] = team_id

    query = text(f"""
        SELECT
            s.round,
            s.team_id,
            t.name AS team_name,
            t.short_name,
            s.position,
            s.total_points,
            (s.points_for - s.points_against) AS point_diff
        FROM standings s
        JOIN teams t ON t.id = s.team_id
        WHERE s.season_id = :sid {team_filter}
        ORDER BY s.round, s.position
    """)

    result = await db.execute(query, params)
    rows = result.fetchall()

    # Agrupar por ronda
    evolution: dict[int, list] = {}
    for r in rows:
        rnd = r.round
        if rnd not in evolution:
            evolution[rnd] = []
        evolution[rnd].append({
            "team_id":    r.team_id,
            "team_name":  r.team_name,
            "short_name": r.short_name,
            "position":   r.position,
            "points":     r.total_points,
            "point_diff": r.point_diff,
        })

    return {"season_id": season_id, "rounds": evolution}
