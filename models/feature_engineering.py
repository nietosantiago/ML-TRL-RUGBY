"""
Feature engineering para modelos predictivos TRL.

Construye el feature vector para cada partido a partir de:
- ELO ratings
- Estadísticas de localía/visitante
- Forma reciente (últimos N partidos)
- Head-to-head histórico
- Momentum (racha actual)

El módulo es stateless: todos los datos se pasan explícitamente.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


FEATURE_NAMES = [
    "elo_diff",             # ELO local - ELO visitante (con ventaja de localía aplicada)
    "elo_home",             # ELO absoluto del local
    "elo_away",             # ELO absoluto del visitante
    "form_home",            # Forma ponderada local (0-1)
    "form_away",            # Forma ponderada visitante (0-1)
    "form_diff",            # form_home - form_away
    "avg_pd_home",          # Diferencia de puntos promedio últimos 5 (local)
    "avg_pd_away",          # Diferencia de puntos promedio últimos 5 (visitante)
    "pd_diff",              # avg_pd_home - avg_pd_away
    "home_win_pct",         # % victorias jugando de local (histórico temporada)
    "away_win_pct",         # % victorias jugando de visitante (histórico temporada)
    "home_avg_scored",      # Puntos promedio anotados jugando de local
    "away_avg_scored",      # Puntos promedio anotados jugando de visitante
    "home_avg_conceded",    # Puntos promedio concedidos jugando de local
    "away_avg_conceded",    # Puntos promedio concedidos jugando de visitante
    "streak_home",          # Racha actual del local (+ve=victorias, -ve=derrotas)
    "streak_away",          # Racha actual del visitante
    "streak_diff",          # streak_home - streak_away
    "h2h_home_win_rate",    # Head-to-head: tasa de victoria del local histórica
    "h2h_total_matches",    # Head-to-head: total de partidos
    "games_played_home",    # Partidos jugados en la temporada (local)
    "games_played_away",    # Partidos jugados en la temporada (visitante)
]

HOME_ADVANTAGE_ELO = 60.0   # mismo valor que EloConfig.home_advantage


@dataclass
class TeamFeatures:
    """Features de un equipo en un momento dado."""
    team_id:            int
    elo_rating:         float = 1500.0
    form_last5:         float = 0.5
    form_pts_last5:     float = 0.0
    home_win_pct:       float = 0.5
    away_win_pct:       float = 0.5
    home_avg_scored:    float = 0.0
    away_avg_scored:    float = 0.0
    home_avg_conceded:  float = 0.0
    away_avg_conceded:  float = 0.0
    current_streak:     int   = 0
    games_played:       int   = 0


def build_match_features(
    home: TeamFeatures,
    away: TeamFeatures,
    h2h_home_wins: int = 0,
    h2h_total: int = 0,
) -> np.ndarray:
    """
    Construye el vector de features para un partido dado.
    El orden debe coincidir con FEATURE_NAMES.

    Returns:
        np.ndarray de shape (len(FEATURE_NAMES),)
    """
    elo_diff = (home.elo_rating + HOME_ADVANTAGE_ELO) - away.elo_rating
    form_diff = home.form_last5 - away.form_last5
    pd_diff   = home.form_pts_last5 - away.form_pts_last5
    streak_diff = home.current_streak - away.current_streak
    h2h_win_rate = h2h_home_wins / max(h2h_total, 1)

    features = np.array([
        elo_diff,
        home.elo_rating,
        away.elo_rating,
        home.form_last5,
        away.form_last5,
        form_diff,
        home.form_pts_last5,
        away.form_pts_last5,
        pd_diff,
        home.home_win_pct,
        away.away_win_pct,
        home.home_avg_scored,
        away.away_avg_scored,
        home.home_avg_conceded,
        away.away_avg_conceded,
        float(home.current_streak),
        float(away.current_streak),
        float(streak_diff),
        h2h_win_rate,
        float(h2h_total),
        float(home.games_played),
        float(away.games_played),
    ], dtype=np.float32)

    assert len(features) == len(FEATURE_NAMES), (
        f"Feature count mismatch: {len(features)} vs {len(FEATURE_NAMES)}"
    )
    return features


def build_dataset_from_db(conn, season_ids: list[int]) -> pd.DataFrame:
    """
    Construye el dataset completo de entrenamiento desde la DB.
    Cada fila es un partido con sus features calculadas EN EL MOMENTO
    del partido (para evitar data leakage).

    Returns:
        DataFrame con columnas = FEATURE_NAMES + ['target', 'match_id', 'season_id']
        target: 1 = local gana, 0 = visitante gana, 0.5 = empate
    """
    with conn.cursor() as cur:
        placeholders = ", ".join(["%s"] * len(season_ids))
        cur.execute(f"""
            SELECT
                m.id AS match_id,
                m.season_id,
                m.round,
                m.match_date,
                m.home_team_id,
                m.away_team_id,
                m.home_score,
                m.away_score
            FROM matches m
            WHERE m.season_id IN ({placeholders})
              AND m.is_played = TRUE
            ORDER BY m.season_id, m.match_date, m.round
        """, season_ids)
        matches = cur.fetchall()

        # ELO snapshots (rating_before de cada partido)
        cur.execute(f"""
            SELECT er.match_id, er.team_id, er.rating_before, er.is_home
            FROM elo_ratings er
            JOIN matches m ON m.id = er.match_id
            WHERE m.season_id IN ({placeholders})
        """, season_ids)
        elo_rows = cur.fetchall()

        # team_stats por temporada (promedios a final de temporada como aproximación)
        cur.execute(f"""
            SELECT ts.team_id, ts.season_id,
                   ts.form_last5, ts.form_pts_last5,
                   ts.home_win_pct, ts.away_win_pct,
                   ts.home_avg_scored, ts.away_avg_scored,
                   ts.home_avg_conceded, ts.away_avg_conceded,
                   ts.current_streak, ts.games_played
            FROM team_stats ts
            WHERE ts.season_id IN ({placeholders})
        """, season_ids)
        stats_rows = cur.fetchall()

        # H2H
        cur.execute("""
            SELECT h.team_a_id, h.team_b_id,
                   h.team_a_wins, h.total_matches
            FROM head_to_head h
        """)
        h2h_rows = cur.fetchall()

    # --- Indexar datos ---
    elo_map: dict[tuple, float] = {}     # (match_id, team_id) -> rating_before
    for m_id, t_id, rating, _ in elo_rows:
        elo_map[(m_id, t_id)] = rating

    stats_map: dict[tuple, dict] = {}   # (team_id, season_id) -> stats dict
    for row in stats_rows:
        (tid, sid, form, form_pd, hwp, awp, has_, aas_, hac, aac, streak, gp) = row
        stats_map[(tid, sid)] = {
            "form_last5": form or 0.5,
            "form_pts_last5": form_pd or 0.0,
            "home_win_pct": hwp or 0.5,
            "away_win_pct": awp or 0.5,
            "home_avg_scored": has_ or 0.0,
            "away_avg_scored": aas_ or 0.0,
            "home_avg_conceded": hac or 0.0,
            "away_avg_conceded": aac or 0.0,
            "current_streak": streak or 0,
            "games_played": gp or 0,
        }

    h2h_map: dict[tuple, tuple] = {}    # (min_id, max_id) -> (a_wins, total)
    for a_id, b_id, a_wins, total in h2h_rows:
        h2h_map[(a_id, b_id)] = (a_wins, total)

    # --- Construir filas del dataset ---
    rows = []
    for match in matches:
        (m_id, s_id, rnd, m_date, h_id, a_id, hs, as_) = match

        if hs is None or as_ is None:
            continue

        h_elo = elo_map.get((m_id, h_id), 1500.0)
        a_elo = elo_map.get((m_id, a_id), 1500.0)

        h_stats = stats_map.get((h_id, s_id), {})
        a_stats = stats_map.get((a_id, s_id), {})

        def default_stat(stats, key, default):
            return stats.get(key, default)

        home_feat = TeamFeatures(
            team_id=h_id,
            elo_rating=h_elo,
            form_last5=default_stat(h_stats, "form_last5", 0.5),
            form_pts_last5=default_stat(h_stats, "form_pts_last5", 0.0),
            home_win_pct=default_stat(h_stats, "home_win_pct", 0.5),
            away_win_pct=default_stat(h_stats, "away_win_pct", 0.5),
            home_avg_scored=default_stat(h_stats, "home_avg_scored", 0.0),
            away_avg_scored=default_stat(h_stats, "away_avg_scored", 0.0),
            home_avg_conceded=default_stat(h_stats, "home_avg_conceded", 0.0),
            away_avg_conceded=default_stat(h_stats, "away_avg_conceded", 0.0),
            current_streak=default_stat(h_stats, "current_streak", 0),
            games_played=default_stat(h_stats, "games_played", 0),
        )

        away_feat = TeamFeatures(
            team_id=a_id,
            elo_rating=a_elo,
            form_last5=default_stat(a_stats, "form_last5", 0.5),
            form_pts_last5=default_stat(a_stats, "form_pts_last5", 0.0),
            home_win_pct=default_stat(a_stats, "home_win_pct", 0.5),
            away_win_pct=default_stat(a_stats, "away_win_pct", 0.5),
            home_avg_scored=default_stat(a_stats, "home_avg_scored", 0.0),
            away_avg_scored=default_stat(a_stats, "away_avg_scored", 0.0),
            home_avg_conceded=default_stat(a_stats, "home_avg_conceded", 0.0),
            away_avg_conceded=default_stat(a_stats, "away_avg_conceded", 0.0),
            current_streak=default_stat(a_stats, "current_streak", 0),
            games_played=default_stat(a_stats, "games_played", 0),
        )

        # H2H: normalizar para que siempre team_a_id < team_b_id
        h2h_key = (min(h_id, a_id), max(h_id, a_id))
        h2h = h2h_map.get(h2h_key, (0, 0))
        # Si home_id > away_id, las victorias de a_id son del visitante
        if h_id > a_id:
            h2h_home_wins = h2h[1] - h2h[0]   # total - a_wins = b_wins = home_wins
        else:
            h2h_home_wins = h2h[0]

        feat = build_match_features(
            home_feat, away_feat, h2h_home_wins, h2h[1]
        )

        if hs > as_:
            target = 1.0
        elif hs < as_:
            target = 0.0
        else:
            target = 0.5

        row = dict(zip(FEATURE_NAMES, feat.tolist()))
        row["target"] = target
        row["match_id"] = m_id
        row["season_id"] = s_id
        row["home_score"] = hs
        row["away_score"] = as_
        rows.append(row)

    df = pd.DataFrame(rows)
    return df


def get_current_team_features(conn, team_id: int, season_id: int) -> TeamFeatures:
    """
    Obtiene los features actuales de un equipo para predicción.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ts.form_last5, ts.form_pts_last5,
                   ts.home_win_pct, ts.away_win_pct,
                   ts.home_avg_scored, ts.away_avg_scored,
                   ts.home_avg_conceded, ts.away_avg_conceded,
                   ts.current_streak, ts.games_played, ts.elo_rating
            FROM team_stats ts
            WHERE ts.team_id = %s AND ts.season_id = %s
        """, (team_id, season_id))
        row = cur.fetchone()

    if row is None:
        return TeamFeatures(team_id=team_id)

    return TeamFeatures(
        team_id=team_id,
        elo_rating=row[10] or 1500.0,
        form_last5=row[0] or 0.5,
        form_pts_last5=row[1] or 0.0,
        home_win_pct=row[2] or 0.5,
        away_win_pct=row[3] or 0.5,
        home_avg_scored=row[4] or 0.0,
        away_avg_scored=row[5] or 0.0,
        home_avg_conceded=row[6] or 0.0,
        away_avg_conceded=row[7] or 0.0,
        current_streak=row[8] or 0,
        games_played=row[9] or 0,
    )
