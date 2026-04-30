"""
Modelo XGBoost para predicción de partidos TRL.

Ventajas sobre regresión logística:
- Captura interacciones no lineales entre features
- Robusto a features correlacionados
- Importancia de features nativa

Trata el problema como clasificación multiclase (3 clases):
  0 = away win, 1 = draw, 2 = home win

Requiere: pip install xgboost
"""

import pickle
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

from sklearn.model_selection import cross_val_score, StratifiedKFold, RandomizedSearchCV
from sklearn.metrics import log_loss, accuracy_score, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV

from .feature_engineering import FEATURE_NAMES
from .logistic_model import _encode_target, _decode_probs

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent / "data" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


class XGBoostMatchPredictor:
    """
    Predictor basado en XGBoost con búsqueda de hiperparámetros y calibración.
    """

    DEFAULT_PARAMS = {
        "n_estimators":    300,
        "max_depth":       4,
        "learning_rate":   0.05,
        "subsample":       0.8,
        "colsample_bytree":0.8,
        "min_child_weight":3,
        "gamma":           0.1,
        "reg_alpha":       0.1,
        "reg_lambda":      1.0,
        "objective":       "multi:softprob",
        "num_class":       3,
        "eval_metric":     "mlogloss",
        "use_label_encoder": False,
        "random_state":    42,
        "n_jobs":          -1,
    }

    def __init__(self, params: Optional[dict] = None, calibrate: bool = True):
        if not XGB_AVAILABLE:
            raise ImportError(
                "xgboost no está instalado. Ejecutar: pip install xgboost"
            )
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}
        self.calibrate = calibrate
        self.model: Optional[xgb.XGBClassifier] = None
        self.classes_: Optional[np.ndarray] = None
        self.feature_names = FEATURE_NAMES
        self._trained = False

    def _build_model(self, params: dict) -> xgb.XGBClassifier:
        return xgb.XGBClassifier(**params)

    def train(
        self,
        df: pd.DataFrame,
        tune_hyperparams: bool = False,
        early_stopping_rounds: int = 30,
    ) -> dict:
        """
        Entrena el modelo XGBoost.

        Args:
            df: DataFrame con FEATURE_NAMES + 'target'
            tune_hyperparams: si True, hace búsqueda aleatoria de hiperparámetros
            early_stopping_rounds: parar si no mejora en N rondas

        Returns:
            dict con métricas de entrenamiento
        """
        X = df[self.feature_names].values.astype(np.float32)
        y = _encode_target(df["target"])

        logger.info(
            f"XGBoost: entrenando con {len(X)} muestras, "
            f"clases={np.unique(y, return_counts=True)}"
        )

        if tune_hyperparams:
            best_params = self._tune_hyperparams(X, y)
            self.params.update(best_params)
            logger.info(f"XGBoost: mejores params={best_params}")

        # Separar validación para early stopping
        from sklearn.model_selection import train_test_split
        X_tr, X_val, y_tr, y_val = train_test_split(
            X, y, test_size=0.15, random_state=42, stratify=y
        )

        self.model = self._build_model(self.params)

        fit_kwargs = {}
        if early_stopping_rounds > 0 and len(X_tr) > 20:
            fit_kwargs["eval_set"] = [(X_val, y_val)]
            fit_kwargs["verbose"] = False

        self.model.fit(X_tr, y_tr, **fit_kwargs)

        if self.calibrate:
            cv_cal = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
            calibrated = CalibratedClassifierCV(
                self.model, method="isotonic", cv=cv_cal
            )
            calibrated.fit(X, y)
            self.model = calibrated

        if hasattr(self.model, "classes_"):
            self.classes_ = self.model.classes_
        else:
            self.classes_ = np.array([0, 1, 2])

        self._trained = True

        probs = self.model.predict_proba(X)
        y_pred = self.model.predict(X)
        metrics = {
            "train_accuracy": float(accuracy_score(y, y_pred)),
            "train_log_loss": float(log_loss(y, probs)),
            "n_samples": len(X),
            "params": self.params,
        }
        logger.info(f"XGBoost metrics: {metrics}")
        return metrics

    def _tune_hyperparams(self, X: np.ndarray, y: np.ndarray) -> dict:
        """Búsqueda aleatoria de hiperparámetros con CV."""
        param_grid = {
            "n_estimators":     [100, 200, 300, 500],
            "max_depth":        [3, 4, 5, 6],
            "learning_rate":    [0.01, 0.03, 0.05, 0.1],
            "subsample":        [0.6, 0.7, 0.8, 0.9],
            "colsample_bytree": [0.6, 0.7, 0.8, 1.0],
            "min_child_weight": [1, 3, 5],
            "gamma":            [0, 0.1, 0.2],
        }
        base = xgb.XGBClassifier(
            objective="multi:softprob",
            num_class=3,
            eval_metric="mlogloss",
            use_label_encoder=False,
            random_state=42,
            n_jobs=-1,
        )
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        search = RandomizedSearchCV(
            base, param_grid,
            n_iter=30,
            scoring="neg_log_loss",
            cv=cv,
            random_state=42,
            n_jobs=-1,
            verbose=0,
        )
        search.fit(X, y)
        logger.info(
            f"Best CV log-loss: {-search.best_score_:.4f} | "
            f"params: {search.best_params_}"
        )
        return search.best_params_

    def predict_proba(self, X: np.ndarray) -> dict[str, np.ndarray]:
        if not self._trained or self.model is None:
            raise RuntimeError("Modelo no entrenado.")
        probs = self.model.predict_proba(X)
        return _decode_probs(probs, self.classes_)

    def predict_single(self, features: np.ndarray) -> dict[str, float]:
        probs = self.predict_proba(features.reshape(1, -1))
        return {
            "home_win": float(probs["home_win"][0]),
            "draw":     float(probs["draw"][0]),
            "away_win": float(probs["away_win"][0]),
        }

    def evaluate(self, df: pd.DataFrame) -> dict:
        X = df[self.feature_names].values.astype(np.float32)
        y = _encode_target(df["target"])
        probs = self.model.predict_proba(X)
        y_pred = self.model.predict(X)

        p_home = _decode_probs(probs, self.classes_)["home_win"]
        y_binary = (y == 2).astype(float)

        return {
            "log_loss":    float(log_loss(y, probs)),
            "accuracy":    float(accuracy_score(y, y_pred)),
            "brier_score": float(brier_score_loss(y_binary, p_home)),
            "n_samples":   len(X),
        }

    def feature_importance(self) -> pd.DataFrame:
        """Retorna importancia de features del modelo base XGBoost."""
        base = self.model
        # Si está calibrado, extraer el estimador base
        if hasattr(base, "estimator"):
            base = base.estimator
        if hasattr(base, "calibrated_classifiers_"):
            # CalibratedClassifierCV con cv='prefit' no expone base directamente
            logger.warning("Importancia de features no disponible para modelo calibrado con CV")
            return pd.DataFrame()

        if not hasattr(base, "feature_importances_"):
            return pd.DataFrame()

        return pd.DataFrame({
            "feature": self.feature_names,
            "importance": base.feature_importances_,
        }).sort_values("importance", ascending=False)

    def save(self, path: Optional[str] = None) -> str:
        path = path or str(MODEL_DIR / "xgboost_model.pkl")
        with open(path, "wb") as f:
            pickle.dump(self, f)
        logger.info(f"XGBoost guardado: {path}")
        return path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "XGBoostMatchPredictor":
        path = path or str(MODEL_DIR / "xgboost_model.pkl")
        with open(path, "rb") as f:
            model = pickle.load(f)
        return model
