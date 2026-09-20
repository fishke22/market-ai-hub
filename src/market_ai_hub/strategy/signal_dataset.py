"""Phase 2F — point-in-time correct historical signal dataset（B）。

每列只含「當時真的已知」的資料。forward return 是 label（未來價格），
不是 feature；feature（regime / forecast）只用 decision_time 之前已知者。
禁止 future leakage：regime 用 backward asof join，未來 regime 不得用於過去決策。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

FORWARD_HORIZONS = (1, 2, 5, 10)


def forward_returns(closes: pd.Series, decision_time, horizons: tuple = FORWARD_HORIZONS) -> dict[str, float | None]:
    """closes：target close series（tz-aware index 升冪）。回傳各 horizon 的 forward return。

    h 表「h 根 bar 之後」。資料不足 → None（不偽造）。
    """
    closes = closes.sort_index()
    t = pd.Timestamp(decision_time)
    hist = closes[closes.index <= t]
    if hist.empty:
        return {f"fwd_{h}d": None for h in horizons}
    entry = float(hist.iloc[-1])
    fut = closes[closes.index > t]
    out: dict[str, float | None] = {}
    for h in horizons:
        if len(fut) >= h:
            out[f"fwd_{h}d"] = float(fut.iloc[h - 1] / entry - 1.0)
        else:
            out[f"fwd_{h}d"] = None
    return out


def build_signal_dataset(closes: pd.Series, forecasts: list[dict[str, Any]],
                         regime_df: pd.DataFrame | None = None,
                         horizons: tuple = FORWARD_HORIZONS) -> pd.DataFrame:
    """由 forecasts + target close +（point-in-time）regime 建立信號資料集。

    forecasts: list of {information_cutoff, forecast_id, model_name, horizon,
                        direction, point_forecast, origin_price}
    regime_df: index=datetime（point-in-time，每列為該時點已知 regime），
               columns=regime feature names。用 backward asof join（no look-ahead）。
    """
    rows: list[dict] = []
    for f in forecasts:
        t = pd.Timestamp(f["information_cutoff"])
        hist = closes[closes.index <= t]
        if hist.empty:
            continue
        entry = float(hist.iloc[-1])
        origin = f.get("origin_price") or entry
        strength = None
        if f.get("point_forecast") is not None and origin:
            strength = float(f["point_forecast"] / origin - 1.0)
        row = {
            "decision_time": t,
            "forecast_id": f.get("forecast_id"),
            "model_name": f.get("model_name"),
            "horizon": f.get("horizon"),
            "direction": f.get("direction"),
            "forecast_strength": strength,
        }
        row.update(forward_returns(closes, t, horizons))
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["decision_time", "forecast_id", "model_name", "horizon",
                                   "direction", "forecast_strength"] + [f"fwd_{h}d" for h in horizons])
    if regime_df is not None and not regime_df.empty and "decision_time" in df.columns:
        df = _asof_join_regime(df, regime_df)
    return df


def _asof_join_regime(df: pd.DataFrame, regime_df: pd.DataFrame) -> pd.DataFrame:
    """backward asof join：decision_time 只取 <= 自身的最近 regime（不洩漏未來）。"""
    regime_df = regime_df.copy().sort_index()
    df = df.sort_values("decision_time").reset_index(drop=True)
    left = df[["decision_time"]].assign(_order=np.arange(len(df)))
    right = regime_df.reset_index()
    time_col = right.columns[0]
    merged = pd.merge_asof(left, right.sort_values(time_col),
                           left_on="decision_time", right_on=time_col, direction="backward")
    merged = merged.sort_values("_order").reset_index(drop=True)
    regime_cols = [c for c in regime_df.columns]
    return pd.concat([df, merged[regime_cols]], axis=1)
