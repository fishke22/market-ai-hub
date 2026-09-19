"""傳統 ML baseline（spec §8 + V1 remediation）。

任務：k-bar future return 三分類（>threshold / flat / <-threshold），k = horizon steps。
- flat threshold：固定 0.005（0.5%），作用於 k-bar 累積報酬。於 model_metadata 揭露。
- 分類器不給價格：point_forecast 用「訓練窗內各 class 的實證平均報酬」映射，
  不再用 threshold 假裝 drift。quantiles 為標註 heuristic 的 spread（非模型 quantile）。
- 分類模型 class metadata：task_type / classes / flat_threshold / class_distribution /
  uniform_random_baseline_accuracy / majority_class_baseline_accuracy。
- V1 remediation：XGBoost 不再因 ±inf 崩潰（feature sanitation 在 build_features 完成，
  分類器接收 NaN=missing；XGBoost/LightGBM 原生處理 missing）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression

from market_ai_hub.features.features import FEATURE_COLUMNS, future_return_k
from market_ai_hub.schemas.market_data import (
    DataGrade,
    EngineeringStatus,
    ForecastOutput,
    ModelRole,
    ModelTask,
    PredictiveValidationStatus,
    QuantileType,
)
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.horizon import (
    HorizonSpec,
    HorizonUnsupportedError,
    parse_horizon,
)

log = logging.getLogger(__name__)

MODEL_NAME = {
    "lr": "logistic-regression",
    "rf": "random-forest",
    "xgb": "xgboost",
    "lgbm": "lightgbm",
}

# xgboost 不接受負 label（-1），需要非負 mapping
_NEEDS_NONNEG_LABEL = {"xgb"}
# sklearn 線性/樹模型不支援 NaN → 用 median imputation（fit 時學習，inference 沿用）
_NEEDS_IMPUTATION = {"lr", "rf"}

FEATURE_INPUT = [
    "returns", "log_returns", "rolling_volatility", "atr", "rsi",
    "ema_10", "ema_20", "sma_20", "distance_from_ma20",
    "rolling_high_20", "rolling_low_20", "realized_volatility_20",
    "volume_change", "time_of_day", "day_of_week",
]

FLAT_THRESHOLD = 0.005
CLASSES = [-1, 0, 1]


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
        self._imputer: SimpleImputer | None = None

    def _encode(self, y: np.ndarray) -> np.ndarray:
        y = np.asarray(y)
        if self.name in _NEEDS_NONNEG_LABEL:
            uniq = np.unique(y)
            # 動態 0..k-1 編碼：訓練集少一個類別（如無 down）也能 fit
            self._label_map = {int(v): i for i, v in enumerate(sorted(uniq))}
            return np.vectorize(self._label_map.get)(y)
        return y

    def _prep_x(self, X: pd.DataFrame, fit_imputer: bool) -> pd.DataFrame:
        if self.name not in _NEEDS_IMPUTATION:
            return X
        if fit_imputer:
            self._imputer = SimpleImputer(strategy="median")
            return pd.DataFrame(self._imputer.fit_transform(X), columns=X.columns, index=X.index)
        if self._imputer is None:
            raise RuntimeError("imputer not fitted")
        return pd.DataFrame(self._imputer.transform(X), columns=X.columns, index=X.index)

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> None:
        self.model.fit(self._prep_x(X, fit_imputer=True), self._encode(np.asarray(y)))
        self.fitted = True

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(self._prep_x(X, fit_imputer=False))

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        pred = self.model.predict(self._prep_x(X, fit_imputer=False))
        if self._label_map is not None:
            rev = {v: k for k, v in self._label_map.items()}
            return np.vectorize(rev.get)(pred)
        return pred


def _class_distribution(y: np.ndarray) -> dict:
    counts = {int(c): int((np.asarray(y) == c).sum()) for c in CLASSES}
    total = sum(counts.values()) or 1
    return {str(k): v for k, v in counts.items()}, {str(k): round(v / total, 4) for k, v in counts.items()}


def prepare_training_data(
    df: pd.DataFrame,
    threshold: float = FLAT_THRESHOLD,
    horizon_steps: int = 1,
) -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame]:
    """建立 k-bar horizon 的 training matrix。

    - features：sanitized（build_features 產出，±inf 已轉 NaN）
    - label：future_return_k（k-bar forward return 三分類）
    - X_last：最後一列 features（inference 用，label 未知）
    """
    feat_df = df[FEATURE_INPUT].copy()
    fr = future_return_k(df, horizon_steps)
    valid = feat_df.notna().all(axis=1) & fr.notna()
    X_train = feat_df[valid].iloc[:-horizon_steps]  # 最後 k 列 label 未知，留作預測窗口
    y = np.where(fr > threshold, 1, np.where(fr < -threshold, -1, 0)).astype(int)
    y_train = y[valid][:-horizon_steps]
    X_last = feat_df.iloc[[-1]]
    return X_train, y_train, X_last


def baseline_forecast(
    model: BaselineClassifier,
    symbol: str,
    df: pd.DataFrame,
    horizon: str = "1d",
    data_grade: str = "RESEARCH_PROXY",
    threshold: float = FLAT_THRESHOLD,
    data_frequency: str = "1d",
) -> ForecastOutput:
    """分類器方向預測 → 統一 ForecastOutput。

    horizon "Nd" → label 用 k=N bar forward return。日內 horizon → UNSUPPORTED。
    """
    spec: HorizonSpec = parse_horizon(horizon, data_frequency)
    if not spec.supported:
        raise HorizonUnsupportedError(spec.reason)
    steps = spec.effective_horizon_steps

    X_train, y_train, X_last = prepare_training_data(df, threshold, steps)
    if len(np.unique(y_train)) < 2:
        raise RuntimeError("training labels contain only one class; cannot fit classifier")
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

    # 實證 class mean return（訓練窗，k-bar 報酬），做 point forecast 映射
    fr_train = future_return_k(df, steps).iloc[: len(X_train)]
    fr_train = fr_train.reset_index(drop=True)
    y_train_aligned = pd.Series(y_train).reset_index(drop=True)
    class_mean = {}
    for c in CLASSES:
        mask = y_train_aligned == c
        vals = fr_train[mask].dropna()
        class_mean[c] = float(vals.mean()) if len(vals) else 0.0
    mean_ret = class_mean[{"up": 1, "flat": 0, "down": -1}[direction]]
    point = last * (1 + mean_ret)

    counts, dist = _class_distribution(y_train)
    uniform_base = round(1 / 3, 4)
    majority_base = max(dist.values()) if dist else None

    # quantile contract：分類器沒有 predictive quantile → NOT_AVAILABLE，
    # heuristic spread 改用 lower_reference / upper_reference（不得假冒 p10/p90）
    lower_ref = last * (1 + class_mean[-1])
    upper_ref = last * (1 + class_mean[1])
    class_probs = {f"class_{int(c)}": float(proba_map.get(c, 0.0)) for c in CLASSES}

    # V1.2 temporal anchor（分類器的 k-bar horizon 同樣指向未來 sessions）
    anchor = _classifier_anchor(symbol, df, steps)

    fo = ForecastOutput(
        model=MODEL_NAME[model.name],
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        horizon=horizon,
        point_forecast=point,
        expected_return=mean_ret,
        quantiles={"p10": None, "p50": None, "p90": None},
        direction=direction,
        confidence=max(up, down, flat),
        data_grade=DataGrade(data_grade),
        requested_horizon=horizon,
        effective_horizon_steps=steps,
        data_frequency=data_frequency,
        horizon_applied=True,
        forecast_path=[],  # 分類器無多步路徑
        forecast_dates=anchor["forecast_target_dates"],
        terminal_forecast=point,
        model_role=ModelRole.BASE_MODEL.value,
        engineering_status=EngineeringStatus.PASS.value,
        predictive_validation_status=PredictiveValidationStatus.UNVALIDATED.value,
        eligible_for_price_reference=False,
        eligible_for_direction_vote=False,  # 需 OOS 超越 baseline 才為 true（見 model_catalog）
        eligible_for_ensemble_weighting=True,
        model_task=ModelTask.DIRECTION_CLASSIFICATION.value,
        quantile_type=QuantileType.NOT_AVAILABLE.value,
        quantile_valid=None,
        class_probabilities=class_probs,
        class_probabilities_calibrated=False,  # tree ensemble 原生 proba 未經 calibration
        lower_reference=lower_ref,
        upper_reference=upper_ref,
        target_calendar=anchor["target_calendar"],
        target_trading_dates=anchor["forecast_target_dates"],
        calendar_grade=anchor["calendar_grade"],
        forecast_origin=anchor["forecast_origin"],
        last_observed_trading_date=anchor["last_observed_trading_date"],
        forecast_target_dates=anchor["forecast_target_dates"],
        exchange_timezone=anchor["exchange_timezone"],
        calendar_name=anchor["calendar_name"],
        calendar_source=anchor["calendar_source"],
        calendar_verified=anchor["calendar_verified"],
        calendar_last_verified=anchor["calendar_last_verified"],
        probability_available=True,
        probability_calibrated=False,
        calibration_method="none",
        calibration_sample_size=None,
        calibration_metrics={"brier_score": None, "ece": None},
        model_metadata={
            "task_type": "classification",
            "classes": CLASSES,
            "flat_threshold": threshold,
            "class_distribution": dist,
            "class_counts": counts,
            "uniform_random_baseline_accuracy": uniform_base,
            "majority_class_baseline_accuracy": majority_base,
            "label_horizon_steps": steps,
            "point_estimate_method": "empirical class mean return (training window)",
        },
        warnings=[
            "classifier baseline: quantile_type=NOT_AVAILABLE; lower/upper_reference are heuristic spreads, not predictive quantiles",
            "class probabilities are raw tree-ensemble outputs, NOT calibrated (calibration_method=none)",
        ],
    )
    return fo.attach_build(build_fingerprint())


def _classifier_anchor(symbol: str, df: pd.DataFrame, steps: int) -> dict:
    """分類器的 temporal anchor：最後一根 bar 的 trading_date + 未來 sessions。"""
    from market_ai_hub.services.calendar import forecast_anchor

    last_ts = df["timestamp_utc"].iloc[-1]
    return forecast_anchor(symbol, last_ts, steps)
