"""
Script de actualización automática de datos TRL.
Ejecuta el scraper, actualiza la DB y regenera los features de ML.

USO MANUAL:
  python scripts/update_data.py

CRON (actualizar cada día a las 23:00):
  0 23 * * * cd /path/to/trl && python scripts/update_data.py >> logs/cron.log 2>&1

SCHEDULER (APScheduler dentro del backend):
  Ver backend/app/scheduler.py
"""

import os
import sys
import logging
import subprocess
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/update.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("update_data")

SEASON_YEAR = int(os.getenv("CURRENT_SEASON", datetime.now().year))
SCRIPTS_DIR = Path(__file__).parent


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "trl_db"),
        user=os.getenv("DB_USER", "trl_user"),
        password=os.getenv("DB_PASSWORD", "trl_password"),
    )


def run_scraper() -> bool:
    """Ejecuta el scraper y guarda resultados en DB."""
    logger.info("=== Ejecutando scraper ===")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "scraper.py"),
         "--season", str(SEASON_YEAR),
         "--save-db",
         "--output", "data/raw"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        logger.info(f"Scraper exitoso:\n{result.stdout}")
        return True
    else:
        logger.error(f"Scraper falló:\n{result.stderr}")
        return False


def update_team_stats(season_year: int) -> None:
    """
    Recalcula team_stats para todos los equipos de la temporada.
    Incluye: ELO, forma, promedios, racha.
    """
    logger.info("Actualizando team_stats...")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM seasons WHERE year = %s", (season_year,))
            row = cur.fetchone()
            if not row:
                logger.warning(f"Temporada {season_year} no encontrada")
                return
            season_id = row[0]

            # Obtener todos los partidos jugados de la temporada, ordenados por fecha
            cur.execute("""
                SELECT m.id, m.match_date, m.round,
                       m.home_team_id, m.away_team_id,
                       m.home_score, m.away_score,
                       m.home_tries, m.away_tries
                FROM matches m
                WHERE m.season_id = %s AND m.is_played = TRUE
                ORDER BY m.match_date, m.round
            """, (season_id,))
            matches = cur.fetchall()

            cur.execute("SELECT id FROM teams")
            all_teams = [r[0] for r in cur.fetchall()]

            # Inicializar estadísticas
            stats: dict[int, dict] = {}
            for tid in all_teams:
                stats[tid] = {
                    "games": 0,
                    "home_games": 0, "home_wins": 0,
                    "away_games": 0, "away_wins": 0,
                    "total_scored": 0, "total_conceded": 0,
                    "home_scored": 0, "home_conceded": 0,
                    "away_scored": 0, "away_conceded": 0,
                    "total_tries_scored": 0, "total_tries_conceded": 0,
                    "results": [],      # lista de (1=win, 0.5=draw, 0=loss)
                    "point_diffs": [],  # diferencias de puntos
                    "streak": 0,
                    "max_win_streak": 0,
                    "cur_win_streak": 0,
                }

            for match in matches:
                (m_id, m_date, rnd,
                 h_id, a_id, hs, as_, ht, at) = match

                if hs is None or as_ is None:
                    continue

                for tid, pts_f, pts_a, tries_f, tries_a, is_home in [
                    (h_id, hs, as_, ht or 0, at or 0, True),
                    (a_id, as_, hs, at or 0, ht or 0, False),
                ]:
                    if tid not in stats:
                        continue
                    s = stats[tid]
                    s["games"] += 1
                    s["total_scored"] += pts_f
                    s["total_conceded"] += pts_a
                    s["total_tries_scored"] += tries_f
                    s["total_tries_conceded"] += tries_a
                    diff = pts_f - pts_a
                    s["point_diffs"].append(diff)

                    if is_home:
                        s["home_games"] += 1
                        s["home_scored"] += pts_f
                        s["home_conceded"] += pts_a
                        if pts_f > pts_a:
                            s["home_wins"] += 1
                    else:
                        s["away_games"] += 1
                        s["away_scored"] += pts_f
                        s["away_conceded"] += pts_a
                        if pts_f > pts_a:
                            s["away_wins"] += 1

                    if pts_f > pts_a:
                        s["results"].append(1.0)
                        s["cur_win_streak"] = max(0, s["cur_win_streak"]) + 1
                        s["streak"] = s["cur_win_streak"]
                    elif pts_f == pts_a:
                        s["results"].append(0.5)
                        s["cur_win_streak"] = 0
                        s["streak"] = 0
                    else:
                        s["results"].append(0.0)
                        s["cur_win_streak"] = min(0, s["cur_win_streak"]) - 1
                        s["streak"] = s["cur_win_streak"]

                    s["max_win_streak"] = max(s["max_win_streak"], s["cur_win_streak"])

            # Calcular forma últimos 5 (ponderada: más reciente = más peso)
            def weighted_form(results: list[float]) -> float:
                last5 = results[-5:]
                if not last5:
                    return 0.5
                weights = list(range(1, len(last5) + 1))
                return sum(r * w for r, w in zip(last5, weights)) / sum(weights)

            def weighted_pd(diffs: list[float]) -> float:
                last5 = diffs[-5:]
                if not last5:
                    return 0.0
                weights = list(range(1, len(last5) + 1))
                return sum(d * w for d, w in zip(last5, weights)) / sum(weights)

            # Obtener ELO actual de la tabla elo_ratings
            cur.execute("""
                SELECT DISTINCT ON (team_id) team_id, rating_after
                FROM elo_ratings
                WHERE season_id = %s
                ORDER BY team_id, created_at DESC
            """, (season_id,))
            elo_map = {row[0]: row[1] for row in cur.fetchall()}

            # Upsert team_stats
            for tid, s in stats.items():
                n = s["games"]
                if n == 0:
                    continue

                elo = elo_map.get(tid, 1500.0)
                form = weighted_form(s["results"])
                form_pd = weighted_pd(s["point_diffs"])

                cur.execute("""
                    INSERT INTO team_stats (
                        team_id, season_id,
                        elo_rating,
                        home_win_pct, away_win_pct,
                        home_avg_scored, away_avg_scored,
                        home_avg_conceded, away_avg_conceded,
                        avg_points_scored, avg_points_conceded,
                        avg_tries_scored, avg_tries_conceded,
                        avg_point_diff,
                        form_last5, form_pts_last5,
                        current_streak, longest_win_streak,
                        games_played
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (team_id, season_id) DO UPDATE SET
                        elo_rating = EXCLUDED.elo_rating,
                        home_win_pct = EXCLUDED.home_win_pct,
                        away_win_pct = EXCLUDED.away_win_pct,
                        home_avg_scored = EXCLUDED.home_avg_scored,
                        away_avg_scored = EXCLUDED.away_avg_scored,
                        home_avg_conceded = EXCLUDED.home_avg_conceded,
                        away_avg_conceded = EXCLUDED.away_avg_conceded,
                        avg_points_scored = EXCLUDED.avg_points_scored,
                        avg_points_conceded = EXCLUDED.avg_points_conceded,
                        avg_tries_scored = EXCLUDED.avg_tries_scored,
                        avg_tries_conceded = EXCLUDED.avg_tries_conceded,
                        avg_point_diff = EXCLUDED.avg_point_diff,
                        form_last5 = EXCLUDED.form_last5,
                        form_pts_last5 = EXCLUDED.form_pts_last5,
                        current_streak = EXCLUDED.current_streak,
                        longest_win_streak = EXCLUDED.longest_win_streak,
                        games_played = EXCLUDED.games_played,
                        updated_at = NOW()
                """, (
                    tid, season_id,
                    elo,
                    s["home_wins"] / max(s["home_games"], 1),
                    s["away_wins"] / max(s["away_games"], 1),
                    s["home_scored"] / max(s["home_games"], 1),
                    s["away_scored"] / max(s["away_games"], 1),
                    s["home_conceded"] / max(s["home_games"], 1),
                    s["away_conceded"] / max(s["away_games"], 1),
                    s["total_scored"] / n,
                    s["total_conceded"] / n,
                    s["total_tries_scored"] / n,
                    s["total_tries_conceded"] / n,
                    sum(s["point_diffs"]) / n,
                    form, form_pd,
                    s["streak"], s["max_win_streak"],
                    n,
                ))

        conn.commit()
        logger.info(f"team_stats actualizados para {len(stats)} equipos")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error actualizando team_stats: {e}")
        raise
    finally:
        conn.close()


def recompute_elo(season_year: int) -> None:
    """
    Llama al módulo ELO para recalcular ratings de todos los partidos jugados.
    """
    logger.info("Recalculando ELO ratings...")
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from models.elo_model import EloSystem

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM seasons WHERE year = %s", (season_year,))
            row = cur.fetchone()
            if not row:
                return
            season_id = row[0]

            # Limpiar ratings anteriores de esta temporada
            cur.execute("DELETE FROM elo_ratings WHERE season_id = %s", (season_id,))

            cur.execute("""
                SELECT DISTINCT ON (team_id) team_id,
                    COALESCE(
                        (SELECT rating_after FROM elo_ratings er2
                         WHERE er2.team_id = m.home_team_id
                         ORDER BY created_at DESC LIMIT 1),
                        1500.0
                    ) AS prev_elo
                FROM matches m WHERE m.season_id = %s
            """, (season_id,))

            cur.execute("""
                SELECT m.id, m.round, m.match_date,
                       m.home_team_id, m.away_team_id,
                       m.home_score, m.away_score
                FROM matches m
                WHERE m.season_id = %s AND m.is_played = TRUE
                ORDER BY m.match_date, m.round
            """, (season_id,))
            played_matches = cur.fetchall()

        elo = EloSystem()
        elo.load_ratings_from_db(conn, exclude_season=season_id)
        elo_records = elo.process_season(played_matches, season_id)

        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO elo_ratings
                    (team_id, season_id, round, match_id, rating_before,
                     rating_after, opponent_id, result, is_home, score_diff)
                VALUES %s
                ON CONFLICT DO NOTHING
            """, elo_records)

        conn.commit()
        logger.info(f"ELO: {len(elo_records)} registros procesados")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error recalculando ELO: {e}")
    finally:
        conn.close()


def main():
    logger.info(f"=== Update TRL {SEASON_YEAR} | {datetime.now().isoformat()} ===")
    os.makedirs("logs", exist_ok=True)

    scraper_ok = run_scraper()
    if not scraper_ok:
        logger.warning("Scraper falló, usando datos existentes en DB.")

    recompute_elo(SEASON_YEAR)
    update_team_stats(SEASON_YEAR)

    logger.info("=== Update completado ===")
    print(f"\n✓ Update completado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
