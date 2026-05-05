"""
Entrena los modelos de predicción (Logistic Regression y XGBoost)
usando datos históricos del TRL (2015-2025).

USO:
  python scripts/train_models.py
  python scripts/train_models.py --seasons 2022 2023 2024 2025
  python scripts/train_models.py --skip-xgb   # solo logistic
"""

import sys, json, argparse, logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("train_models")

RAW_JSON   = Path("data/raw/trl_all_seasons.json")
MODELS_DIR = Path("data/models")

REGULAR_PHASES = {"Regular season", "First phase",
                  "Zona Campeonato", "Zona Reclasificacion"}

HOME_ADV = 60.0


# ── ELO simple inline (sin dependencias) ─────────────────────────────────────

class _ELO:
    def __init__(self, k=32, scale=400, initial=1500, home_adv=60, decay=0.3):
        self.ratings = defaultdict(lambda: initial)
        self.k = k; self.scale = scale
        self.home_adv = home_adv; self.decay = decay

    def expected(self, a, b, a_home):
        adj = self.ratings[a] + (self.home_adv if a_home else 0)
        return 1 / (1 + 10 ** ((self.ratings[b] - adj) / self.scale))

    def update(self, h, a, hs, as_):
        ph = self.expected(h, a, True)
        diff = abs(hs - as_)
        k = self.k * min(np.log(diff + 1) / np.log(2), 2.5)
        s_h = 1.0 if hs > as_ else (0.5 if hs == as_ else 0.0)
        self.ratings[h] += k * (s_h - ph)
        self.ratings[a] += k * ((1 - s_h) - (1 - ph))

    def season_decay(self):
        if not self.ratings:
            return
        mean = np.mean(list(self.ratings.values()))
        for t in self.ratings:
            self.ratings[t] = self.ratings[t] * (1 - self.decay) + mean * self.decay


# ── Stats acumulados por equipo ───────────────────────────────────────────────

class _TeamStats:
    def __init__(self):
        self.results   = []     # 1=win, 0.5=draw, 0=loss (cronológico)
        self.pt_diffs  = []
        self.h_games = self.h_wins = 0
        self.a_games = self.a_wins = 0
        self.h_scored = self.h_conc = 0.0
        self.a_scored = self.a_conc = 0.0
        self.streak   = 0

    def snapshot(self):
        """Devuelve features en el momento actual (antes del partido)."""
        last5 = self.results[-5:] or [0.5]
        w = list(range(1, len(last5) + 1))
        form = sum(r * wt for r, wt in zip(last5, w)) / sum(w)

        last5_pd = self.pt_diffs[-5:] or [0.0]
        form_pd = sum(d * wt for d, wt in zip(last5_pd, w)) / sum(w)

        gp = len(self.results)
        return dict(
            form_last5       = form,
            form_pts_last5   = form_pd,
            home_win_pct     = self.h_wins / max(self.h_games, 1),
            away_win_pct     = self.a_wins / max(self.a_games, 1),
            home_avg_scored  = self.h_scored / max(self.h_games, 1),
            away_avg_scored  = self.a_scored / max(self.a_games, 1),
            home_avg_conceded= self.h_conc  / max(self.h_games, 1),
            away_avg_conceded= self.a_conc  / max(self.a_games, 1),
            current_streak   = self.streak,
            games_played     = gp,
        )

    def update(self, pf, pa, is_home):
        diff = pf - pa
        self.pt_diffs.append(diff)
        if pf > pa:
            self.results.append(1.0)
            self.streak = max(self.streak, 0) + 1
        elif pf == pa:
            self.results.append(0.5)
            self.streak = 0
        else:
            self.results.append(0.0)
            self.streak = min(self.streak, 0) - 1

        if is_home:
            self.h_games += 1; self.h_scored += pf; self.h_conc += pa
            if pf > pa: self.h_wins += 1
        else:
            self.a_games += 1; self.a_scored += pf; self.a_conc += pa
            if pf > pa: self.a_wins += 1


# ── H2H acumulado ─────────────────────────────────────────────────────────────

class _H2H:
    def __init__(self):
        self._data = defaultdict(lambda: [0, 0])  # key=(min,max): [a_wins, total]

    def get(self, h_id, a_id):
        key = (min(h_id, a_id), max(h_id, a_id))
        a_wins, total = self._data[key]
        h2h_home_wins = a_wins if h_id < a_id else (total - a_wins)
        return h2h_home_wins, total

    def update(self, h_id, a_id, hs, as_):
        key = (min(h_id, a_id), max(h_id, a_id))
        self._data[key][1] += 1
        if hs > as_ and h_id == key[0]:
            self._data[key][0] += 1
        elif as_ > hs and a_id == key[0]:
            self._data[key][0] += 1


# ── Construcción del dataset ──────────────────────────────────────────────────

def _parse_date(s):
    try:
        d, m, y = s.split("/")
        return datetime(int(y), int(m), int(d))
    except Exception:
        return datetime(9999, 1, 1)


def build_dataset(matches: list[dict], train_seasons: list[int]) -> pd.DataFrame:
    """
    Procesa los partidos en orden cronológico, construyendo features
    sin data leakage (snapshot ANTES de cada partido).
    """
    # Ordenar cronológicamente
    ms = [m for m in matches if m["round_name"] in REGULAR_PHASES]
    ms.sort(key=lambda m: (m["season"], _parse_date(m.get("date", ""))))

    elo   = _ELO()
    stats = defaultdict(_TeamStats)
    h2h   = _H2H()
    rows  = []
    prev_season = None

    for m in ms:
        yr = m["season"]
        if prev_season and yr != prev_season:
            elo.season_decay()
            # Resetear stats de temporada
            stats = defaultdict(_TeamStats)
        prev_season = yr

        h_id = m["home_team_id"]
        a_id = m["away_team_id"]
        hs   = m["home_score"]
        as_  = m["away_score"]

        # Features ANTES del partido
        h_elo = elo.ratings[h_id]
        a_elo = elo.ratings[a_id]
        h_st  = stats[h_id].snapshot()
        a_st  = stats[a_id].snapshot()
        h2h_hw, h2h_tot = h2h.get(h_id, a_id)

        elo_diff = (h_elo + HOME_ADV) - a_elo

        feat = [
            elo_diff, h_elo, a_elo,
            h_st["form_last5"], a_st["form_last5"],
            h_st["form_last5"] - a_st["form_last5"],
            h_st["form_pts_last5"], a_st["form_pts_last5"],
            h_st["form_pts_last5"] - a_st["form_pts_last5"],
            h_st["home_win_pct"], a_st["away_win_pct"],
            h_st["home_avg_scored"], a_st["away_avg_scored"],
            h_st["home_avg_conceded"], a_st["away_avg_conceded"],
            float(h_st["current_streak"]), float(a_st["current_streak"]),
            float(h_st["current_streak"] - a_st["current_streak"]),
            h2h_hw / max(h2h_tot, 1), float(h2h_tot),
            float(h_st["games_played"]), float(a_st["games_played"]),
        ]

        # Target: 1.0=home win, 0.5=draw, 0.0=away win (formato que espera _encode_target)
        if hs > as_:    target = 1.0
        elif hs == as_: target = 0.5
        else:           target = 0.0

        if yr in train_seasons:
            rows.append(feat + [target, yr])

        # Actualizar estado
        elo.update(h_id, a_id, hs, as_)
        stats[h_id].update(hs, as_, is_home=True)
        stats[a_id].update(as_, hs, is_home=False)
        h2h.update(h_id, a_id, hs, as_)

    from models.feature_engineering import FEATURE_NAMES
    df = pd.DataFrame(rows, columns=FEATURE_NAMES + ["target", "season"])
    return df


# ── Entrenamiento ─────────────────────────────────────────────────────────────

def train_and_save(df: pd.DataFrame, skip_xgb: bool = False):
    from models.logistic_model import LogisticMatchPredictor
    from models.feature_engineering import FEATURE_NAMES
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(f"Dataset: {len(df)} partidos | distribución target: {df['target'].value_counts().to_dict()}")

    # ── Logistic Regression ──────────────────────────────────────────────────
    logger.info("Entrenando Logistic Regression…")
    lr = LogisticMatchPredictor()
    metrics = lr.train(df, tune_C=True)
    lr.save(str(MODELS_DIR / "logistic_model.pkl"))
    logger.info(f"  Log-loss: {metrics['train_log_loss']:.4f} | Accuracy: {metrics['train_accuracy']:.3f}")

    if not skip_xgb:
        from models.xgboost_model import XGBoostMatchPredictor
        logger.info("Entrenando XGBoost…")
        xgb = XGBoostMatchPredictor()
        metrics_xgb = xgb.train(df, tune_hyperparams=False)
        xgb.save(str(MODELS_DIR / "xgboost_model.pkl"))
        logger.info(f"  Log-loss: {metrics_xgb['train_log_loss']:.4f} | Accuracy: {metrics_xgb['train_accuracy']:.3f}")

        # Top features
        fi = xgb.feature_importance()
        logger.info("  Top 5 features:")
        for _, row in fi.head(5).iterrows():
            logger.info(f"    {row['feature']}: {row['importance']:.4f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+",
                        default=[2015,2016,2017,2018,2019,2021,2022,2023,2024,2025],
                        help="Temporadas para entrenamiento")
    parser.add_argument("--skip-xgb", action="store_true")
    args = parser.parse_args()

    if not RAW_JSON.exists():
        logger.error(f"No existe {RAW_JSON}. Ejecutá primero: python scripts/scraper.py --all")
        sys.exit(1)

    logger.info(f"Cargando {RAW_JSON}…")
    with open(RAW_JSON, encoding="utf-8") as f:
        data = json.load(f)

    logger.info(f"Construyendo dataset con temporadas: {args.seasons}")
    df = build_dataset(data["all_matches"], set(args.seasons))

    if df.empty:
        logger.error("Dataset vacío. Verificá las temporadas disponibles.")
        sys.exit(1)

    logger.info(f"Dataset listo: {len(df)} partidos")
    train_and_save(df, skip_xgb=args.skip_xgb)

    print(f"\n✓ Modelos guardados en {MODELS_DIR}/")
    print(f"  logistic_model.pkl")
    if not args.skip_xgb:
        print(f"  xgboost_model.pkl")


if __name__ == "__main__":
    main()
