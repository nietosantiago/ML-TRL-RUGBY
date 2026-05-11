"""
Carga el fixture oficial del TRL 2026 Primera División en la base de datos.
Reemplaza los partidos pendientes generados algorítmicamente con el fixture real.

USO:
  python scripts/load_fixture_2026.py              # carga el fixture
  python scripts/load_fixture_2026.py --dry-run    # muestra sin insertar
  python scripts/load_fixture_2026.py --show-teams # lista equipos en la DB
"""

import os, sys, logging, argparse
from datetime import date
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("load_fixture")

CURRENT_SEASON = 2026

# ── Fixture oficial TRL 2026 Primera División ─────────────────────────────────
# (fecha DD/MM/YYYY, nro_fecha, local, visitante)
FIXTURE = [
    # Fecha 1 - 21/03/2026
    ("21/03/2026", 1, "SANTA FE RUGBY CLUB",       "CLUB UNIVERSITARIO"),
    ("21/03/2026", 1, "OLD RESIAN CLUB",            "GIMNASIA Y ESGRIMA"),
    ("21/03/2026", 1, "PARANA ROWING CLUB",         "CLUB A.ESTUDIANTES PARANA"),
    ("21/03/2026", 1, "C.R.A.I.",                   "DUENDES RUGBY CLUB"),
    ("21/03/2026", 1, "JOCKEY CLUB VDO.TUERTO",     "JOCKEY CLUB ROSARIO"),
    # Fecha 2 - 11/04/2026
    ("11/04/2026", 2, "CLUB UNIVERSITARIO",         "JOCKEY CLUB VDO.TUERTO"),
    ("11/04/2026", 2, "JOCKEY CLUB ROSARIO",        "C.R.A.I."),
    ("11/04/2026", 2, "DUENDES RUGBY CLUB",         "PARANA ROWING CLUB"),
    ("11/04/2026", 2, "CLUB A.ESTUDIANTES PARANA",  "OLD RESIAN CLUB"),
    ("11/04/2026", 2, "GIMNASIA Y ESGRIMA",         "SANTA FE RUGBY CLUB"),
    # Fecha 3 - 18/04/2026
    ("18/04/2026", 3, "GIMNASIA Y ESGRIMA",         "CLUB UNIVERSITARIO"),
    ("18/04/2026", 3, "SANTA FE RUGBY CLUB",        "CLUB A.ESTUDIANTES PARANA"),
    ("18/04/2026", 3, "OLD RESIAN CLUB",            "DUENDES RUGBY CLUB"),
    ("18/04/2026", 3, "PARANA ROWING CLUB",         "JOCKEY CLUB ROSARIO"),
    ("18/04/2026", 3, "C.R.A.I.",                   "JOCKEY CLUB VDO.TUERTO"),
    # Fecha 4 - 02/05/2026
    ("02/05/2026", 4, "CLUB UNIVERSITARIO",         "C.R.A.I."),
    ("02/05/2026", 4, "JOCKEY CLUB VDO.TUERTO",     "PARANA ROWING CLUB"),
    ("02/05/2026", 4, "JOCKEY CLUB ROSARIO",        "OLD RESIAN CLUB"),
    ("02/05/2026", 4, "DUENDES RUGBY CLUB",         "SANTA FE RUGBY CLUB"),
    ("02/05/2026", 4, "CLUB A.ESTUDIANTES PARANA",  "GIMNASIA Y ESGRIMA"),
    # Fecha 5 - 09/05/2026
    ("09/05/2026", 5, "CLUB A.ESTUDIANTES PARANA",  "CLUB UNIVERSITARIO"),
    ("09/05/2026", 5, "GIMNASIA Y ESGRIMA",         "DUENDES RUGBY CLUB"),
    ("09/05/2026", 5, "SANTA FE RUGBY CLUB",        "JOCKEY CLUB ROSARIO"),
    ("09/05/2026", 5, "OLD RESIAN CLUB",            "JOCKEY CLUB VDO.TUERTO"),
    ("09/05/2026", 5, "PARANA ROWING CLUB",         "C.R.A.I."),
    # Fecha 6 - 16/05/2026
    ("16/05/2026", 6, "CLUB UNIVERSITARIO",         "PARANA ROWING CLUB"),
    ("16/05/2026", 6, "C.R.A.I.",                   "OLD RESIAN CLUB"),
    ("16/05/2026", 6, "JOCKEY CLUB VDO.TUERTO",     "SANTA FE RUGBY CLUB"),
    ("16/05/2026", 6, "JOCKEY CLUB ROSARIO",        "GIMNASIA Y ESGRIMA"),
    ("16/05/2026", 6, "DUENDES RUGBY CLUB",         "CLUB A.ESTUDIANTES PARANA"),
    # Fecha 7 - 06/06/2026
    ("06/06/2026", 7, "DUENDES RUGBY CLUB",         "CLUB UNIVERSITARIO"),
    ("06/06/2026", 7, "CLUB A.ESTUDIANTES PARANA",  "JOCKEY CLUB ROSARIO"),
    ("06/06/2026", 7, "GIMNASIA Y ESGRIMA",         "JOCKEY CLUB VDO.TUERTO"),
    ("06/06/2026", 7, "SANTA FE RUGBY CLUB",        "C.R.A.I."),
    ("06/06/2026", 7, "OLD RESIAN CLUB",            "PARANA ROWING CLUB"),
    # Fecha 8 - 13/06/2026
    ("13/06/2026", 8, "CLUB UNIVERSITARIO",         "OLD RESIAN CLUB"),
    ("13/06/2026", 8, "PARANA ROWING CLUB",         "SANTA FE RUGBY CLUB"),
    ("13/06/2026", 8, "C.R.A.I.",                   "GIMNASIA Y ESGRIMA"),
    ("13/06/2026", 8, "JOCKEY CLUB VDO.TUERTO",     "CLUB A.ESTUDIANTES PARANA"),
    ("13/06/2026", 8, "JOCKEY CLUB ROSARIO",        "DUENDES RUGBY CLUB"),
    # Fecha 9 - 04/07/2026
    ("04/07/2026", 9, "JOCKEY CLUB ROSARIO",        "CLUB UNIVERSITARIO"),
    ("04/07/2026", 9, "DUENDES RUGBY CLUB",         "JOCKEY CLUB VDO.TUERTO"),
    ("04/07/2026", 9, "CLUB A.ESTUDIANTES PARANA",  "C.R.A.I."),
    ("04/07/2026", 9, "GIMNASIA Y ESGRIMA",         "PARANA ROWING CLUB"),
    ("04/07/2026", 9, "SANTA FE RUGBY CLUB",        "OLD RESIAN CLUB"),
    # Fecha 10 - 11/07/2026
    ("11/07/2026", 10, "CLUB UNIVERSITARIO",        "SANTA FE RUGBY CLUB"),
    ("11/07/2026", 10, "GIMNASIA Y ESGRIMA",        "OLD RESIAN CLUB"),
    ("11/07/2026", 10, "CLUB A.ESTUDIANTES PARANA", "PARANA ROWING CLUB"),
    ("11/07/2026", 10, "DUENDES RUGBY CLUB",        "C.R.A.I."),
    ("11/07/2026", 10, "JOCKEY CLUB ROSARIO",       "JOCKEY CLUB VDO.TUERTO"),
    # Fecha 11 - 18/07/2026
    ("18/07/2026", 11, "JOCKEY CLUB VDO.TUERTO",    "CLUB UNIVERSITARIO"),
    ("18/07/2026", 11, "C.R.A.I.",                  "JOCKEY CLUB ROSARIO"),
    ("18/07/2026", 11, "PARANA ROWING CLUB",        "DUENDES RUGBY CLUB"),
    ("18/07/2026", 11, "OLD RESIAN CLUB",           "CLUB A.ESTUDIANTES PARANA"),
    ("18/07/2026", 11, "SANTA FE RUGBY CLUB",       "GIMNASIA Y ESGRIMA"),
    # Fecha 12 - 08/08/2026
    ("08/08/2026", 12, "CLUB UNIVERSITARIO",        "GIMNASIA Y ESGRIMA"),
    ("08/08/2026", 12, "CLUB A.ESTUDIANTES PARANA", "SANTA FE RUGBY CLUB"),
    ("08/08/2026", 12, "DUENDES RUGBY CLUB",        "OLD RESIAN CLUB"),
    ("08/08/2026", 12, "JOCKEY CLUB ROSARIO",       "PARANA ROWING CLUB"),
    ("08/08/2026", 12, "JOCKEY CLUB VDO.TUERTO",    "C.R.A.I."),
    # Fecha 13 - 22/08/2026
    ("22/08/2026", 13, "C.R.A.I.",                  "CLUB UNIVERSITARIO"),
    ("22/08/2026", 13, "PARANA ROWING CLUB",        "JOCKEY CLUB VDO.TUERTO"),
    ("22/08/2026", 13, "OLD RESIAN CLUB",           "JOCKEY CLUB ROSARIO"),
    ("22/08/2026", 13, "SANTA FE RUGBY CLUB",       "DUENDES RUGBY CLUB"),
    ("22/08/2026", 13, "GIMNASIA Y ESGRIMA",        "CLUB A.ESTUDIANTES PARANA"),
    # Fecha 14 - 29/08/2026
    ("29/08/2026", 14, "CLUB UNIVERSITARIO",        "CLUB A.ESTUDIANTES PARANA"),
    ("29/08/2026", 14, "DUENDES RUGBY CLUB",        "GIMNASIA Y ESGRIMA"),
    ("29/08/2026", 14, "JOCKEY CLUB ROSARIO",       "SANTA FE RUGBY CLUB"),
    ("29/08/2026", 14, "JOCKEY CLUB VDO.TUERTO",    "OLD RESIAN CLUB"),
    ("29/08/2026", 14, "C.R.A.I.",                  "PARANA ROWING CLUB"),
    # Fecha 15 - 19/09/2026
    ("19/09/2026", 15, "PARANA ROWING CLUB",        "CLUB UNIVERSITARIO"),
    ("19/09/2026", 15, "OLD RESIAN CLUB",           "C.R.A.I."),
    ("19/09/2026", 15, "SANTA FE RUGBY CLUB",       "JOCKEY CLUB VDO.TUERTO"),
    ("19/09/2026", 15, "GIMNASIA Y ESGRIMA",        "JOCKEY CLUB ROSARIO"),
    ("19/09/2026", 15, "CLUB A.ESTUDIANTES PARANA", "DUENDES RUGBY CLUB"),
    # Fecha 16 - 10/10/2026
    ("10/10/2026", 16, "CLUB UNIVERSITARIO",        "DUENDES RUGBY CLUB"),
    ("10/10/2026", 16, "JOCKEY CLUB ROSARIO",       "CLUB A.ESTUDIANTES PARANA"),
    ("10/10/2026", 16, "JOCKEY CLUB VDO.TUERTO",    "GIMNASIA Y ESGRIMA"),
    ("10/10/2026", 16, "C.R.A.I.",                  "SANTA FE RUGBY CLUB"),
    ("10/10/2026", 16, "PARANA ROWING CLUB",        "OLD RESIAN CLUB"),
    # Fecha 17 - 17/10/2026
    ("17/10/2026", 17, "OLD RESIAN CLUB",           "CLUB UNIVERSITARIO"),
    ("17/10/2026", 17, "SANTA FE RUGBY CLUB",       "PARANA ROWING CLUB"),
    ("17/10/2026", 17, "GIMNASIA Y ESGRIMA",        "C.R.A.I."),
    ("17/10/2026", 17, "CLUB A.ESTUDIANTES PARANA", "JOCKEY CLUB VDO.TUERTO"),
    ("17/10/2026", 17, "DUENDES RUGBY CLUB",        "JOCKEY CLUB ROSARIO"),
    # Fecha 18 - 24/10/2026
    ("24/10/2026", 18, "CLUB UNIVERSITARIO",        "JOCKEY CLUB ROSARIO"),
    ("24/10/2026", 18, "JOCKEY CLUB VDO.TUERTO",    "DUENDES RUGBY CLUB"),
    ("24/10/2026", 18, "C.R.A.I.",                  "CLUB A.ESTUDIANTES PARANA"),
    ("24/10/2026", 18, "PARANA ROWING CLUB",        "GIMNASIA Y ESGRIMA"),
    ("24/10/2026", 18, "OLD RESIAN CLUB",           "SANTA FE RUGBY CLUB"),
]


def get_conn():
    db_url = (os.getenv("DATABASE_URL") or "").strip()
    if db_url:
        return psycopg2.connect(db_url)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "trl_db"),
        user=os.getenv("DB_USER", "trl_user"),
        password=os.getenv("DB_PASSWORD", "trl_password"),
    )


# Mapeo directo: nombre en el fixture → ID en la DB
NAME_MAP = {
    "SANTA FE RUGBY CLUB":       1271,   # Santa Fe R.C.
    "CLUB UNIVERSITARIO":        1284,   # Universitario Rosario
    "OLD RESIAN CLUB":           1294,   # Old Resian
    "GIMNASIA Y ESGRIMA":        1265,   # G.E.R.
    "PARANA ROWING CLUB":        1338,   # Paraná Rowing
    "CLUB A.ESTUDIANTES PARANA": 1186,   # Estudiantes Paranà
    "C.R.A.I.":                  1290,   # C.R.A.I.
    "DUENDES RUGBY CLUB":        1223,   # Duendes
    "JOCKEY CLUB VDO.TUERTO":    8396,   # Jockey Club Venado Tuerto
    "JOCKEY CLUB ROSARIO":       1221,   # Jockey Club Rosario
}


def find_team_id(teams: dict[int, str], fixture_name: str) -> int | None:
    """Busca team_id usando el mapeo directo."""
    return NAME_MAP.get(fixture_name.strip().upper())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",    action="store_true", help="Mostrar sin insertar")
    parser.add_argument("--show-teams", action="store_true", help="Listar equipos en DB y salir")
    args = parser.parse_args()

    conn = get_conn()
    cur  = conn.cursor()

    # Obtener season_id actual
    cur.execute("SELECT id FROM seasons WHERE year = %s", (CURRENT_SEASON,))
    row = cur.fetchone()
    if not row:
        logger.error(f"Temporada {CURRENT_SEASON} no encontrada en la DB. Corré seed_data.py primero.")
        sys.exit(1)
    season_id = row[0]

    # Obtener equipos de la temporada 2026
    cur.execute("""
        SELECT DISTINCT t.id, t.name
        FROM teams t
        JOIN matches m ON (m.home_team_id = t.id OR m.away_team_id = t.id)
        WHERE m.season_id = %s
        ORDER BY t.name
    """, (season_id,))
    teams = {row[0]: row[1] for row in cur.fetchall()}

    if args.show_teams:
        print(f"\nEquipos en DB para temporada {CURRENT_SEASON}:")
        for tid, tname in sorted(teams.items(), key=lambda x: x[1]):
            print(f"  {tid:5d}  {tname}")
        cur.close(); conn.close()
        return

    # Resolver IDs para cada entrada del fixture
    resolved = []
    errors   = []
    for fecha_str, rnd, home_name, away_name in FIXTURE:
        d, m, y  = fecha_str.split("/")
        match_date = date(int(y), int(m), int(d))

        h_id = find_team_id(teams, home_name)
        a_id = find_team_id(teams, away_name)

        if h_id is None:
            errors.append(f"  No encontrado: '{home_name}'")
        if a_id is None:
            errors.append(f"  No encontrado: '{away_name}'")
        if h_id and a_id:
            resolved.append((season_id, rnd, match_date, h_id, a_id))

    if errors:
        logger.error("No se pudieron resolver los siguientes equipos:")
        for e in errors:
            print(e)
        print("\nCorré con --show-teams para ver los nombres exactos en la DB.")
        sys.exit(1)

    logger.info(f"Fixture resuelto: {len(resolved)} partidos en {CURRENT_SEASON}")

    # Partidos ya jugados (no tocar)
    cur.execute("""
        SELECT home_team_id, away_team_id FROM matches
        WHERE season_id = %s AND is_played = TRUE
    """, (season_id,))
    played_pairs = {(r[0], r[1]) for r in cur.fetchall()}
    logger.info(f"  Partidos ya jugados en DB: {len(played_pairs)}")

    # Separar jugados vs pendientes del fixture
    pending = [
        (sid, rnd, mdate, h, a, False)
        for sid, rnd, mdate, h, a in resolved
        if (h, a) not in played_pairs
    ]
    already_played_in_fixture = len(resolved) - len(pending)
    logger.info(f"  Ya jugados (no se tocan): {already_played_in_fixture}")
    logger.info(f"  Pendientes a insertar:    {len(pending)}")

    if args.dry_run:
        print("\n[DRY RUN] Partidos que se insertarían como pendientes:")
        for sid, rnd, mdate, h, a, _ in pending:
            print(f"  Fecha {rnd:2d} | {mdate} | {teams[h]:35s} vs {teams[a]}")
        cur.close(); conn.close()
        return

    # Borrar pendientes actuales de 2026
    cur.execute(
        "DELETE FROM matches WHERE season_id = %s AND is_played = FALSE",
        (season_id,)
    )
    deleted = cur.rowcount
    logger.info(f"  Partidos pendientes eliminados: {deleted}")

    # Insertar fixture real
    if pending:
        execute_values(cur, """
            INSERT INTO matches (season_id, round, match_date, home_team_id, away_team_id, is_played)
            VALUES %s
        """, pending)
        logger.info(f"  {len(pending)} partidos pendientes insertados con fixture oficial")

    conn.commit()
    cur.close()
    conn.close()
    print(f"\n✓ Fixture 2026 cargado: {len(pending)} partidos pendientes con fechas y orden reales.")


if __name__ == "__main__":
    main()
