-- ============================================================
--  TRL - Torneo Regional del Litoral de Rugby
--  Database Schema - PostgreSQL
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
--  TEAMS
-- ============================================================
CREATE TABLE IF NOT EXISTS teams (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    short_name  VARCHAR(15),
    city        VARCHAR(100),
    province    VARCHAR(100),
    founded_year INTEGER,
    colors      VARCHAR(100),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
--  SEASONS
-- ============================================================
CREATE TABLE IF NOT EXISTS seasons (
    id          SERIAL PRIMARY KEY,
    year        INTEGER NOT NULL,
    name        VARCHAR(100) NOT NULL,
    start_date  DATE,
    end_date    DATE,
    is_current  BOOLEAN DEFAULT FALSE,
    num_rounds  INTEGER,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(year, name)
);

-- ============================================================
--  MATCHES
-- ============================================================
CREATE TABLE IF NOT EXISTS matches (
    id              SERIAL PRIMARY KEY,
    season_id       INTEGER NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    round           INTEGER NOT NULL,
    match_date      DATE,
    match_time      TIME,
    home_team_id    INTEGER NOT NULL REFERENCES teams(id),
    away_team_id    INTEGER NOT NULL REFERENCES teams(id),
    -- Scores (NULL = not played yet)
    home_score      INTEGER,
    away_score      INTEGER,
    home_tries      INTEGER,
    away_tries      INTEGER,
    home_conversions    INTEGER,
    away_conversions    INTEGER,
    home_penalties      INTEGER,
    away_penalties      INTEGER,
    -- Bonus points
    home_bonus_try      BOOLEAN DEFAULT FALSE,   -- scored 4+ tries
    away_bonus_try      BOOLEAN DEFAULT FALSE,
    home_bonus_losing   BOOLEAN DEFAULT FALSE,   -- lost by 7 or fewer
    away_bonus_losing   BOOLEAN DEFAULT FALSE,
    -- Status
    is_played       BOOLEAN DEFAULT FALSE,
    venue           VARCHAR(200),
    notes           TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT no_self_match CHECK (home_team_id <> away_team_id)
);

CREATE INDEX IF NOT EXISTS idx_matches_season ON matches(season_id);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team_id, away_team_id);
CREATE INDEX IF NOT EXISTS idx_matches_round ON matches(season_id, round);
CREATE INDEX IF NOT EXISTS idx_matches_played ON matches(is_played);

-- ============================================================
--  STANDINGS (snapshot por ronda)
-- ============================================================
CREATE TABLE IF NOT EXISTS standings (
    id              SERIAL PRIMARY KEY,
    season_id       INTEGER NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    team_id         INTEGER NOT NULL REFERENCES teams(id),
    round           INTEGER NOT NULL,            -- 0 = inicio de temporada
    -- Match record
    played          INTEGER DEFAULT 0,
    won             INTEGER DEFAULT 0,
    drawn           INTEGER DEFAULT 0,
    lost            INTEGER DEFAULT 0,
    -- Scoring
    points_for      INTEGER DEFAULT 0,
    points_against  INTEGER DEFAULT 0,
    tries_for       INTEGER DEFAULT 0,
    tries_against   INTEGER DEFAULT 0,
    -- Points breakdown
    match_points        INTEGER DEFAULT 0,       -- 4=victoria, 2=empate, 0=derrota
    bonus_try_points    INTEGER DEFAULT 0,       -- +1 por 4 tries
    bonus_losing_points INTEGER DEFAULT 0,       -- +1 por perder por <= 7
    total_points        INTEGER DEFAULT 0,       -- columna calculada
    -- Position
    position        INTEGER,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(season_id, team_id, round)
);

CREATE INDEX IF NOT EXISTS idx_standings_season_round ON standings(season_id, round);

-- ============================================================
--  ELO RATINGS (historial completo)
-- ============================================================
CREATE TABLE IF NOT EXISTS elo_ratings (
    id              SERIAL PRIMARY KEY,
    team_id         INTEGER NOT NULL REFERENCES teams(id),
    season_id       INTEGER REFERENCES seasons(id),
    round           INTEGER,
    match_id        INTEGER REFERENCES matches(id),
    rating_before   FLOAT NOT NULL,
    rating_after    FLOAT NOT NULL,
    rating_change   FLOAT GENERATED ALWAYS AS (rating_after - rating_before) STORED,
    opponent_id     INTEGER REFERENCES teams(id),
    result          VARCHAR(10),    -- 'win', 'draw', 'loss'
    is_home         BOOLEAN,
    score_diff      INTEGER,        -- positive = equipo ganó
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_elo_team ON elo_ratings(team_id, created_at);

-- ============================================================
--  TEAM STATS (features para ML, actualizados continuamente)
-- ============================================================
CREATE TABLE IF NOT EXISTS team_stats (
    id                  SERIAL PRIMARY KEY,
    team_id             INTEGER NOT NULL REFERENCES teams(id),
    season_id           INTEGER NOT NULL REFERENCES seasons(id),
    -- Current ELO
    elo_rating          FLOAT DEFAULT 1500.0,
    -- Performance splits
    home_win_pct        FLOAT DEFAULT 0.0,
    away_win_pct        FLOAT DEFAULT 0.0,
    home_avg_scored     FLOAT DEFAULT 0.0,
    away_avg_scored     FLOAT DEFAULT 0.0,
    home_avg_conceded   FLOAT DEFAULT 0.0,
    away_avg_conceded   FLOAT DEFAULT 0.0,
    -- Aggregates (all games in season)
    avg_points_scored   FLOAT DEFAULT 0.0,
    avg_points_conceded FLOAT DEFAULT 0.0,
    avg_tries_scored    FLOAT DEFAULT 0.0,
    avg_tries_conceded  FLOAT DEFAULT 0.0,
    avg_point_diff      FLOAT DEFAULT 0.0,
    -- Recent form (last 5 games, weighted 1.0 for most recent)
    form_last5          FLOAT DEFAULT 0.0,      -- 0.0 = all losses, 1.0 = all wins
    form_pts_last5      FLOAT DEFAULT 0.0,      -- avg points diff last 5
    -- Streak
    current_streak      INTEGER DEFAULT 0,      -- positive=wins, negative=losses
    longest_win_streak  INTEGER DEFAULT 0,
    -- Season totals
    games_played        INTEGER DEFAULT 0,
    -- Metadata
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(team_id, season_id)
);

-- ============================================================
--  HEAD TO HEAD
-- ============================================================
CREATE TABLE IF NOT EXISTS head_to_head (
    id              SERIAL PRIMARY KEY,
    team_a_id       INTEGER NOT NULL REFERENCES teams(id),
    team_b_id       INTEGER NOT NULL REFERENCES teams(id),
    total_matches   INTEGER DEFAULT 0,
    team_a_wins     INTEGER DEFAULT 0,
    team_b_wins     INTEGER DEFAULT 0,
    draws           INTEGER DEFAULT 0,
    team_a_points   INTEGER DEFAULT 0,
    team_b_points   INTEGER DEFAULT 0,
    last_match_id   INTEGER REFERENCES matches(id),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(team_a_id, team_b_id),
    CONSTRAINT ordered_teams CHECK (team_a_id < team_b_id)
);

-- ============================================================
--  MODEL METADATA (tracking de modelos entrenados)
-- ============================================================
CREATE TABLE IF NOT EXISTS model_runs (
    id              SERIAL PRIMARY KEY,
    model_type      VARCHAR(50) NOT NULL,   -- 'elo', 'logistic', 'xgboost'
    season_ids      INTEGER[],              -- temporadas usadas para entrenar
    log_loss        FLOAT,
    accuracy        FLOAT,
    brier_score     FLOAT,
    params          JSONB,
    model_path      VARCHAR(500),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
--  SIMULATION RESULTS (cache de simulaciones Monte Carlo)
-- ============================================================
CREATE TABLE IF NOT EXISTS simulation_results (
    id              SERIAL PRIMARY KEY,
    season_id       INTEGER NOT NULL REFERENCES seasons(id),
    simulation_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    num_iterations  INTEGER NOT NULL,
    model_used      VARCHAR(50),
    -- Serialized results as JSON
    position_probs  JSONB,   -- {team_id: {pos_1: 0.35, pos_2: 0.28, ...}}
    champion_probs  JSONB,   -- {team_id: 0.35}
    semifinal_probs JSONB,   -- {team_id: 0.65}
    points_dist     JSONB,   -- {team_id: {mean: 45, p5: 38, p95: 52, ...}}
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
--  TRIGGERS: updated_at automático
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER matches_updated_at
    BEFORE UPDATE ON matches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER team_stats_updated_at
    BEFORE UPDATE ON team_stats
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER head_to_head_updated_at
    BEFORE UPDATE ON head_to_head
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
--  VIEW: Tabla de posiciones actual (última ronda)
-- ============================================================
CREATE OR REPLACE VIEW current_standings AS
SELECT
    s.season_id,
    s.team_id,
    t.name AS team_name,
    t.short_name,
    s.round,
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
    s.position
FROM standings s
JOIN teams t ON t.id = s.team_id
JOIN (
    SELECT season_id, MAX(round) AS max_round
    FROM standings
    GROUP BY season_id
) latest ON latest.season_id = s.season_id AND latest.max_round = s.round;

-- ============================================================
--  VIEW: Matches con nombres de equipos
-- ============================================================
CREATE OR REPLACE VIEW matches_detail AS
SELECT
    m.*,
    ht.name AS home_team_name,
    ht.short_name AS home_team_short,
    at.name AS away_team_name,
    at.short_name AS away_team_short,
    se.year AS season_year,
    se.name AS season_name
FROM matches m
JOIN teams ht ON ht.id = m.home_team_id
JOIN teams at ON at.id = m.away_team_id
JOIN seasons se ON se.id = m.season_id;

-- ============================================================
--  VIDEO ANALYSIS: detección de situaciones de juego
-- ============================================================
CREATE TABLE IF NOT EXISTS video_analyses (
    id              SERIAL PRIMARY KEY,
    match_id        INTEGER REFERENCES matches(id) ON DELETE SET NULL,
    video_name      VARCHAR(255) NOT NULL,
    duration_seconds FLOAT,
    fps             FLOAT,
    pipeline_version VARCHAR(20),
    params          JSONB,
    analyzed_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS match_events (
    id          SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES video_analyses(id) ON DELETE CASCADE,
    event_type  VARCHAR(20) NOT NULL,   -- ruck | tackle | kick | carry
    t_start     FLOAT NOT NULL,         -- segundos desde el inicio del video
    t_end       FLOAT,
    confidence  FLOAT,
    n_players   INTEGER,
    x_norm      FLOAT,                  -- posición normalizada [0,1] en el frame
    y_norm      FLOAT,
    meta        JSONB,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_match_events_analysis
    ON match_events(analysis_id, event_type);
