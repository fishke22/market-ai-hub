"""Feature engineering（spec §20）。

核心紀律（spec §19 Data Leakage 防護）：
- 只使用「當時已知」資料計算 feature（rolling 全部 left-closed）
- 每個 feature 都有 available_at 概念 = 該 bar 的 timestamp_utc
- 禁止 future fill / look-ahead
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 回傳 columns 順序固定，方便 feature_set hash
FEATURE_COLUMNS = [
    "returns",
    "log_returns",
    "rolling_volatility",
    "atr",
    "rsi",
    "ema_10",
    "ema_20",
    "sma_20",
    "distance_from_ma20",
    "rolling_high_20",
    "rolling_low_20",
    "realized_volatility_20",
    "volume_change",
    "time_of_day",
    "day_of_week",
    "future_return_1",
    "future_return_3",
]


def build_features(df: pd.DataFrame, horizon_return_days: int = 1) -> pd.DataFrame:
    """輸入統一 schema df（含 open/high/low/close/volume，按 timestamp_utc 排序）。

    回傳 features df + label：
      future_return_1 = close[t+1]/close[t] - 1 （當下可得性：label 只用於 training，預測時不得使用）
    """
    out = df.copy().reset_index(drop=True)
    close = out["close"]
    high = out["high"]
    low = out["low"]
    volume = out["volume"]

    out["returns"] = close.pct_change()
    out["log_returns"] = np.log(close / close.shift(1))
    out["rolling_volatility"] = out["returns"].rolling(20).std()
    out["atr"] = _atr(high, low, close, 14)
    out["rsi"] = _rsi(close, 14)
    out["ema_10"] = close.ewm(span=10, adjust=False).mean()
    out["ema_20"] = close.ewm(span=20, adjust=False).mean()
    out["sma_20"] = close.rolling(20).mean()
    out["distance_from_ma20"] = close / out["sma_20"] - 1.0
    out["rolling_high_20"] = high.rolling(20).max()
    out["rolling_low_20"] = low.rolling(20).min()
    out["realized_volatility_20"] = out["log_returns"].rolling(20).std() * np.sqrt(252)
    out["volume_change"] = volume.pct_change()
    out["time_of_day"] = out["timestamp_utc"].dt.hour + out["timestamp_utc"].dt.minute / 60.0
    out["day_of_week"] = out["timestamp_utc"].dt.dayofweek

    # label：future return（僅供 training / backtest，feature 計算禁止使用）
    out["future_return_1"] = close.shift(-horizon_return_days) / close - 1.0

    return out


def cross_market_features(market_df: pd.DataFrame) -> pd.DataFrame:
    """cross-market features（spec §20）：input 需含 symbol 欄位的多市場統一資料。"""
    feats = {}
    for sym, grp in market_df.groupby("symbol"):
        g = grp.sort_values("timestamp_utc")
        feats[f"{sym}_return"] = g["close"].pct_change().rename(sym)
        if "volume" in g and g["volume"].notna().any():
            feats[f"{sym}_volume_change"] = g["volume"].pct_change().rename(sym)
    wide = pd.DataFrame(feats, index=market_df.sort_values("timestamp_utc")["timestamp_utc"])
    # VIX 是 change 不是 return
    for c in wide.columns:
        if "VIX" in c:
            wide[c] = wide[c]  # 保留 change 語意（VIX 原值本身是波動率）
    return wide


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - 100 / (1 + rs)


def make_classification_labels(df: pd.DataFrame, threshold: float = 0.005) -> pd.Series:
    """分類 label（spec §8）：future_return > threshold → 1, < -threshold → -1, else 0。"""
    fr = df["future_return_1"]
    return np.where(fr > threshold, 1, np.where(fr < -threshold, -1, 0))
