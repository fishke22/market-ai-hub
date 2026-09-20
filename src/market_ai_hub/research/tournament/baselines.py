"""Phase 2D — Baselines（naive + statistical）。Tournament 永遠保留這些 baseline。

- naive price：Last Price Naive / Random Walk / Drift / Moving Average / Seasonal Naive
- direction：Majority Class / Always Flat
- statistical（statsmodels/sklearn）：Ridge / VAR / Dynamic Factor / Kalman(local level)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from market_ai_hub.research.tournament.adapter import ForecastResult, ModelAdapter


def _closes(df: pd.DataFrame) -> pd.Series:
    return df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna()


def _direction(point: float, last: float) -> str:
    return "up" if point > last else ("down" if point < last else "flat")


class _PointBaseline(ModelAdapter):
    task = "price"

    def _point(self, closes: pd.Series, steps: int) -> float:
        raise NotImplementedError

    def forecast(self, df, steps):
        closes = _closes(df)
        point = self._point(closes, steps)
        return ForecastResult(point=point, direction=_direction(point, closes.iloc[-1]),
                              quantile_valid=None, warnings=["baseline: point only"])


class LastPriceNaive(_PointBaseline):
    name = "last_price_naive"

    def _point(self, closes, steps):
        return float(closes.iloc[-1])


class RandomWalk(_PointBaseline):
    name = "random_walk"

    def _point(self, closes, steps):
        rets = closes.pct_change().dropna()
        rng = np.random.default_rng(42)
        shock = float(rng.choice(rets.to_numpy())) if len(rets) else 0.0
        return float(closes.iloc[-1] * (1 + shock))


class Drift(_PointBaseline):
    name = "drift"

    def _point(self, closes, steps):
        d = float(closes.pct_change().dropna().mean()) if len(closes) > 1 else 0.0
        return float(closes.iloc[-1] * (1 + d) ** steps)


class MovingAverage(_PointBaseline):
    name = "moving_average"

    def _point(self, closes, steps):
        ma = closes.rolling(20).mean().iloc[-1]
        return float(closes.iloc[-1]) if pd.isna(ma) else float(ma)


class SeasonalNaive(_PointBaseline):
    name = "seasonal_naive"

    def _point(self, closes, steps):
        lag = 5  # 週級季節性（daily）
        if len(closes) <= lag:
            return float(closes.iloc[-1])
        return float(closes.iloc[-lag])


class _DirectionBaseline(ModelAdapter):
    task = "direction"

    def _label(self, closes: pd.Series, steps: int) -> int:
        raise NotImplementedError

    def forecast(self, df, steps):
        closes = _closes(df)
        label = self._label(closes, steps)
        return ForecastResult(class_label=label,
                              direction="up" if label == 1 else ("down" if label == -1 else "flat"),
                              point=None, probability_calibrated=False)


class MajorityClass(_DirectionBaseline):
    name = "majority_class"

    def _label(self, closes, steps):
        rets = closes.pct_change().dropna()
        if len(rets) == 0:
            return 0
        y = np.where(rets > 0.005, 1, np.where(rets < -0.005, -1, 0))
        return int(np.bincount(y + 1).argmax() - 1)  # 多數類


class AlwaysFlat(_DirectionBaseline):
    name = "always_flat"

    def _label(self, closes, steps):
        return 0


class _StatsPoint(ModelAdapter):
    task = "price"

    def _fit_forecast(self, closes: pd.Series, steps: int) -> float | None:
        raise NotImplementedError

    def forecast(self, df, steps):
        # statsmodels 對無 freq 的 DatetimeIndex forecast 會 ValueError → 用整數 index
        closes = _closes(df).reset_index(drop=True)
        try:
            point = self._fit_forecast(closes, steps)
        except Exception as e:
            return ForecastResult(point=None, direction="", warnings=[f"{self.name} failed: {type(e).__name__}"])
        if point is None:
            return ForecastResult(point=None, direction="", warnings=[f"{self.name} insufficient data"])
        return ForecastResult(point=float(point), direction=_direction(float(point), closes.iloc[-1]),
                              quantile_valid=None, warnings=["statistical baseline: point only"])


class RidgeBaseline(_StatsPoint):
    name = "ridge"

    def _fit_forecast(self, closes, steps):
        from sklearn.linear_model import Ridge

        if len(closes) < 30:
            return None
        p = 5
        y = closes.iloc[p:].to_numpy()
        X = np.column_stack([closes.shift(i).iloc[p:].to_numpy() for i in range(1, p + 1)])
        m = Ridge(alpha=1.0).fit(X, y)
        cur = closes.iloc[-p:].to_numpy()[::-1]  # 最近 p 個
        point = float(closes.iloc[-1])
        for _ in range(steps):
            nxt = m.predict(cur.reshape(1, -1))[0]
            cur = np.concatenate([[nxt], cur[:-1]])
        return cur[0]


class VARBaseline(_StatsPoint):
    name = "var"

    def _fit_forecast(self, closes, steps):
        from statsmodels.tsa.api import VAR

        if len(closes) < 30:
            return None
        data = pd.DataFrame({"close": closes, "ret": closes.diff().fillna(0.0)})
        res = VAR(data).fit(maxlags=1)
        fc = res.forecast(data.values, steps=steps)
        return fc[-1, 0]


class DFMBaseline(_StatsPoint):
    name = "dynamic_factor"

    def _fit_forecast(self, closes, steps):
        from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor

        if len(closes) < 30:
            return None
        data = pd.DataFrame({"close": closes, "ret": closes.diff().fillna(0.0)})
        mod = DynamicFactor(data, k_factors=1, factor_order=1)
        res = mod.fit(disp=False, maxiter=50)
        fc = res.forecast(steps)
        return float(np.asarray(fc)[-1, 0])


class KalmanBaseline(_StatsPoint):
    name = "kalman_local_level"

    def _fit_forecast(self, closes, steps):
        from statsmodels.tsa.statespace.structural import UnobservedComponents

        if len(closes) < 30:
            return None
        mod = UnobservedComponents(closes, "local level")
        res = mod.fit(disp=False)
        fc = res.forecast(steps)
        return float(np.asarray(fc)[-1])


PRICE_BASELINES = [LastPriceNaive, RandomWalk, Drift, MovingAverage, SeasonalNaive]
DIRECTION_BASELINES = [MajorityClass, AlwaysFlat]
STATISTICAL_BASELINES = [RidgeBaseline, VARBaseline, DFMBaseline, KalmanBaseline]


def all_baseline_adapters() -> list[ModelAdapter]:
    return [c() for c in PRICE_BASELINES + DIRECTION_BASELINES + STATISTICAL_BASELINES]
