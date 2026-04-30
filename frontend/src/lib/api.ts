import axios from 'axios';
import type {
  Team, Season, Match, Standing,
  MatchPrediction, SimulationResult,
  TeamEloHistory, StandingsEvolution,
  ModelType, MatchResult,
} from './types';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const API  = `${BASE}/api/v1`;

const http = axios.create({
  baseURL: API,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

// ─── Teams ──────────────────────────────────���─────────────────────────────────
export const fetchTeams = (): Promise<Team[]> =>
  http.get('/teams/').then(r => r.data);

export const fetchTeam = (id: number): Promise<Team> =>
  http.get(`/teams/${id}`).then(r => r.data);

export const fetchTeamEloHistory = (
  teamId: number,
  seasonId?: number,
): Promise<TeamEloHistory> =>
  http.get(`/teams/${teamId}/elo-history`, {
    params: seasonId ? { season_id: seasonId } : {},
  }).then(r => r.data);

// ─── Seasons ──────────────────────────────────────────────────────────────────
export const fetchCurrentSeason = (): Promise<Season> =>
  http.get('/standings/').then(r => r.data);   // standings devuelve la season implícita

// ─── Matches ──────────────────────────────────────────────────────────────────
export const fetchMatches = (params?: {
  season_id?: number;
  round?: number;
  played?: boolean;
  team_id?: number;
}): Promise<Match[]> =>
  http.get('/matches/', { params }).then(r => r.data);

export const fetchMatch = (id: number): Promise<Match> =>
  http.get(`/matches/${id}`).then(r => r.data);

// ─── Standings ────────────────────────────────────────────────────────────────
export const fetchStandings = (params?: {
  season_id?: number;
  round?: number;
}): Promise<Standing[]> =>
  http.get('/standings/', { params }).then(r => r.data);

export const fetchStandingsEvolution = (params?: {
  season_id?: number;
  team_id?: number;
}): Promise<StandingsEvolution> =>
  http.get('/standings/evolution', { params }).then(r => r.data);

// ─── Prediction ───────────────────────────────────────────────────────────────
export const predictMatch = (
  homeTeamId: number,
  awayTeamId: number,
  model: ModelType = 'elo',
  seasonId?: number,
): Promise<MatchPrediction> =>
  http.post('/predict/match', {
    home_team_id: homeTeamId,
    away_team_id: awayTeamId,
    model,
    season_id: seasonId,
  }).then(r => r.data);

// ─── Simulation ───────────────────────────────────────────────────────────────
export const simulateSeason = (params: {
  season_id?: number;
  n_iterations?: number;
  model?: ModelType;
}): Promise<SimulationResult> =>
  http.post('/simulate/season', {
    season_id:    params.season_id,
    n_iterations: params.n_iterations ?? 10_000,
    model:        params.model ?? 'elo',
  }).then(r => r.data);

export const customSimulation = (params: {
  season_id?: number;
  n_iterations?: number;
  model?: ModelType;
  fixed_results: Array<{ match_id: number; result: MatchResult }>;
}): Promise<SimulationResult> =>
  http.post('/simulate/custom', {
    season_id:     params.season_id,
    n_iterations:  params.n_iterations ?? 10_000,
    model:         params.model ?? 'elo',
    fixed_results: params.fixed_results,
  }).then(r => r.data);

// ─── Health ───────────────────────────────────────────────────────────────────
export const fetchHealth = (): Promise<{ status: string; version: string; db: string }> =>
  http.get('/health', { baseURL: BASE }).then(r => r.data);
