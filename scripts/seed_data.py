"""
Carga todos los datos históricos reales del TRL desde data/raw/trl_all_seasons.json.

USO:
  python scripts/seed_data.py             # carga datos + calcula ELO
  python scripts/seed_data.py --skip-elo  # solo datos, sin recalcular ELO
"""

import os, sys, json, logging, argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("seed_data")

RAW_JSON      = Path("data/raw/trl_all_seasons.json")
CURRENT_SEASON = "2026"

# Orden relativo de las fases dentro de una temporada (para asignar número de fecha)
PHASE_ORDER = {
    "Regular season":             0,
    "First phase":                0,
    "Zona Campeonato":            1,
    "Zona Reclasificacion":       1,
    "Reclasificacion A/B":        1,
    "Reclasificacion A":          1,
    "Reclasificatorio Regional A":1,
    "CuadrangularFinal":          2,
    "Playout":                    2,
    "Promocion A semifinals":     2,
    "Promocion A final":          2,
    "5th place semifinals":       3,
    "11th place semifinals":      3,
    "15th place semifinals":      3,
    "5th place final":            3,
    "7th place final":            3,
    "9th place final":            3,
    "11th place final":           3,
    "13th place final":           3,
    "15th place final":           3,
    "17th place final":           3,
    "Semifinals":                 4,
    "3rd place final":            5,
    "Final":                      6,
}

REGULAR_PHASES = {"Regular season", "First phase"}


def _parse_date(s: str):
    """DD/MM/YYYY → datetime. Retorna None si inválido."""
    try:
        d, m, y = s.split("/")
        return datetime(int(y), int(m), int(d))
    except Exception:
        return None


def get_conn():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "trl_db"),
        user=os.getenv("DB_USER", "trl_user"),
        password=os.getenv("DB_PASSWORD", "trl_password"),
    )


# ── Paso 1: Teams ─────────────────────────────────────────────────────────────

def seed_teams(cur, matches: list[dict]) -> dict[int, str]:
    """Inserta todos los equipos usando los IDs reales de la API."""
    teams: dict[int, str] = {}
    for m in matches:
        teams[m["home_team_id"]] = m["home_team"]
        teams[m["away_team_id"]] = m["away_team"]

    rows = [(tid, name) for tid, name in teams.items()]
    execute_values(cur, """
        INSERT INTO teams (id, name)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
    """, rows)

    logger.info(f"  {len(teams)} equipos insertados/actualizados")
    return teams


# ── Paso 2: Seasons ───────────────────────────────────────────────────────────

def seed_seasons(cur, season_meta: dict) -> dict[int, int]:
    """Inserta las temporadas. Retorna {year: season_id}."""
    season_id_map: dict[int, int] = {}
    for year_str, meta in season_meta.items():
        year = int(year_str)
        is_cur = (year_str == CURRENT_SEASON)
        cur.execute("""
            INSERT INTO seasons (year, name, is_current)
            VALUES (%s, %s, %s)
            ON CONFLICT (year, name) DO UPDATE SET is_current = EXCLUDED.is_current
            RETURNING id
        """, (year, f"TRL {year}", is_cur))
        season_id_map[year] = cur.fetchone()[0]

    # Asegurar que sólo CURRENT_SEASON tenga is_current = TRUE
    cur.execute("UPDATE seasons SET is_current = FALSE WHERE year != %s", (int(CURRENT_SEASON),))
    logger.info(f"  {len(season_id_map)} temporadas insertadas/actualizadas")
    return season_id_map


# ── Paso 3: Round numbering ───────────────────────────────────────────────────

def assign_round_numbers(matches: list[dict]) -> dict[tuple, int]:
    """
    Asigna números de fecha enteros a los partidos de una temporada.
    Agrupa por (phase_order, date) y asigna 1, 2, 3, ...
    Retorna {(round_name, date_str): round_number}.
    """
    groups: set[tuple] = set()
    for m in matches:
        ph = PHASE_ORDER.get(m["round_name"], 0)
        groups.add((ph, m["date"], m["round_name"]))

    # Ordenar cronológicamente dentro de cada fase
    def sort_key(g):
        ph, date_str, _ = g
        dt = _parse_date(date_str)
        return (ph, dt or datetime(9999, 1, 1))

    sorted_groups = sorted(groups, key=sort_key)

    # Agrupar fechas cercanas (mismo día) como la misma fecha/round
    # (simplificación: mismo (phase, date) exacto = misma fecha)
    result: dict[tuple, int] = {}
    round_num = 0
    last_key = None
    for ph, date_str, rname in sorted_groups:
        key = (ph, date_str)
        if key != last_key:
            round_num += 1
            last_key = key
        result[(rname, date_str)] = round_num

    return result


# ── Paso 4: Matches ───────────────────────────────────────────────────────────

def seed_matches(cur, matches: list[dict], season_id_map: dict[int, int]) -> int:
    """Inserta todos los partidos. Retorna cantidad insertada."""
    by_season: dict[int, list[dict]] = defaultdict(list)
    for m in matches:
        by_season[m["season"]].append(m)

    total = 0
    for year, season_matches in sorted(by_season.items()):
        sid = season_id_map.get(year)
        if not sid:
            continue

        # Para la temporada activa: borrar todos los existentes y re-insertar
        # (garantiza que partidos jugados reemplacen a los pendientes)
        if str(year) == CURRENT_SEASON:
            cur.execute("DELETE FROM matches WHERE season_id = %s", (sid,))
            logger.info(f"  {year}: matches existentes eliminados para re-seedear")

        round_map = assign_round_numbers(season_matches)
        rows = []
        for m in season_matches:
            rnum = round_map.get((m["round_name"], m["date"]), 1)
            date_val = None
            if m.get("date"):
                dt = _parse_date(m["date"])
                date_val = dt.date() if dt else None

            rows.append((
                sid, rnum, date_val,
                m["home_team_id"], m["away_team_id"],
                m["home_score"], m["away_score"],
                True,
            ))

        execute_values(cur, """
            INSERT INTO matches
                (season_id, round, match_date, home_team_id, away_team_id,
                 home_score, away_score, is_played)
            VALUES %s
            ON CONFLICT DO NOTHING
        """, rows)
        total += len(rows)
        logger.info(f"  {year}: {len(rows)} partidos jugados")

    return total


# ── Paso 5: Standings ─────────────────────────────────────────────────────────

def seed_standings(cur, standings: list[dict], season_id_map: dict[int, int]) -> int:
    """Inserta la tabla de posiciones final de cada temporada (snapshot ronda 0)."""
    # Deduplicar: si un equipo aparece en múltiples fases, quedarse con el de más puntos
    best: dict[tuple, dict] = {}
    for s in standings:
        sid = season_id_map.get(s["season"])
        if not sid:
            continue
        key = (sid, s["team_id"])
        if key not in best or s["total_points"] > best[key]["total_points"]:
            best[key] = {**s, "_sid": sid}

    rows = []
    for (sid, _), s in best.items():
        rows.append((
            sid, s["team_id"], 0,       # round=0 = snapshot final de fase
            s["played"], s["won"], s["drawn"], s["lost"],
            s["points_for"], s["points_against"],
            0, 0,                       # tries_for / tries_against (no en la API)
            0, s["bonus_try"], s["bonus_losing"], s["total_points"],
            s.get("position") or 99,
        ))

    execute_values(cur, """
        INSERT INTO standings
            (season_id, team_id, round,
             played, won, drawn, lost,
             points_for, points_against, tries_for, tries_against,
             match_points, bonus_try_points, bonus_losing_points, total_points,
             position)
        VALUES %s
        ON CONFLICT (season_id, team_id, round) DO UPDATE SET
            played = EXCLUDED.played, won = EXCLUDED.won,
            drawn = EXCLUDED.drawn, lost = EXCLUDED.lost,
            points_for = EXCLUDED.points_for,
            points_against = EXCLUDED.points_against,
            bonus_try_points = EXCLUDED.bonus_try_points,
            bonus_losing_points = EXCLUDED.bonus_losing_points,
            total_points = EXCLUDED.total_points,
            position = EXCLUDED.position
    """, rows)
    logger.info(f"  {len(rows)} filas de posiciones insertadas/actualizadas")
    return len(rows)


# ── Paso 5b: Partidos pendientes (fixture no jugado) ─────────────────────────

def _round_robin_schedule(teams: list[int]) -> list[list[tuple[int, int]]]:
    """
    Genera un calendario round-robin para n equipos (n par).
    Retorna lista de rondas, cada ronda es lista de (home_id, away_id).
    Algoritmo de rotación estándar: fija posición 0, rota el resto.
    """
    n = len(teams)
    if n % 2 != 0:
        teams = teams + [-1]   # bye
        n += 1

    rounds = []
    t = list(teams)

    for _ in range(n - 1):
        round_pairs = []
        for i in range(n // 2):
            home = t[i]
            away = t[n - 1 - i]
            if home != -1 and away != -1 and home != away:
                round_pairs.append((home, away))
        rounds.append(round_pairs)
        # Fijar t[0], rotar t[1:]
        t = [t[0]] + [t[-1]] + t[1:-1]

    return rounds


def seed_pending_matches(
    cur,
    all_matches: list[dict],
    season_id_map: dict[int, int],
    current_season: str = CURRENT_SEASON,
) -> int:
    """
    Genera e inserta los partidos pendientes del torneo en curso.
    Usa formato doble round-robin igual que las temporadas anteriores.
    Retorna cantidad de partidos pendientes insertados.
    """
    year = int(current_season)
    sid  = season_id_map.get(year)
    if not sid:
        return 0

    # Equipos de la temporada actual
    played_2026 = [m for m in all_matches if m["season"] == year]
    team_ids: list[int] = sorted({
        tid
        for m in played_2026
        for tid in (m["home_team_id"], m["away_team_id"])
    })

    if not team_ids:
        return 0

    # Pares ya jugados (ordered: home_id, away_id)
    played_pairs: set[tuple[int, int]] = {
        (m["home_team_id"], m["away_team_id"]) for m in played_2026
    }

    # Generar doble round-robin: 2 vueltas (ida y vuelta)
    rounds_vuelta1 = _round_robin_schedule(team_ids)
    rounds_vuelta2 = [
        [(a, h) for h, a in rnd] for rnd in rounds_vuelta1
    ]
    all_rounds = rounds_vuelta1 + rounds_vuelta2   # 18 fechas para 10 equipos

    # Última ronda jugada (para continuar la numeración)
    cur.execute("SELECT MAX(round) FROM matches WHERE season_id = %s", (sid,))
    last_round = (cur.fetchone()[0] or 0)

    rows = []
    round_offset = last_round    # rounds se asignarán last_round+1, +2, ...
    pending_round = round_offset

    for rnd_idx, rnd_pairs in enumerate(all_rounds):
        # Solo insertar fechas cuyas parejas NO estén todas jugadas
        new_in_round = [
            (h, a) for h, a in rnd_pairs
            if h != -1 and a != -1 and (h, a) not in played_pairs
        ]
        if not new_in_round:
            continue   # toda esta fecha ya fue jugada

        pending_round += 1
        for h_id, a_id in new_in_round:
            rows.append((sid, pending_round, None, h_id, a_id, False))

    if rows:
        execute_values(cur, """
            INSERT INTO matches
                (season_id, round, match_date, home_team_id, away_team_id, is_played)
            VALUES %s
            ON CONFLICT DO NOTHING
        """, rows)
        logger.info(f"  {len(rows)} partidos pendientes insertados (temporada {current_season})")
    else:
        logger.info(f"  Sin partidos pendientes para {current_season}")

    return len(rows)


# ── Paso 6: ELO histórico ─────────────────────────────────────────────────────

def compute_and_seed_elo(cur, matches: list[dict], season_id_map: dict[int, int]) -> None:
    """Recalcula ELO desde 2015 en orden cronológico e inserta en elo_ratings."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from models.elo_model import EloSystem, EloConfig
    except ImportError as e:
        logger.error(f"No se pudo importar EloSystem: {e}")
        return

    elo = EloSystem(EloConfig())

    # Solo partidos de fase regular para ELO (excluir playoffs para evitar sesgo)
    regular_matches = [m for m in matches if m["round_name"] in REGULAR_PHASES
                       or m["round_name"] in {"Zona Campeonato", "Zona Reclasificacion",
                                               "Regular season", "First phase"}]

    # Ordenar cronológicamente
    def sort_key(m):
        dt = _parse_date(m.get("date", ""))
        return (m["season"], dt or datetime(9999, 1, 1))

    regular_matches.sort(key=sort_key)

    cur.execute("DELETE FROM elo_ratings")
    logger.info(f"  Procesando {len(regular_matches)} partidos para ELO…")

    elo_rows = []
    prev_season = None
    for m in regular_matches:
        yr = m["season"]
        sid = season_id_map.get(yr)
        if not sid:
            continue

        # Decay entre temporadas
        if prev_season and yr != prev_season:
            elo.apply_season_decay()
        prev_season = yr

        h_id  = m["home_team_id"]
        a_id  = m["away_team_id"]
        h_bef = elo.ratings.get(h_id, elo.config.initial_rating)
        a_bef = elo.ratings.get(a_id, elo.config.initial_rating)

        elo.update(h_id, a_id, m["home_score"], m["away_score"])

        h_aft = elo.ratings[h_id]
        a_aft = elo.ratings[a_id]
        diff  = m["home_score"] - m["away_score"]

        if diff > 0:
            h_result, a_result = "win", "loss"
        elif diff < 0:
            h_result, a_result = "loss", "win"
        else:
            h_result, a_result = "draw", "draw"

        elo_rows.append((h_id, sid, h_bef, h_aft, a_id, h_result, True,  int(diff)))
        elo_rows.append((a_id, sid, a_bef, a_aft, h_id, a_result, False, int(-diff)))

    execute_values(cur, """
        INSERT INTO elo_ratings
            (team_id, season_id, rating_before, rating_after,
             opponent_id, result, is_home, score_diff)
        VALUES %s
    """, elo_rows)

    # Guardar ratings actuales en team_stats
    for tid, rating in elo.ratings.items():
        sid_2026 = season_id_map.get(int(CURRENT_SEASON))
        if not sid_2026:
            continue
        cur.execute("""
            INSERT INTO team_stats (team_id, season_id, elo_rating)
            VALUES (%s, %s, %s)
            ON CONFLICT (team_id, season_id) DO UPDATE SET elo_rating = EXCLUDED.elo_rating
        """, (tid, sid_2026, rating))

    logger.info(f"  {len(elo_rows)} filas ELO insertadas")
    logger.info("  ELO ratings actuales:")
    for tid, rating in sorted(elo.ratings.items(), key=lambda x: -x[1]):
        logger.info(f"    {tid}: {rating:.1f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def clear_existing_data(cur) -> None:
    """Elimina todos los datos previos para evitar duplicados en re-ejecución."""
    cur.execute("DELETE FROM elo_ratings")
    cur.execute("DELETE FROM team_stats")
    cur.execute("DELETE FROM standings")
    cur.execute("DELETE FROM matches")
    cur.execute("DELETE FROM seasons")
    cur.execute("DELETE FROM teams")
    logger.info("  Datos previos eliminados")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-elo", action="store_true",
                        help="No recalcular ELO histórico")
    parser.add_argument("--force", action="store_true",
                        help="Eliminar datos existentes antes de insertar")
    args = parser.parse_args()

    if not RAW_JSON.exists():
        logger.error(f"No existe {RAW_JSON}. Ejecutá primero: python scripts/scraper.py --all")
        sys.exit(1)

    logger.info(f"Cargando {RAW_JSON}…")
    with open(RAW_JSON, encoding="utf-8") as f:
        data = json.load(f)

    # El scraper guarda las claves como "matches"/"standings"; soportar ambos formatos
    all_matches   = data.get("all_matches") or data.get("matches", [])
    all_standings = data.get("all_standings") or data.get("standings", [])
    # Construir season_meta desde los partidos si no viene como dict
    raw_meta = data.get("seasons", {})
    if isinstance(raw_meta, list):
        season_meta = {str(yr): {} for yr in raw_meta}
    elif isinstance(raw_meta, dict):
        season_meta = raw_meta
    else:
        season_meta = {str(m["season"]) for m in all_matches}
        season_meta = {yr: {} for yr in season_meta}

    logger.info(f"  {len(all_matches)} partidos, {len(all_standings)} posiciones en {len(season_meta)} temporadas")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Verificar si ya hay datos
            cur.execute("SELECT COUNT(*) FROM teams")
            existing_teams = cur.fetchone()[0]
            if existing_teams > 0:
                if args.force:
                    logger.info("--force: limpiando datos previos…")
                else:
                    logger.info(f"DB ya tiene {existing_teams} equipos — actualizando datos de {CURRENT_SEASON}…")
            if args.force:
                logger.info("Paso 0: Limpiando datos previos…")
                clear_existing_data(cur)

            logger.info("Paso 1: Equipos…")
            seed_teams(cur, all_matches)

            logger.info("Paso 2: Temporadas…")
            season_id_map = seed_seasons(cur, season_meta)

            logger.info("Paso 3: Partidos…")
            n_matches = seed_matches(cur, all_matches, season_id_map)

            logger.info("Paso 4: Posiciones…")
            n_standings = seed_standings(cur, all_standings, season_id_map)

            logger.info(f"Paso 4b: Partidos pendientes {CURRENT_SEASON}…")
            n_pending = seed_pending_matches(cur, all_matches, season_id_map)

            if not args.skip_elo:
                logger.info("Paso 5: ELO histórico…")
                compute_and_seed_elo(cur, all_matches, season_id_map)

        conn.commit()
        logger.info("✓ Commit exitoso")
        print(f"\n✓ Seed completado:")
        print(f"  Partidos jugados: {n_matches}")
        print(f"  Partidos pend.:   {n_pending}")
        print(f"  Posiciones:       {n_standings}")
        print(f"  Temporadas:       {sorted(season_id_map.keys())}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error: {e}", exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
