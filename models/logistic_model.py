"""
Modelo de Regresión Logística para predicción de partidos TRL.

Trata el problema como clasificación binaria (home win = 1, no win = 0).
Los empates se manejan como clase separada usando OvR (One vs Rest).

Incluye:
- Calibración de probabilidades (Platt scaling / isotonic)
- Regularización L2 con búsqueda de hiperparámetros
- Persistencia del modelo entrenado
"""

import os
import pickle
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import log_loss, accuracy_score, brier_score_loss

from .feature_engineering import FEATURE_NAMES

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent / "data" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def _encode_target(target: pd.Series) -> np.ndarray:
    """
    Convierte target (0, 0.5, 1) a clases enteras:
    0 = away win, 1 = draw, 2 = home win
    """
    mapping = {0.0: 0, 0.5: 1, 1.0: 2}
    return target.map(mapping).values


def _decode_probs(probs: np.ndarray, classes: np.ndarray) -> dict[str, np.ndarray]:
    """
    Dado un array de probabilidades (n_samples, n_classes) y las clases
    en el orden del modelo, retorna dict con home_win, draw, away_win.
    """
    result = {
        "home_win": np.zeros(len(probs)),
        "draw":     np.zeros(len(probs)),
        "away_win": np.zeros(len(probs)),
    }
    class_map = {0: "away_win", 1: "draw", 2: "home_win"}
    for idx, cls in enumerate(classes):
        key = class_map.get(cls)
        if key:
            result[key] = probs[:, idx]
    return result


class LogisticMatchPredictor:
    """
    Wrapper completo alrededor de scikit-learn LogisticRegression.
    Maneja escalado, calibración y persistencia.
    """

    def __init__(self, C: float = 1.0, calibrate: bool = True):
        self.C = C
        self.calibrate = calibrate
        self.model: Optional[Pipeline] = None
        self.classes_: Optional[np.ndarray] = None
        self.feature_names = FEATURE_NAMES
        self._trained = False

    def _build_pipeline(self, C: float) -> Pipeline:
        base_lr = LogisticRegression(
            C=C,
            multi_class="multinomial",
            solver="lbfgs",
            max_iter=1000,
            random_state=42,
            class_weight="balanced",
        )
        if self.calibrate:
            calibrated = CalibratedClassifierCV(
                base_lr, method="isotonic", cv=3
            )
            return Pipeline([
                ("scaler", StandardScaler()),
                ("clf", calibrated),
            ])
        return Pipeline([
            ("scaler", StandardScaler()),
            ("clf", base_lr),
        ])

    def train(
        self,
        df: pd.DataFrame,
        tune_C: bool = False,
    ) -> dict:
        """
        Entrena el modelo.
        df debe tener columnas FEATURE_NAMES + 'target'

        Returns:
            dict con métricas de validación cruzada.
        """
        X = df[self.feature_names].values.astype(np.float32)
        y = _encode_target(df["target"])

        logger.info(
            f"Logistic: entrenando con {len(X)} muestras, "
            f"clases={np.unique(y, return_counts=True)}"
        )

        best_C = self.C
        if tune_C:
            best_C, cv_score = self._tune_C(X, y)
            logger.info(f"Logistic: mejor C={best_C:.3f} (cv log-loss={cv_score:.4f})")

        self.model = self._build_pipeline(best_C)
        self.model.fit(X, y)

        # Clases pueden no incluir las 3 si hay pocos empates en los datos
        if hasattr(self.model.named_steps["clf"], "classes_"):
            self.classes_ = self.model.named_steps["clf"].classes_
        elif hasattr(self.model.named_steps["clf"], "estimator"):
            self.classes_ = self.model.named_steps["clf"].estimator.classes_
        else:
            self.classes_ = np.array([0, 1, 2])

        self._trained = True

        # Métricas en train (para diagnóstico, no para evaluación final)
        probs = self.model.predict_proba(X)
        y_pred = self.model.predict(X)
        metrics = {
            "train_accuracy": float(accuracy_score(y, y_pred)),
            "train_log_loss": float(log_loss(y, probs)),
            "n_samples": len(X),
            "C": best_C,
        }
        logger.info(f"Logistic metrics: {metrics}")
        return metrics

    def _tune_C(self, X: np.ndarray, y: np.ndarray) -> tuple[float, float]:
        """Grid search simple sobre C usando log-loss en CV."""
        C_values = [0.001, 0.01, 0.1, 0.5, 1.0, 5.0, 10.0]
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        best_C, best_score = 1.0, float("inf")

        for C in C_values:
            pipeline = self._build_pipeline(C)
            scores = cross_val_score(
                pipeline, X, y, cv=cv,
                scoring="neg_log_loss", n_jobs=-1,
            )
            mean_score = -scores.mean()
            if mean_score < best_score:
                best_score, best_C = mean_score, C

        return best_C, best_score

    def predict_proba(self, X: np.ndarray) -> dict[str, np.ndarray]:
        """
        Predice probabilidades para un batch de partidos.
        X: (n_samples, n_features)
        Returns dict: {"home_win": [...], "draw": [...], "away_win": [...]}
        """
        if not self._trained or self.model is None:
            raise RuntimeError("Modelo no entrenado. Llamar a .train() primero.")

        probs = self.model.predict_proba(X)
        return _decode_probs(probs, self.classes_)

    def predict_single(self, features: np.ndarray) -> dict[str, float]:
        """Predice un único partido."""
        probs = self.predict_proba(features.reshape(1, -1))
        return {
            "home_win": float(probs["home_win"][0]),
            "draw":     float(probs["draw"][0]),
            "away_win": float(probs["away_win"][0]),
        }

    def evaluate(self, df: pd.DataFrame) -> dict:
        """
        Evalúa el modelo en un conjunto de test.
        Retorna log_loss, accuracy, brier_score.
        """
        X = df[self.feature_names].values.astype(np.float32)
        y = _encode_target(df["target"])
        probs = self.model.predict_proba(X)
        y_pred = self.model.predict(X)

        # Brier score calculado solo sobre home_win para comparabilidad con ELO
        p_home = _decode_probs(probs, self.classes_)["home_win"]
        y_binary = (y == 2).astype(float)   # 2 = home win

        return {
            "log_loss":    float(log_loss(y, probs)),
            "accuracy":    float(accuracy_score(y, y_pred)),
            "brier_score": float(brier_score_loss(y_binary, p_home)),
            "n_samples":   len(X),
        }

    def feature_importance(self) -> pd.DataFrame:
        """
        Retorna los coeficientes del modelo por clase.
        Solo disponible si no hay calibración, o si el calibrador expone coefs.
        """
        clf = self.model.named_steps.get("clf")
        if hasattr(clf, "coef_"):
            coef_matrix = clf.coef_
        elif hasattr(clf, "estimator") and hasattr(clf.estimator, "coef_"):
            coef_matrix = clf.estimator.coef_
        else:
            logger.warning("Coeficientes no disponibles (modelo calibrado)")
            return pd.DataFrame()

        class_names = ["away_win", "draw", "home_win"]
        rows = []
        for cls_idx, cls_name in enumerate(class_names):
            if cls_idx < len(coef_matrix):
                for feat_idx, feat_name in enumerate(self.feature_names):
                    rows.append({
                        "class": cls_name,
                        "feature": feat_name,
                        "coefficient": coef_matrix[cls_idx, feat_idx],
                    })
        return pd.DataFrame(rows)

    def save(self, path: Optional[str] = None) -> str:
        path = path or str(MODEL_DIR / "logistic_model.pkl")
        with open(path, "wb") as f:
            pickle.dump(self, f)
        logger.info(f"Modelo guardado: {path}")
        return path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "LogisticMatchPredictor":
        path = path or str(MODEL_DIR / "logistic_model.pkl")
        with open(path, "rb") as f:
            model = pickle.load(f)
        logger.info(f"Modelo cargado: {path}")
        return model
