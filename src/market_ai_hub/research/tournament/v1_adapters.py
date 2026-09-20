"""Phase 2D — V1 模型與 FinCast 的 Tournament Adapter（包裝既有模型，不改 V1 核心）。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from market_ai_hub.research.tournament.adapter import ForecastResult, ModelAdapter


def _closes(df: pd.DataFrame) -> pd.Series:
    return df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna()


class ChronosAdapter(ModelAdapter):
    name = "chronos-2"
    task = "price"
    revision = "29ec3766d36d6f73f0696f85560a422f50e8498c"

    def forecast(self, df, steps):
        from market_ai_hub.models.chronos_model import ChronosAdapter as C

        closes = _closes(df)
        r = C().predict(closes, horizon=steps)
        path = r["path"]
        p10, p50, p90 = path["p10"][-1], path["p50"][-1], path["p90"][-1]
        direction = "up" if p50 > closes.iloc[-1] else ("down" if p50 < closes.iloc[-1] else "flat")
        return ForecastResult(point=p50, p10=p10, p50=p50, p90=p90,
                              forecast_path=path["p50"], quantile_valid=(p10 <= p50 <= p90),
                              direction=direction)


class TimesFMAdapter(ModelAdapter):
    name = "timesfm-3.0"
    task = "price"
    revision = "43046b85ec22d584a13f8098c2ed39c889e129c2"

    def forecast(self, df, steps):
        from market_ai_hub.models.timesfm_model import TimesFM3Adapter as T

        closes = _closes(df)
        r = T().predict(closes, horizon=steps)
        path = r["path"]
        p10, p50, p90 = path["p10"][-1], path["p50"][-1], path["p90"][-1]
        direction = "up" if p50 > closes.iloc[-1] else ("down" if p50 < closes.iloc[-1] else "flat")
        return ForecastResult(point=p50, p10=p10, p50=p50, p90=p90,
                              forecast_path=path["p50"], quantile_valid=(p10 <= p50 <= p90),
                              direction=direction,
                              warnings=["TIMESFM3_NON_COMMERCIAL_ONLY"])


class FinCastAdapter(ModelAdapter):
    name = "fincast"
    task = "price"
    revision = "2d7d90b159db8961d27c2cf165d51195902ef92b"

    def forecast(self, df, steps):
        from market_ai_hub.models.fincast_model import FinCastAdapter as F

        closes = _closes(df)
        r = F().predict(closes, horizon=steps)
        point = float(np.mean(r["point"]))
        direction = "up" if point > closes.iloc[-1] else ("down" if point < closes.iloc[-1] else "flat")
        return ForecastResult(point=point, direction=direction, quantile_valid=None,
                              warnings=["fincast bridge: point only, no predictive quantiles"])


class _ClassifierAdapter(ModelAdapter):
    task = "direction"
    _name = "classifier"
    _classifier_key = "xgb"  # BaselineClassifier 的 key（xgb/lgbm/lr/rf）

    def __init__(self) -> None:
        self.name = self._name
        self.revision = ""

    def forecast(self, df, steps):
        from market_ai_hub.features.features import build_features, future_return_k
        from market_ai_hub.models.baseline_ml import FEATURE_INPUT, BaselineClassifier

        feat = build_features(df)
        X = feat[FEATURE_INPUT]
        y = future_return_k(feat, steps)
        valid = X.notna().all(axis=1) & y.notna()
        X, y = X[valid].iloc[:-steps], y[valid][:-steps]
        y_cls = np.where(y > 0.005, 1, np.where(y < -0.005, -1, 0)).astype(int)
        if len(np.unique(y_cls)) < 2:
            return ForecastResult(direction="", class_label=None, point=None,
                                  warnings=["training labels single class"])
        m = BaselineClassifier(self._classifier_key)
        m.fit(X, y_cls)
        pred = int(m.predict(X.iloc[[-1]])[0])
        direction = "up" if pred == 1 else ("down" if pred == -1 else "flat")
        return ForecastResult(direction=direction, class_label=pred, point=None,
                              probability_calibrated=False,
                              calibration_metadata={"method": "none"})


class XGBoostAdapter(_ClassifierAdapter):
    _name = "xgboost"
    _classifier_key = "xgb"
    revision = "3.4.1"


class LightGBMAdapter(_ClassifierAdapter):
    _name = "lightgbm"
    _classifier_key = "lgbm"
    revision = "4.7.0"


PRICE_ADAPTERS = [ChronosAdapter, TimesFMAdapter, FinCastAdapter]
DIRECTION_ADAPTERS = [XGBoostAdapter, LightGBMAdapter]
