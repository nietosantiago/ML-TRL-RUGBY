"""Pydantic v2 schemas para request/response de la API."""

from datetime import date, datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
#  Teams
# ---------------------------------------------------------------------------

class TeamBase(BaseModel):
    name:         str
    short_name:   Optional[str] = None
    city:         Optional[str] = None
    province:     Optional[str] = None
    founded_year: Optional[int] = None
    colors:       Optional[str] = None

class TeamOut(TeamBase):
    model_config = ConfigDict(from_attributes=True)
    id: int

class TeamWithStats(TeamOut):
    elo_rating:      float = 1500.0
    form_last5:      float = 0.5
    current_streak:  int   = 0
    games_played:    int   = 0
    avg_point_diff:  float = 0.0


# ---------------------------------------------------------------------------
#  Seasons
# ---------------------------------------------------------------------------

class SeasonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    year:       int
    name:       str
    start_date: Optional[date]
    end_date:   Optional[date]
    is_current: bool
    num_rounds: Optional[int]


# ---------------------------------------------------------------------------
#  Matches
# ---------------------------------------------------------------------------

class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                 int
    season_id:          int
    round:              int
    match_date:         Optional[date]
    home_team_id:       int
    away_team_id:       int
    home_team_name:     Optional[str] = None
    away_team_name:     Optional[str] = None
    home_score:         Optional[int]
    away_score:         Optional[int]
    home_tries:         Optional[int]
    away_tries:         Optional[int]
    home_bonus_try:     bool = False
    away_bonus_try:     bool = False
    home_bonus_losing:  bool = False
    away_bonus_losing:  bool = False
    is_played:          bool
    venue:              Optional[str]


# ---------------------------------------------------------------------------
#  Standings
# ---------------------------------------------------------------------------

class StandingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    team_id:              int
    team_name:            str
    team_short_name:      Optional[str] = None
    played:               int
    won:                  int
    drawn:                int
    lost:                 int
    points_for:           int
    points_against:       int
    point_diff:           int
    tries_for:            int
    tries_against:        int
    match_points:         int
    bonus_try_points:     int
    bonus_losing_points:  int
    total_points:         int
    position:             Optional[int]
    elo_rating:           Optional[float] = None


# ---------------------------------------------------------------------------
#  Prediction
# ---------------------------------------------------------------------------

class MatchPredictionRequest(BaseModel):
    home_team_id: int = Field(..., description="ID del equipo local")
    away_team_id: int = Field(..., description="ID del equipo visitante")
    season_id:    Optional[int] = None
    model:        str = Field("elo", description="'elo' | 'logistic' | 'xgboost'")

class MatchPredictionOut(BaseModel):
    home_team_id:   int
    away_team_id:   int
    home_team_name: Optional[str] = None
    away_team_name: Optional[str] = None
    home_win_prob:  float
    draw_prob:      float
    away_win_prob:  float
    home_elo:       float
    away_elo:       float
    elo_diff:       float
    model_used:     str


# ---------------------------------------------------------------------------
#  Season Simulation
# ---------------------------------------------------------------------------

class SimulationRequest(BaseModel):
    season_id:     Optional[int] = None
    n_iterations:  int = Field(1_000, ge=100, le=10_000)
    model:         str = Field("elo", description="Modelo para probabilidades")

class TeamSimResult(BaseModel):
    team_id:         int
    team_name:       str
    champion_prob:   float
    semifinal_prob:  float
    position_probs:  dict[str, float]
    points_mean:     float
    points_p5:       float
    points_p50:      float
    points_p95:      float

class SimulationOut(BaseModel):
    season_id:       int
    n_iterations:    int
    model_used:      str
    computed_at:     datetime
    teams:           list[TeamSimResult]


# ---------------------------------------------------------------------------
#  Custom Simulation (usuario fija resultados)
# ---------------------------------------------------------------------------

class FixedResult(BaseModel):
    match_id: int
    result:   str = Field(..., description="'home' | 'draw' | 'away'")

class CustomSimulationRequest(BaseModel):
    season_id:     Optional[int] = None
    n_iterations:  int = Field(1_000, ge=100, le=10_000)
    model:         str = "elo"
    fixed_results: list[FixedResult] = []

class CustomSimulationOut(SimulationOut):
    fixed_results_applied: int


# ---------------------------------------------------------------------------
#  ELO History
# ---------------------------------------------------------------------------

class EloHistoryPoint(BaseModel):
    round:          int
    match_date:     Optional[date]
    opponent_name:  Optional[str]
    rating_before:  float
    rating_after:   float
    rating_change:  float
    result:         Optional[str]
    is_home:        Optional[bool]

class TeamEloHistory(BaseModel):
    team_id:    int
    team_name:  str
    history:    list[EloHistoryPoint]


# ---------------------------------------------------------------------------
#  Misc
# ---------------------------------------------------------------------------

class HealthOut(BaseModel):
    status:  str
    version: str
    db:      str


# ---------------------------------------------------------------------------
#  Video Analysis (detección de situaciones de juego)
# ---------------------------------------------------------------------------

class MatchEventIn(BaseModel):
    event_type: str = Field(pattern="^(ruck|tackle|kick|carry)$")
    t_start:    float = Field(ge=0)
    t_end:      Optional[float] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)
    n_players:  Optional[int] = None
    x_norm:     Optional[float] = Field(None, ge=0, le=1)
    y_norm:     Optional[float] = Field(None, ge=0, le=1)
    meta:       Optional[dict[str, Any]] = None

class AnalysisImportIn(BaseModel):
    video_name:       str
    match_id:         Optional[int] = None
    duration_seconds: Optional[float] = None
    fps:              Optional[float] = None
    pipeline_version: Optional[str] = None
    params:           Optional[dict[str, Any]] = None
    events:           list[MatchEventIn] = Field(default_factory=list)

class MatchEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    event_type: str
    t_start:    float
    t_end:      Optional[float]
    confidence: Optional[float]
    n_players:  Optional[int]
    x_norm:     Optional[float]
    y_norm:     Optional[float]
    meta:       Optional[dict[str, Any]] = None

class AnalysisOut(BaseModel):
    id:               int
    video_name:       str
    match_id:         Optional[int]
    match_label:      Optional[str] = None    # "Local vs Visitante (fecha N)"
    duration_seconds: Optional[float]
    fps:              Optional[float]
    pipeline_version: Optional[str]
    analyzed_at:      Optional[datetime]
    n_events:         int = 0
    events_by_type:   dict[str, int] = Field(default_factory=dict)

class AnalysisDetailOut(AnalysisOut):
    events: list[MatchEventOut] = Field(default_factory=list)

class AnalysisImportOut(BaseModel):
    analysis_id: int
    n_events:    int

class TimelineBucket(BaseModel):
    t_start: float                   # inicio del bucket en segundos
    counts:  dict[str, int]          # eventos por tipo en el bucket

class AnalysisSummaryOut(BaseModel):
    analysis_id:      int
    video_name:       str
    duration_seconds: Optional[float]
    events_by_type:   dict[str, int]
    avg_confidence:   dict[str, float]
    ruck_total_seconds: float = 0.0
    bucket_seconds:   int = 300
    timeline:         list[TimelineBucket] = Field(default_factory=list)
