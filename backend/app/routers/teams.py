"""Endpoints de equipos."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.db_models import Team, TeamStat
from ..models.schemas import TeamOut, TeamWithStats
from ..config import get_settings

router = APIRouter(prefix="/teams", tags=["teams"])
settings = get_settings()


@router.get("/", response_model=list[TeamOut])
async def list_teams(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).order_by(Team.name))
    return result.scalars().all()


@router.get("/{team_id}", response_model=TeamWithStats)
async def get_team(team_id: int, db: AsyncSession = Depends(get_db)):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    # Obtener stats de la temporada actual
    season_result = await db.execute(
        text("SELECT id FROM seasons WHERE is_current = TRUE LIMIT 1")
    )
    season_row = season_result.fetchone()
    season_id = season_row[0] if season_row else None

    elo       = 1500.0
    form      = 0.5
    streak    = 0
    gp        = 0
    avg_pd    = 0.0

    if season_id:
        stats_result = await db.execute(
            select(TeamStat).where(
                TeamStat.team_id == team_id,
                TeamStat.season_id == season_id,
            )
        )
        stats = stats_result.scalar_one_or_none()
        if stats:
            elo    = stats.elo_rating or 1500.0
            form   = stats.form_last5 or 0.5
            streak = stats.current_streak or 0
            gp     = stats.games_played or 0
            avg_pd = stats.avg_point_diff or 0.0

    return TeamWithStats(
        id=team.id,
        name=team.name,
        short_name=team.short_name,
        city=team.city,
        province=team.province,
        founded_year=team.founded_year,
        colors=team.colors,
        elo_rating=elo,
        form_last5=form,
        current_streak=streak,
        games_played=gp,
        avg_point_diff=avg_pd,
    )


@router.get("/{team_id}/elo-history")
async def get_team_elo_history(
    team_id: int,
    season_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    if not season_id:
        result = await db.execute(
            text("SELECT id FROM seasons WHERE is_current = TRUE LIMIT 1")
        )
        row = result.fetchone()
        season_id = row[0] if row else None

    query = text("""
        SELECT
            er.round,
            m.match_date,
            t2.name AS opponent_name,
            er.rating_before,
            er.rating_after,
            (er.rating_after - er.rating_before) AS rating_change,
            er.result,
            er.is_home
        FROM elo_ratings er
        LEFT JOIN matches m ON m.id = er.match_id
        LEFT JOIN teams t2 ON t2.id = er.opponent_id
        WHERE er.team_id = :team_id
          AND (:season_id IS NULL OR er.season_id = :season_id)
        ORDER BY er.created_at
    """)
    result = await db.execute(query, {"team_id": team_id, "season_id": season_id})
    rows = result.fetchall()

    history = [
        {
            "round":         r.round,
            "match_date":    r.match_date,
            "opponent_name": r.opponent_name,
            "rating_before": r.rating_before,
            "rating_after":  r.rating_after,
            "rating_change": r.rating_change,
            "result":        r.result,
            "is_home":       r.is_home,
        }
        for r in rows
    ]

    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    return {"team_id": team_id, "team_name": team.name, "history": history}
