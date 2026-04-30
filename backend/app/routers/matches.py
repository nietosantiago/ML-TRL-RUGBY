"""Endpoints de partidos."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.db_models import Match, Season
from ..models.schemas import MatchOut
from ..config import get_settings

router = APIRouter(prefix="/matches", tags=["matches"])
settings = get_settings()


@router.get("/", response_model=list[MatchOut])
async def list_matches(
    season_id: Optional[int] = Query(None),
    round:     Optional[int] = Query(None),
    played:    Optional[bool] = Query(None),
    team_id:   Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Resolver season_id si no se pasa
    if season_id is None:
        result = await db.execute(
            text("SELECT id FROM seasons WHERE is_current = TRUE LIMIT 1")
        )
        row = result.fetchone()
        if row:
            season_id = row[0]

    stmt = select(Match).options(
        selectinload(Match.home_team),
        selectinload(Match.away_team),
    )

    if season_id is not None:
        stmt = stmt.where(Match.season_id == season_id)
    if round is not None:
        stmt = stmt.where(Match.round == round)
    if played is not None:
        stmt = stmt.where(Match.is_played == played)
    if team_id is not None:
        stmt = stmt.where(
            (Match.home_team_id == team_id) | (Match.away_team_id == team_id)
        )

    stmt = stmt.order_by(Match.round, Match.match_date)
    result = await db.execute(stmt)
    matches = result.scalars().all()

    return [
        MatchOut(
            id=m.id,
            season_id=m.season_id,
            round=m.round,
            match_date=m.match_date,
            home_team_id=m.home_team_id,
            away_team_id=m.away_team_id,
            home_team_name=m.home_team.name if m.home_team else None,
            away_team_name=m.away_team.name if m.away_team else None,
            home_score=m.home_score,
            away_score=m.away_score,
            home_tries=m.home_tries,
            away_tries=m.away_tries,
            home_bonus_try=m.home_bonus_try,
            away_bonus_try=m.away_bonus_try,
            home_bonus_losing=m.home_bonus_losing,
            away_bonus_losing=m.away_bonus_losing,
            is_played=m.is_played,
            venue=m.venue,
        )
        for m in matches
    ]


@router.get("/{match_id}", response_model=MatchOut)
async def get_match(match_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Match)
        .options(selectinload(Match.home_team), selectinload(Match.away_team))
        .where(Match.id == match_id)
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Partido no encontrado")

    return MatchOut(
        id=m.id,
        season_id=m.season_id,
        round=m.round,
        match_date=m.match_date,
        home_team_id=m.home_team_id,
        away_team_id=m.away_team_id,
        home_team_name=m.home_team.name if m.home_team else None,
        away_team_name=m.away_team.name if m.away_team else None,
        home_score=m.home_score,
        away_score=m.away_score,
        home_tries=m.home_tries,
        away_tries=m.away_tries,
        home_bonus_try=m.home_bonus_try,
        away_bonus_try=m.away_bonus_try,
        home_bonus_losing=m.home_bonus_losing,
        away_bonus_losing=m.away_bonus_losing,
        is_played=m.is_played,
        venue=m.venue,
    )
