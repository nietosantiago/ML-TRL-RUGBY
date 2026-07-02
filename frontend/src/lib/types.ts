// Tipos TypeScript que reflejan los schemas Pydantic del backend

export interface Team {
  id: number;
  name: string;
  short_name: string | null;
  city: string | null;
  province: string | null;
  elo_rating?: number;
  form_last5?: number;
  current_streak?: number;
  games_played?: number;
  avg_point_diff?: number;
}

export interface Season {
  id: number;
  year: number;
  name: string;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
  num_rounds: number | null;
}

export interface Match {
  id: number;
  season_id: number;
  round: number;
  match_date: string | null;
  home_team_id: number;
  away_team_id: number;
  home_team_name: string | null;
  away_team_name: string | null;
  home_score: number | null;
  away_score: number | null;
  home_tries: number | null;
  away_tries: number | null;
  home_bonus_try: boolean;
  away_bonus_try: boolean;
  home_bonus_losing: boolean;
  away_bonus_losing: boolean;
  is_played: boolean;
  venue: string | null;
}

export interface Standing {
  team_id: number;
  team_name: string;
  team_short_name: string | null;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  points_for: number;
  points_against: number;
  point_diff: number;
  tries_for: number;
  tries_against: number;
  match_points: number;
  bonus_try_points: number;
  bonus_losing_points: number;
  total_points: number;
  position: number | null;
  elo_rating: number | null;
}

export interface MatchPrediction {
  home_team_id: number;
  away_team_id: number;
  home_team_name: string | null;
  away_team_name: string | null;
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  home_elo: number;
  away_elo: number;
  elo_diff: number;
  model_used: string;
}

export interface PositionProbs {
  [key: string]: number;   // pos_1, pos_2, ...
}

export interface TeamSimResult {
  team_id: number;
  team_name: string;
  champion_prob: number;
  semifinal_prob: number;
  position_probs: PositionProbs;
  points_mean: number;
  points_p5: number;
  points_p50: number;
  points_p95: number;
}

export interface SimulationResult {
  season_id: number;
  n_iterations: number;
  model_used: string;
  computed_at: string;
  teams: TeamSimResult[];
  fixed_results_applied?: number;
}

export interface EloHistoryPoint {
  round: number;
  match_date: string | null;
  opponent_name: string | null;
  rating_before: number;
  rating_after: number;
  rating_change: number;
  result: string | null;
  is_home: boolean | null;
}

export interface TeamEloHistory {
  team_id: number;
  team_name: string;
  history: EloHistoryPoint[];
}

export interface StandingsEvolution {
  season_id: number;
  rounds: Record<string, Array<{
    team_id: number;
    team_name: string;
    short_name: string | null;
    position: number;
    points: number;
    point_diff: number;
  }>>;
}

export type ModelType = 'elo' | 'logistic' | 'xgboost';
export type MatchResult = 'home' | 'draw' | 'away';

// ─── Video Analysis (detección de situaciones de juego) ──────────────────────

export type EventType = 'ruck' | 'tackle' | 'kick' | 'carry';

export interface MatchEvent {
  id: number;
  event_type: EventType;
  t_start: number;
  t_end: number | null;
  confidence: number | null;
  n_players: number | null;
  x_norm: number | null;
  y_norm: number | null;
  meta: Record<string, unknown> | null;
}

export interface VideoAnalysis {
  id: number;
  video_name: string;
  match_id: number | null;
  match_label: string | null;
  duration_seconds: number | null;
  fps: number | null;
  pipeline_version: string | null;
  analyzed_at: string | null;
  n_events: number;
  events_by_type: Record<string, number>;
}

export interface VideoAnalysisDetail extends VideoAnalysis {
  events: MatchEvent[];
}

export interface TimelineBucket {
  t_start: number;
  counts: Record<string, number>;
}

export interface AnalysisSummary {
  analysis_id: number;
  video_name: string;
  duration_seconds: number | null;
  events_by_type: Record<string, number>;
  avg_confidence: Record<string, number>;
  ruck_total_seconds: number;
  bucket_seconds: number;
  timeline: TimelineBucket[];
}
