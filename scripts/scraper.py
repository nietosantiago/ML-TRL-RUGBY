"""
Scraper para el Torneo Regional del Litoral de Rugby.
Fuente: http://rugbyarchive.net/api/stagionicompetizione/121/stagione/{year}/?cultura=en

USO:
  python scripts/scraper.py --season 2026          # solo temporada actual
  python scripts/scraper.py --all                  # todas las temporadas
  python scripts/scraper.py --save-db              # guardar en PostgreSQL
"""

import os, sys, json, time, logging, argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
import urllib.request

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler("logs/scraper.log", encoding="utf-8")],
)
logger = logging.getLogger("trl_scraper")

# ── Configuración ────────────────────────────────────────────────────────────
API_BASE       = "http://rugbyarchive.net/api/stagionicompetizione/121/stagione/{year}/?cultura=en"
COMPETITION_ID = 121
ALL_SEASONS    = ["2015","2016","2017","2018","2019","2021","2022","2023","2024","2025","2026"]
CURRENT_SEASON = "2026"
# ─────────────────────────────────────────────────────────────────────────────

def _fix(s):
    """Repara encoding roto UTF-8 → latin1 de la API."""
    if not isinstance(s, str):
        return s
    return (s.replace('Ã\xa0','à').replace('Ã ','à').replace('Ã¡','á')
             .replace('Ã©','é').replace('Ã­','í').replace('Ã³','ó')
             .replace('Ãº','ú').replace('Ã±','ñ').replace('Ã\x00 ','à')
             .replace('Â°','°'))


def fetch_season(year: str) -> Optional[dict]:
    url = API_BASE.format(year=year)
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TRL-Scraper/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            logger.info(f"[{year}] OK — {len(data.get('partiteGiocate',[]))} partidos en respuesta")
            return data
        except Exception as e:
            logger.warning(f"[{year}] intento {attempt}/3: {e}")
            time.sleep(3)
    return None


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_matches(data: dict, year: int) -> list[dict]:
    matches = []
    for entry in data.get("partiteGiocate", []):
        p = entry.get("partita")
        if not p:
            continue
        res = str(p.get("risultato", ""))
        if "-" not in res:
            continue
        try:
            hs, aw = map(int, res.split("-"))
        except ValueError:
            continue

        matches.append({
            "season":       year,
            "round_name":   entry.get("turno", ""),
            "date":         entry.get("data", ""),
            "home_team":    _fix(p["squadraCasa"]["nome"]),
            "home_team_id": p["squadraCasa"]["id"],
            "away_team":    _fix(p["squadraTrasferta"]["nome"]),
            "away_team_id": p["squadraTrasferta"]["id"],
            "home_score":   hs,
            "away_score":   aw,
            "match_id":     p.get("idPartita"),
        })
    return matches


def parse_standings(data: dict, year: int) -> list[dict]:
    rows = []
    for fase in data.get("fasi", []):
        if fase.get("tipoFase") != 0:
            continue
        fase_name = _fix(fase["nomeFase"])
        for sf in fase.get("sottoFasi", []):
            for grupo in (sf.get("gruppi") or []):
                for c in grupo.get("classifiche", []):
                    rows.append({
                        "season":         year,
                        "fase":           fase_name,
                        "position":       int(c["posizione"]) if str(c["posizione"]).isdigit() else None,
                        "team":           _fix(c["squadra"]["nome"]),
                        "team_id":        c["squadra"]["id"],
                        "played":         c["partiteGiocate"],
                        "won":            c["vinte"],
                        "drawn":          c["pareggiate"],
                        "lost":           c["perse"],
                        "points_for":     c["puntiFatti"],
                        "points_against": c["puntiSubiti"],
                        "point_diff":     c["differenzaPunti"],
                        "bonus_try":      c["bonusOffensivo"],
                        "bonus_losing":   c["bonusDifensivo"],
                        "total_points":   int(c["puntiClassifica"]) if str(c["puntiClassifica"]).isdigit() else 0,
                        "description":    _fix(c.get("descrizione") or ""),
                    })
    return rows


def parse_playoffs(data: dict, year: int) -> list[dict]:
    results = []
    for fase in data.get("fasi", []):
        if fase.get("tipoFase") == 0:
            continue
        fase_name = _fix(fase["nomeFase"])
        for sf in fase.get("sottoFasi", []):
            for turno in (sf.get("turniFasiFinali") or []):
                turno_name = _fix(turno["nomeTurno"])
                for partido in (turno.get("partite") or []):
                    if not partido or not partido.get("primaSquadra") or not partido.get("secondaSquadra"):
                        continue
                    eq1 = _fix(partido["primaSquadra"]["nome"])
                    eq2 = _fix(partido["secondaSquadra"]["nome"])
                    winner = _fix((partido.get("vincente") or {}).get("nome", ""))
                    for p in partido.get("partite", []):
                        try:
                            hs, aw = map(int, str(p["risultato"]).split("-"))
                        except:
                            continue
                        results.append({
                            "season":      year,
                            "fase":        fase_name,
                            "round_name":  turno_name,
                            "date":        p["data"],
                            "home_team":   eq1,
                            "away_team":   eq2,
                            "home_score":  hs,
                            "away_score":  aw,
                            "winner":      winner,
                        })
    return results


def parse_champion(data: dict) -> Optional[str]:
    for v in data.get("vincitori", []):
        if v.get("squadre"):
            return _fix(v["squadre"][0]["nome"])
    return None


# ── DB ────────────────────────────────────────────────────────────────────────

def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "trl_db"),
        user=os.getenv("DB_USER", "trl_user"),
        password=os.getenv("DB_PASSWORD", "trl_password"),
    )


def save_to_db(all_matches: list[dict], all_standings: list[dict]) -> None:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # Collect all team names/ids
            all_team_ids = {}
            for m in all_matches:
                all_team_ids[m["home_team_id"]] = m["home_team"]
                all_team_ids[m["away_team_id"]] = m["away_team"]
            for s in all_standings:
                all_team_ids[s["team_id"]] = s["team"]

            for tid, tname in all_team_ids.items():
                cur.execute("""
                    INSERT INTO teams (id, name)
                    VALUES (%s, %s)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                """, (tid, tname))

            # Seasons
            all_years = sorted(set(m["season"] for m in all_matches))
            season_id_map = {}
            for yr in all_years:
                is_cur = (str(yr) == CURRENT_SEASON)
                cur.execute("""
                    INSERT INTO seasons (year, name, is_current)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (year, name) DO UPDATE
                        SET is_current = EXCLUDED.is_current
                    RETURNING id
                """, (yr, f"TRL {yr}", is_cur))
                season_id_map[yr] = cur.fetchone()[0]

            # Matches
            match_rows = []
            for m in all_matches:
                sid = season_id_map.get(m["season"])
                if not sid:
                    continue
                date_val = None
                if m["date"]:
                    try:
                        d, mo, y = m["date"].split("/")
                        date_val = f"{y}-{mo}-{d}"
                    except:
                        pass
                is_played = True
                match_rows.append((
                    sid, m["round_name"], date_val,
                    m["home_team_id"], m["away_team_id"],
                    m["home_score"], m["away_score"],
                    is_played,
                ))

            execute_values(cur, """
                INSERT INTO matches
                    (season_id, round, match_date, home_team_id, away_team_id,
                     home_score, away_score, is_played)
                VALUES %s ON CONFLICT DO NOTHING
            """, match_rows)

            # Standings (solo la tabla regular — round=0 como snapshot final)
            standing_rows = []
            for s in all_standings:
                sid = season_id_map.get(s["season"])
                if not sid:
                    continue
                standing_rows.append((
                    sid, s["team_id"], 0,
                    s["played"], s["won"], s["drawn"], s["lost"],
                    s["points_for"], s["points_against"],
                    0, 0,
                    0, s["bonus_try"], s["bonus_losing"], s["total_points"],
                    s["position"] or 99,
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
                    points_for = EXCLUDED.points_for, points_against = EXCLUDED.points_against,
                    bonus_try_points = EXCLUDED.bonus_try_points,
                    bonus_losing_points = EXCLUDED.bonus_losing_points,
                    total_points = EXCLUDED.total_points, position = EXCLUDED.position
            """, standing_rows)

        conn.commit()
        logger.info(f"DB: {len(match_rows)} partidos, {len(standing_rows)} filas tabla guardados")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error: {e}")
        raise
    finally:
        conn.close()


# ── Orquestador ───────────────────────────────────────────────────────────────

class TRLScraper:
    def __init__(self, seasons: list[str]):
        self.seasons = seasons
        self.all_matches: list[dict] = []
        self.all_standings: list[dict] = []
        self.all_playoffs: list[dict] = []
        self.champions: dict[str, str] = {}

    def run(self) -> dict:
        for year in self.seasons:
            logger.info(f"=== Procesando temporada {year} ===")
            data = fetch_season(year)
            if not data:
                continue
            matches   = parse_matches(data, int(year))
            standings = parse_standings(data, int(year))
            playoffs  = parse_playoffs(data, int(year))
            champion  = parse_champion(data)

            self.all_matches.extend(matches)
            self.all_standings.extend(standings)
            self.all_playoffs.extend(playoffs)
            if champion:
                self.champions[year] = champion

            logger.info(f"  {year}: {len(matches)} partidos, {len(standings)} tablas, campeon={champion}")
            time.sleep(0.3)

        return {
            "scraped_at": datetime.now().isoformat(),
            "seasons": self.seasons,
            "total_matches": len(self.all_matches),
            "champions": self.champions,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=str, default=CURRENT_SEASON, help="Año a scrappear")
    parser.add_argument("--all",    action="store_true", help="Todas las temporadas")
    parser.add_argument("--save-db", action="store_true")
    parser.add_argument("--output",  default="data/raw")
    args = parser.parse_args()

    os.makedirs("logs", exist_ok=True)
    seasons = ALL_SEASONS if args.all else [args.season]

    scraper = TRLScraper(seasons)
    summary = scraper.run()

    # Guardar raw JSON
    Path(args.output).mkdir(parents=True, exist_ok=True)
    out_path = Path(args.output) / f"trl_{'+'.join(seasons)}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": summary,
            "matches": scraper.all_matches,
            "standings": scraper.all_standings,
            "playoffs": scraper.all_playoffs,
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"Guardado: {out_path}")

    if args.save_db:
        save_to_db(scraper.all_matches, scraper.all_standings)

    print(f"\n✓ Scraping completado: {summary['total_matches']} partidos | temporadas: {seasons}")
    print(f"  Campeones: {summary['champions']}")


if __name__ == "__main__":
    main()
