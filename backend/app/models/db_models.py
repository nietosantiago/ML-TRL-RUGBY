"""
SQLAlchemy 2.0 ORM models para TRL.
Mapean las tablas de data/schemas/init.sql.
"""

from datetime import date, time, datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean, Date, Float, ForeignKey, Integer,
    String, Text, Time, UniqueConstraint, ARRAY,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

from ..database import Base


class Team(Base):
    __tablename__ = "teams"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    name:         Mapped[str]           = mapped_column(String(100), unique=True, nullable=False)
    short_name:   Mapped[Optional[str]] = mapped_column(String(15))
    city:         Mapped[Optional[str]] = mapped_column(String(100))
    province:     Mapped[Optional[str]] = mapped_column(String(100))
    founded_year: Mapped[Optional[int]] = mapped_column(Integer)
    colors:       Mapped[Optional[str]] = mapped_column(String(100))
    created_at:   Mapped[datetime]      = mapped_column(TIMESTAMP(timezone=True))

    home_matches:  Mapped[List["Match"]] = relationship("Match", foreign_keys="Match.home_team_id", back_populates="home_team")
    away_matches:  Mapped[List["Match"]] = relationship("Match", foreign_keys="Match.away_team_id", back_populates="away_team")
    stats:         Mapped[List["TeamStat"]] = relationship("TeamStat", back_populates="team")
    elo_ratings:   Mapped[List["EloRating"]] = relationship("EloRating", foreign_keys="EloRating.team_id", back_populates="team")


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("year", "name"),)

    id:         Mapped[int]           = mapped_column(Integer, primary_key=True)
    year:       Mapped[int]           = mapped_column(Integer, nullable=False)
    name:       Mapped[str]           = mapped_column(String(100), nullable=False)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date:   Mapped[Optional[date]] = mapped_column(Date)
    is_current: Mapped[bool]          = mapped_column(Boolean, default=False)
    num_rounds: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime]      = mapped_column(TIMESTAMP(timezone=True))

    matches:    Mapped[List["Match"]]    = relationship("Match",    back_populates="season")
    standings:  Mapped[List["Standing"]] = relationship("Standing", back_populates="season")


class Match(Base):
    __tablename__ = "matches"

    id:                 Mapped[int]             = mapped_column(Integer, primary_key=True)
    season_id:          Mapped[int]             = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    round:              Mapped[int]             = mapped_column(Integer, nullable=False)
    match_date:         Mapped[Optional[date]]  = mapped_column(Date)
    match_time:         Mapped[Optional[time]]  = mapped_column(Time)
    home_team_id:       Mapped[int]             = mapped_column(ForeignKey("teams.id"))
    away_team_id:       Mapped[int]             = mapped_column(ForeignKey("teams.id"))
    home_score:         Mapped[Optional[int]]   = mapped_column(Integer)
    away_score:         Mapped[Optional[int]]   = mapped_column(Integer)
    home_tries:         Mapped[Optional[int]]   = mapped_column(Integer)
    away_tries:         Mapped[Optional[int]]   = mapped_column(Integer)
    home_conversions:   Mapped[Optional[int]]   = mapped_column(Integer)
    away_conversions:   Mapped[Optional[int]]   = mapped_column(Integer)
    home_penalties:     Mapped[Optional[int]]   = mapped_column(Integer)
    away_penalties:     Mapped[Optional[int]]   = mapped_column(Integer)
    home_bonus_try:     Mapped[bool]            = mapped_column(Boolean, default=False)
    away_bonus_try:     Mapped[bool]            = mapped_column(Boolean, default=False)
    home_bonus_losing:  Mapped[bool]            = mapped_column(Boolean, default=False)
    away_bonus_losing:  Mapped[bool]            = mapped_column(Boolean, default=False)
    is_played:          Mapped[bool]            = mapped_column(Boolean, default=False)
    venue:              Mapped[Optional[str]]   = mapped_column(String(200))
    notes:              Mapped[Optional[str]]   = mapped_column(Text)
    created_at:         Mapped[datetime]        = mapped_column(TIMESTAMP(timezone=True))
    updated_at:         Mapped[datetime]        = mapped_column(TIMESTAMP(timezone=True))

    season:    Mapped["Season"] = relationship("Season", back_populates="matches")
    home_team: Mapped["Team"]   = relationship("Team", foreign_keys=[home_team_id], back_populates="home_matches")
    away_team: Mapped["Team"]   = relationship("Team", foreign_keys=[away_team_id], back_populates="away_matches")


class Standing(Base):
    __tablename__ = "standings"
    __table_args__ = (UniqueConstraint("season_id", "team_id", "round"),)

    id:                   Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id:            Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    team_id:              Mapped[int] = mapped_column(ForeignKey("teams.id"))
    round:                Mapped[int] = mapped_column(Integer, nullable=False)
    played:               Mapped[int] = mapped_column(Integer, default=0)
    won:                  Mapped[int] = mapped_column(Integer, default=0)
    drawn:                Mapped[int] = mapped_column(Integer, default=0)
    lost:                 Mapped[int] = mapped_column(Integer, default=0)
    points_for:           Mapped[int] = mapped_column(Integer, default=0)
    points_against:       Mapped[int] = mapped_column(Integer, default=0)
    tries_for:            Mapped[int] = mapped_column(Integer, default=0)
    tries_against:        Mapped[int] = mapped_column(Integer, default=0)
    match_points:         Mapped[int] = mapped_column(Integer, default=0)
    bonus_try_points:     Mapped[int] = mapped_column(Integer, default=0)
    bonus_losing_points:  Mapped[int] = mapped_column(Integer, default=0)
    total_points:         Mapped[int] = mapped_column(Integer, default=0)
    position:             Mapped[Optional[int]] = mapped_column(Integer)
    created_at:           Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    season: Mapped["Season"] = relationship("Season", back_populates="standings")
    team:   Mapped["Team"]   = relationship("Team")


class TeamStat(Base):
    __tablename__ = "team_stats"
    __table_args__ = (UniqueConstraint("team_id", "season_id"),)

    id:                 Mapped[int]             = mapped_column(Integer, primary_key=True)
    team_id:            Mapped[int]             = mapped_column(ForeignKey("teams.id"))
    season_id:          Mapped[int]             = mapped_column(ForeignKey("seasons.id"))
    elo_rating:         Mapped[float]           = mapped_column(Float, default=1500.0)
    home_win_pct:       Mapped[Optional[float]] = mapped_column(Float)
    away_win_pct:       Mapped[Optional[float]] = mapped_column(Float)
    home_avg_scored:    Mapped[Optional[float]] = mapped_column(Float)
    away_avg_scored:    Mapped[Optional[float]] = mapped_column(Float)
    home_avg_conceded:  Mapped[Optional[float]] = mapped_column(Float)
    away_avg_conceded:  Mapped[Optional[float]] = mapped_column(Float)
    avg_points_scored:  Mapped[Optional[float]] = mapped_column(Float)
    avg_points_conceded:Mapped[Optional[float]] = mapped_column(Float)
    avg_tries_scored:   Mapped[Optional[float]] = mapped_column(Float)
    avg_tries_conceded: Mapped[Optional[float]] = mapped_column(Float)
    avg_point_diff:     Mapped[Optional[float]] = mapped_column(Float)
    form_last5:         Mapped[Optional[float]] = mapped_column(Float)
    form_pts_last5:     Mapped[Optional[float]] = mapped_column(Float)
    current_streak:     Mapped[Optional[int]]   = mapped_column(Integer)
    longest_win_streak: Mapped[Optional[int]]   = mapped_column(Integer)
    games_played:       Mapped[int]             = mapped_column(Integer, default=0)
    updated_at:         Mapped[datetime]        = mapped_column(TIMESTAMP(timezone=True))

    team:   Mapped["Team"]   = relationship("Team", back_populates="stats")


class EloRating(Base):
    __tablename__ = "elo_ratings"

    id:            Mapped[int]             = mapped_column(Integer, primary_key=True)
    team_id:       Mapped[int]             = mapped_column(ForeignKey("teams.id"))
    season_id:     Mapped[Optional[int]]   = mapped_column(ForeignKey("seasons.id"))
    round:         Mapped[Optional[int]]   = mapped_column(Integer)
    match_id:      Mapped[Optional[int]]   = mapped_column(ForeignKey("matches.id"))
    rating_before: Mapped[float]           = mapped_column(Float, nullable=False)
    rating_after:  Mapped[float]           = mapped_column(Float, nullable=False)
    opponent_id:   Mapped[Optional[int]]   = mapped_column(ForeignKey("teams.id"))
    result:        Mapped[Optional[str]]   = mapped_column(String(10))
    is_home:       Mapped[Optional[bool]]  = mapped_column(Boolean)
    score_diff:    Mapped[Optional[int]]   = mapped_column(Integer)
    created_at:    Mapped[datetime]        = mapped_column(TIMESTAMP(timezone=True))

    team: Mapped["Team"] = relationship("Team", foreign_keys=[team_id], back_populates="elo_ratings")
