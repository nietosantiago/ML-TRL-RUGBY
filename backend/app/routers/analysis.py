"""
Endpoints de análisis de video: importación y consulta de situaciones de
juego detectadas (rucks, tackles, kicks, carries).

Los eventos se generan localmente con scripts/analyze_video.py y se importan
acá; el backend no procesa video.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.db_models import Match, MatchEvent, VideoAnalysis
from ..models.schemas import (
    AnalysisDetailOut,
    AnalysisImportIn,
    AnalysisImportOut,
    AnalysisOut,
    AnalysisSummaryOut,
    MatchEventOut,
    TimelineBucket,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])

EVENT_TYPES = ("ruck", "tackle", "kick", "carry")


def _match_label(m: Optional[Match]) -> Optional[str]:
    if m is None:
        return None
    home = m.home_team.name if m.home_team else f"#{m.home_team_id}"
    away = m.away_team.name if m.away_team else f"#{m.away_team_id}"
    return f"{home} vs {away} (fecha {m.round})"


async def _counts_by_type(db: AsyncSession, analysis_ids: list[int]) -> dict[int, dict[str, int]]:
    if not analysis_ids:
        return {}
    result = await db.execute(
        select(MatchEvent.analysis_id, MatchEvent.event_type, func.count())
        .where(MatchEvent.analysis_id.in_(analysis_ids))
        .group_by(MatchEvent.analysis_id, MatchEvent.event_type)
    )
    counts: dict[int, dict[str, int]] = defaultdict(dict)
    for analysis_id, event_type, n in result.all():
        counts[analysis_id][event_type] = n
    return counts


@router.post("/import", response_model=AnalysisImportOut, status_code=201)
async def import_analysis(payload: AnalysisImportIn, db: AsyncSession = Depends(get_db)):
    """Importa el JSON de eventos producido por el pipeline de video."""
    if payload.match_id is not None:
        match = await db.get(Match, payload.match_id)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Partido {payload.match_id} no existe")

    analysis = VideoAnalysis(
        match_id=payload.match_id,
        video_name=payload.video_name,
        duration_seconds=payload.duration_seconds,
        fps=payload.fps,
        pipeline_version=payload.pipeline_version,
        params=payload.params,
        analyzed_at=datetime.now(timezone.utc),
    )
    db.add(analysis)
    await db.flush()

    for e in payload.events:
        db.add(MatchEvent(
            analysis_id=analysis.id,
            event_type=e.event_type,
            t_start=e.t_start,
            t_end=e.t_end,
            confidence=e.confidence,
            n_players=e.n_players,
            x_norm=e.x_norm,
            y_norm=e.y_norm,
            meta=e.meta,
        ))

    await db.flush()
    return AnalysisImportOut(analysis_id=analysis.id, n_events=len(payload.events))


@router.get("/", response_model=list[AnalysisOut])
async def list_analyses(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VideoAnalysis)
        .options(
            selectinload(VideoAnalysis.match).selectinload(Match.home_team),
            selectinload(VideoAnalysis.match).selectinload(Match.away_team),
        )
        .order_by(VideoAnalysis.analyzed_at.desc())
    )
    analyses = result.scalars().all()
    counts = await _counts_by_type(db, [a.id for a in analyses])

    return [
        AnalysisOut(
            id=a.id,
            video_name=a.video_name,
            match_id=a.match_id,
            match_label=_match_label(a.match),
            duration_seconds=a.duration_seconds,
            fps=a.fps,
            pipeline_version=a.pipeline_version,
            analyzed_at=a.analyzed_at,
            n_events=sum(counts.get(a.id, {}).values()),
            events_by_type=counts.get(a.id, {}),
        )
        for a in analyses
    ]


@router.get("/{analysis_id}", response_model=AnalysisDetailOut)
async def get_analysis(
    analysis_id: int,
    event_type: Optional[str] = Query(None, pattern="^(ruck|tackle|kick|carry)$"),
    min_confidence: Optional[float] = Query(None, ge=0, le=1),
    t_from: Optional[float] = Query(None, ge=0),
    t_to: Optional[float] = Query(None, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VideoAnalysis)
        .options(
            selectinload(VideoAnalysis.match).selectinload(Match.home_team),
            selectinload(VideoAnalysis.match).selectinload(Match.away_team),
        )
        .where(VideoAnalysis.id == analysis_id)
    )
    a = result.scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")

    stmt = select(MatchEvent).where(MatchEvent.analysis_id == analysis_id)
    if event_type is not None:
        stmt = stmt.where(MatchEvent.event_type == event_type)
    if min_confidence is not None:
        stmt = stmt.where(MatchEvent.confidence >= min_confidence)
    if t_from is not None:
        stmt = stmt.where(MatchEvent.t_start >= t_from)
    if t_to is not None:
        stmt = stmt.where(MatchEvent.t_start <= t_to)
    stmt = stmt.order_by(MatchEvent.t_start)

    events = (await db.execute(stmt)).scalars().all()
    counts = await _counts_by_type(db, [analysis_id])

    return AnalysisDetailOut(
        id=a.id,
        video_name=a.video_name,
        match_id=a.match_id,
        match_label=_match_label(a.match),
        duration_seconds=a.duration_seconds,
        fps=a.fps,
        pipeline_version=a.pipeline_version,
        analyzed_at=a.analyzed_at,
        n_events=sum(counts.get(analysis_id, {}).values()),
        events_by_type=counts.get(analysis_id, {}),
        events=[MatchEventOut.model_validate(e) for e in events],
    )


@router.get("/{analysis_id}/summary", response_model=AnalysisSummaryOut)
async def get_analysis_summary(
    analysis_id: int,
    bucket_seconds: int = Query(300, ge=30, le=1200),
    db: AsyncSession = Depends(get_db),
):
    """Resumen agregado: conteos por tipo, confianza media y timeline por bloques."""
    a = await db.get(VideoAnalysis, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")

    events = (await db.execute(
        select(MatchEvent)
        .where(MatchEvent.analysis_id == analysis_id)
        .order_by(MatchEvent.t_start)
    )).scalars().all()

    by_type: dict[str, int] = defaultdict(int)
    conf_sum: dict[str, float] = defaultdict(float)
    conf_n: dict[str, int] = defaultdict(int)
    ruck_seconds = 0.0
    buckets: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for e in events:
        by_type[e.event_type] += 1
        if e.confidence is not None:
            conf_sum[e.event_type] += e.confidence
            conf_n[e.event_type] += 1
        if e.event_type == "ruck" and e.t_end is not None:
            ruck_seconds += max(0.0, e.t_end - e.t_start)
        buckets[int(e.t_start // bucket_seconds)][e.event_type] += 1

    max_bucket = -1
    if a.duration_seconds:
        max_bucket = int(a.duration_seconds // bucket_seconds)
    if buckets:
        max_bucket = max(max_bucket, max(buckets.keys()))

    timeline = [
        TimelineBucket(t_start=k * bucket_seconds, counts=dict(buckets.get(k, {})))
        for k in range(0, max_bucket + 1)
    ]

    return AnalysisSummaryOut(
        analysis_id=analysis_id,
        video_name=a.video_name,
        duration_seconds=a.duration_seconds,
        events_by_type=dict(by_type),
        avg_confidence={
            k: round(conf_sum[k] / conf_n[k], 3) for k in conf_n if conf_n[k] > 0
        },
        ruck_total_seconds=round(ruck_seconds, 1),
        bucket_seconds=bucket_seconds,
        timeline=timeline,
    )


@router.delete("/{analysis_id}", status_code=204)
async def delete_analysis(analysis_id: int, db: AsyncSession = Depends(get_db)):
    a = await db.get(VideoAnalysis, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")
    await db.execute(delete(MatchEvent).where(MatchEvent.analysis_id == analysis_id))
    await db.delete(a)
