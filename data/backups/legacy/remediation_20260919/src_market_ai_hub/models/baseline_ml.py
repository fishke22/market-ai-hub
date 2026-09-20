"""傳統 ML baseline（spec §8）：LogisticRegression / RandomForest / XGBoost / LightGBM。

任務：future_return 三分類（>threshold / <-threshold / flat）。
這些是 benchmark baseline，不是備胎；第一階段禁止宣稱 foundation model 一定較準。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from market_ai_hub.features.features import FEATURE_COLUMNS, make_classification_labels
from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput

log = logging.getLogger(__name__)

MODEL_NAME = {
    "lr": "logistic-regression",
    "rf": "random-forest",
    "xgb": "xgboost",
    "lgbm": "lightgbm",
}

# xgboost 不接受負 label（-1），需要 0/1/2 mapping
_NEEDS_NONNEG_LABEL = {"xgb"}

FEATURE_INPUT = [
    "returns", "log_returns", "rolling_volatility", "atr", "rsi",
    "ema_10", "ema_20", "sma_20", "distance_from_ma20",
    "rolling_high_20", "rolling_low_20", "realized_volatility_20",
    "volume_change", "time_of_day", "day_of_week",
]


def _new_model(name: str):
    if name == "lr":
        return LogisticRegression(max_iter=1000)
    if name == "rf":
        return RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=42)
    if name == "xgb":
        import xgboost as xgb

        return xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1, n_jobs=-1, random_state=42)
    if name == "lgbm":
        import lightgbm as lgb

        return lgb.LGBMClassifier(n_estimators=200, max_depth=4, learning_rate=0.1, n_jobs=-1, random_state=42, verbosity=-1)
    raise ValueError(f"unknown model {name}")


class BaselineClassifier:
    def __init__(self, name: str) -> None:
        self.name = name
        self.model = _new_model(name)
        self.fitted = False
        self._label_map: dict[int, int] | None = None

    def _encode(self, y: np.ndarray) -> np.ndarray:
        y = np.asarray(y)
        if self.name in _NEEDS_NONNEG_LABEL:
            uniq = np.unique(y)
            # 動態 0..k-1 編碼：訓練集少一個類別（如無 down）也能 fit
            self._label_map = {int(v): i for i, v in enumerate(sorted(uniq))}
            return np.vectorize(self._label_map.get)(y)
        return y

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> None:
        self.model.fit(X, self._encode(np.asarray(y)))
        self.fitted = True

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        pred = self.model.predict(X)
        if self._label_map is not None:
            rev = {v: k for k, v in self._label_map.items()}
            return np.vectorize(rev.get)(pred)
        return pred


def prepare_training_data(
    df: pd.DataFrame, threshold: float = 0.005
) -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame]:
    """從 features df 建立 training matrix（只保留無 NaN 的歷史列，最後一列供 inference）。"""
    feat_df = df[FEATURE_INPUT].copy()
    y = make_classification_labels(df, threshold)
    valid = feat_df.notna().all(axis=1) & (df["future_return_1"].notna())
    X_train = feat_df[valid].iloc[:-1]  # 最後一列 label 未知，留作預測
    y_train = np.asarray(y)[valid][:-1]
    X_last = feat_df.iloc[[-1]]
    return X_train, y_train, X_last


def baseline_forecast(
    model: BaselineClassifier,
    symbol: str,
    df: pd.DataFrame,
    horizon: str = "1d",
    data_grade: str = "RESEARCH_PROXY",
    threshold: float = 0.005,
) -> ForecastOutput:
    """用最後一列 features 預測方向機率，轉 ForecastOutput。

    方向 = argmax(up / flat / down)；quantiles 不適用於分類器，只給點估計與方向。
    """
    X_train, y_train, X_last = prepare_training_data(df, threshold)
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_last)[0]
    classes = list(model.model.classes_)
    if model._label_map is not None:
        rev = {v: k for k, v in model._label_map.items()}
        classes = [int(rev.get(c, c)) for c in classes]
    proba_map = {int(c): float(p) for c, p in zip(classes, proba)}
    up = proba_map.get(1, 0.0)
    down = proba_map.get(-1, 0.0)
    flat = proba_map.get(0, 0.0)
    direction = "up" if up > down and up > flat else ("down" if down > up and down > flat else "flat")
    last = float(df["close"].iloc[-1])
    drift = {"up": 1 + threshold, "flat": 1.0, "down": 1 - threshold}[direction]
    point = last * drift
    return ForecastOutput(
        model=MODEL_NAME[model.name],
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        horizon=horizon,
        point_forecast=point,
        expected_return=(point - last) / last,
        quantiles={"p10": last * (1 - threshold), "p50": point, "p90": last * (1 + threshold)},
        direction=direction,
        confidence=max(up, down, flat),
        data_grade=DataGrade(data_grade),
        warnings=["classifier baseline: quantiles are heuristic spreads, not model quantiles"],
    )
