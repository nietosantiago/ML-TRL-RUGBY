"""
Validación histórica (backtesting) de modelos predictivos TRL.

Metodología:
- Walk-forward: entrenar con temporadas T-n ... T-1, evaluar en T
- Evita data leakage: el modelo nunca ve datos del futuro
- Métricas: Log Loss, Accuracy, Brier Score
- Comparación entre ELO, Logística y XGBoost

USO:
  python -m models.validation --seasons 2022 2023 --test 2024
"""

import logging
import argparse
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, accuracy_score, brier_score_loss

from .elo_model import EloSystem, EloConfig
from .feature_engineering import (
    build_dataset_from_db, build_match_features,
    get_current_team_features, FEATURE_NAMES,
)
from .logistic_model import LogisticMatchPredictor, _encode_target
from .xgboost_model import XGBoostMatchPredictor, XGB_AVAILABLE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Evaluación ELO (backtesting puro sin entrenamiento ML)
# ---------------------------------------------------------------------------

def backtest_elo(conn, train_season_ids: list[int], test_season_id: int) -> dict:
    """
    Hace backtesting del sistema ELO.
    Entrena los ratings procesando las temporadas de entrenamiento cronológicamente,
    luego evalúa en los partidos de la temporada test (predice antes de actualizar).
    """
    elo = EloSystem()

    # Fase de entrenamiento: procesar temporadas pasadas para calentar ELO
    with conn.cursor() as cur:
        placeholders = ", ".join(["%s"] * len(train_season_ids))
        cur.execute(f"""
            SELECT m.id, m.round, m.match_date,
                   m.home_team_id, m.away_team_id,
                   m.home_score, m.away_score
            FROM matches m
            WHERE m.season_id IN ({placeholders})
              AND m.is_played = TRUE
            ORDER BY m.match_date, m.round
        """, train_season_ids)
        train_matches = cur.fetchall()

    for match in train_matches:
        (m_id, rnd, m_date, h_id, a_id, hs, as_) = match
        if hs is not None and as_ is not None:
            elo.update(h_id, a_id, hs, as_)

    # Aplicar decay de temporada
    elo.apply_season_decay()

    # Fase de test: predecir ANTES de actualizar
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.id, m.round, m.match_date,
                   m.home_team_id, m.away_team_id,
                   m.home_score, m.away_score
            FROM matches m
            WHERE m.season_id = %s AND m.is_played = TRUE
            ORDER BY m.match_date, m.round
        """, (test_season_id,))
        test_matches = cur.fetchall()

    y_true, y_pred_probs = [], []
    predictions = []

    for match in test_matches:
        (m_id, rnd, m_date, h_id, a_id, hs, as_) = match
        if hs is None or as_ is None:
            continue

        # Predecir ANTES de actualizar
        pred = elo.predict(h_id, a_id)
        p_home, p_draw, p_away = pred["home_win"], pred["draw"], pred["away_win"]

        if hs > as_:
            y_true.append(2)    # home win
        elif hs < as_:
            y_true.append(0)    # away win
        else:
            y_true.append(1)    # draw

        y_pred_probs.append([p_away, p_draw, p_home])

        predictions.append({
            "match_id": m_id,
            "round": rnd,
            "home_id": h_id,
            "away_id": a_id,
            "p_home": p_home,
            "p_draw": p_draw,
            "p_away": p_away,
            "actual": "home" if hs > as_ else ("away" if hs < as_ else "draw"),
        })

        # Actualizar ELO con el resultado real
        elo.update(h_id, a_id, hs, as_)

    if not y_true:
        return {"error": "Sin partidos en temporada test"}

    y_true = np.array(y_true)
    y_pred_probs = np.array(y_pred_probs)
    y_pred = np.argmax(y_pred_probs, axis=1)

    p_home_only = y_pred_probs[:, 2]
    y_binary = (y_true == 2).astype(float)

    return {
        "model": "elo",
        "test_season_id": test_season_id,
        "n_samples": len(y_true),
        "log_loss":    float(log_loss(y_true, y_pred_probs)),
        "accuracy":    float(accuracy_score(y_true, y_pred)),
        "brier_score": float(brier_score_loss(y_binary, p_home_only)),
        "predictions": predictions,
    }


def backtest_ml_model(
    conn,
    train_season_ids: list[int],
    test_season_id: int,
    model_type: str = "logistic",
) -> dict:
    """
    Backtesting de modelos ML (logistic / xgboost).
    Entrena con train_season_ids, evalúa en test_season_id.
    """
    logger.info(f"Backtesting {model_type}: train={train_season_ids}, test={test_season_id}")

    # Dataset de entrenamiento
    df_train = build_dataset_from_db(conn, train_season_ids)
    if len(df_train) < 20:
        return {"error": f"Muy pocos datos de entrenamiento: {len(df_train)}"}

    # Dataset de test
    df_test = build_dataset_from_db(conn, [test_season_id])
    if len(df_test) == 0:
        return {"error": "Sin datos en temporada test"}

    # Entrenar modelo
    if model_type == "logistic":
        predictor = LogisticMatchPredictor(calibrate=True)
    elif model_type == "xgboost":
        if not XGB_AVAILABLE:
            return {"error": "xgboost no instalado"}
        predictor = XGBoostMatchPredictor(calibrate=True)
    else:
        raise ValueError(f"model_type debe ser 'logistic' o 'xgboost', no '{model_type}'")

    predictor.train(df_train, tune_C=(model_type == "logistic"))
    metrics = predictor.evaluate(df_test)
    metrics["model"] = model_type
    metrics["test_season_id"] = test_season_id
    metrics["train_seasons"] = train_season_ids

    return metrics


# ---------------------------------------------------------------------------
#  Comparación completa de modelos
# ---------------------------------------------------------------------------

def compare_models(conn, all_season_ids: list[int]) -> pd.DataFrame:
    """
    Walk-forward cross-validation sobre todas las temporadas disponibles.
    Para cada temporada T >= 2do elemento, usa anteriores para entrenar.

    Returns:
        DataFrame con columnas: model, season, log_loss, accuracy, brier_score
    """
    if len(all_season_ids) < 2:
        raise ValueError("Se necesitan al menos 2 temporadas para validación")

    results = []
    for test_idx in range(1, len(all_season_ids)):
        train_ids = all_season_ids[:test_idx]
        test_id   = all_season_ids[test_idx]

        logger.info(f"--- Fold {test_idx}: train={train_ids}, test={test_id} ---")

        # ELO
        elo_metrics = backtest_elo(conn, train_ids, test_id)
        results.append({
            "model": "ELO",
            "test_season_id": test_id,
            "log_loss":    elo_metrics.get("log_loss"),
            "accuracy":    elo_metrics.get("accuracy"),
            "brier_score": elo_metrics.get("brier_score"),
            "n_samples":   elo_metrics.get("n_samples"),
        })

        # Logistic
        lr_metrics = backtest_ml_model(conn, train_ids, test_id, "logistic")
        results.append({
            "model": "LogisticRegression",
            "test_season_id": test_id,
            "log_loss":    lr_metrics.get("log_loss"),
            "accuracy":    lr_metrics.get("accuracy"),
            "brier_score": lr_metrics.get("brier_score"),
            "n_samples":   lr_metrics.get("n_samples"),
        })

        # XGBoost (opcional)
        if XGB_AVAILABLE:
            xgb_metrics = backtest_ml_model(conn, train_ids, test_id, "xgboost")
            results.append({
                "model": "XGBoost",
                "test_season_id": test_id,
                "log_loss":    xgb_metrics.get("log_loss"),
                "accuracy":    xgb_metrics.get("accuracy"),
                "brier_score": xgb_metrics.get("brier_score"),
                "n_samples":   xgb_metrics.get("n_samples"),
            })

    df = pd.DataFrame(results)
    return df


def select_best_model(comparison_df: pd.DataFrame) -> str:
    """
    Selecciona el mejor modelo basándose en log_loss promedio.
    Menor log_loss = mejor.
    """
    summary = (
        comparison_df.groupby("model")[["log_loss", "accuracy", "brier_score"]]
        .mean()
        .sort_values("log_loss")
    )
    logger.info(f"\nResumen de modelos:\n{summary.to_string()}")
    best = summary.index[0]
    logger.info(f"Mejor modelo: {best}")
    return best


def train_final_model(
    conn,
    all_season_ids: list[int],
    model_type: str = "logistic",
):
    """
    Entrena el modelo seleccionado con TODOS los datos disponibles.
    Este es el modelo que se usa en producción.
    """
    logger.info(f"Entrenando modelo final: {model_type} con temporadas {all_season_ids}")
    df = build_dataset_from_db(conn, all_season_ids)

    if model_type == "logistic":
        model = LogisticMatchPredictor(calibrate=True)
        model.train(df, tune_C=True)
        model.save()
    elif model_type == "xgboost":
        model = XGBoostMatchPredictor(calibrate=True)
        model.train(df, tune_hyperparams=True)
        model.save()
    else:
        raise ValueError(f"model_type desconocido: {model_type}")

    return model


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------

def main():
    import os
    import sys
    sys.path.insert(0, str(__file__).rsplit("/models/", 1)[0])
    from dotenv import load_dotenv
    load_dotenv()
    import psycopg2

    parser = argparse.ArgumentParser(description="Backtesting de modelos TRL")
    parser.add_argument("--train-seasons", nargs="+", type=int, default=[2022, 2023])
    parser.add_argument("--test-season",   type=int, default=2024)
    parser.add_argument("--compare-all",   action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        dbname=os.getenv("DB_NAME", "trl_db"),
        user=os.getenv("DB_USER", "trl_user"),
        password=os.getenv("DB_PASSWORD", "trl_password"),
    )

    if args.compare_all:
        all_ids = args.train_seasons + [args.test_season]
        df = compare_models(conn, all_ids)
        print("\n=== Comparación de modelos (Walk-forward CV) ===")
        print(df.to_string(index=False))

        best = select_best_model(df)
        print(f"\n✓ Mejor modelo: {best}")

        # Entrenar modelo final con todos los datos
        model_key = {"ELO": None, "LogisticRegression": "logistic", "XGBoost": "xgboost"}
        mk = model_key.get(best)
        if mk:
            train_final_model(conn, all_ids, mk)
            print(f"✓ Modelo final '{mk}' guardado en data/models/")
    else:
        for model_name in ["elo", "logistic"] + (["xgboost"] if XGB_AVAILABLE else []):
            if model_name == "elo":
                r = backtest_elo(conn, args.train_seasons, args.test_season)
            else:
                r = backtest_ml_model(conn, args.train_seasons, args.test_season, model_name)
            print(f"\n{model_name.upper()}: log_loss={r.get('log_loss', 'N/A'):.4f}, "
                  f"accuracy={r.get('accuracy', 'N/A'):.3f}, "
                  f"brier={r.get('brier_score', 'N/A'):.4f}")

    conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
