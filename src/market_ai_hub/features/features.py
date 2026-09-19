"""Feature engineering（spec §20 + V1 remediation：feature sanitation）。

核心紀律（spec §19 Data Leakage 防護）：
- 只使用「當時已知」資料計算 feature（rolling 全部 left-closed）
- 每個 feature 都有 available_at 概念 = 該 bar 的 timestamp_utc
- 禁止 future fill / look-ahead

V1 remediation（XGBoost inf/overflow 修復）：
- 所有比率型 feature 在分母為 0 / log(0) 時會產生 ±inf → 在 feature construction 層
  統一轉成 NaN（missing），不得留在 matrix 內送給 XGBoost/LightGBM（gradient_index.h crash）。
- training / inference 共用同一個 build_features，確保 preprocessing 一致。
- 不用任意數字 clipping；NaN 是 tree 模型原生 missing representation。
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


def _safe_pct(s: pd.Series) -> pd.Series:
    """pct_change 的 denominator=0 安全版：0 → NaN，避免 ±inf。"""
    return s.replace(0, np.nan).pct_change()


def _safe_log_return(close: pd.Series) -> pd.Series:
    """log return：close<=0 視為 missing，避免 -inf / log(0)。"""
    c = close.replace(0, np.nan)
    return np.log(c / c.shift(1))


def sanitize(df: pd.DataFrame) -> pd.DataFrame:
    """把 ±inf 統一轉 NaN。這是 V1 的 missing representation，training/inference 一致。"""
    return df.replace([np.inf, -np.inf], np.nan)


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

    out["returns"] = _safe_pct(close)
    out["log_returns"] = _safe_log_return(close)
    out["rolling_volatility"] = out["returns"].rolling(20).std()
    out["atr"] = _atr(high, low, close, 14)
    out["rsi"] = _rsi(close, 14)
    out["ema_10"] = close.ewm(span=10, adjust=False).mean()
    out["ema_20"] = close.ewm(span=20, adjust=False).mean()
    out["sma_20"] = close.rolling(20).mean()
    # denominator=0 安全：sma_20 為 0 時視為 missing（close 全 0 的股票沒有可算的距離）
    out["distance_from_ma20"] = close / out["sma_20"].replace(0, np.nan) - 1.0
    out["rolling_high_20"] = high.rolling(20).max()
    out["rolling_low_20"] = low.rolling(20).min()
    out["realized_volatility_20"] = out["log_returns"].rolling(20).std() * np.sqrt(252)
    out["volume_change"] = _safe_pct(volume)
    out["time_of_day"] = out["timestamp_utc"].dt.hour + out["timestamp_utc"].dt.minute / 60.0
    out["day_of_week"] = out["timestamp_utc"].dt.dayofweek

    # label：future return（僅供 training / backtest，feature 計算禁止使用）
    out["future_return_1"] = close.shift(-horizon_return_days) / close.replace(0, np.nan) - 1.0

    out = sanitize(out)
    return out


def future_return_k(df: pd.DataFrame, k: int) -> pd.Series:
    """k 根 bar 的 forward return（horizon=k 的 label）。k=1..10。"""
    close = df["close"].replace(0, np.nan)
    return close.shift(-k) / close - 1.0


def cross_market_features(market_df: pd.DataFrame) -> pd.DataFrame:
    """cross-market features（spec §20）：input 需含 symbol 欄位的多市場統一資料。"""
    feats = {}
    for sym, grp in market_df.groupby("symbol"):
        g = grp.sort_values("timestamp_utc")
        feats[f"{sym}_return"] = _safe_pct(g["close"]).rename(sym)
        if "volume" in g and g["volume"].notna().any():
            feats[f"{sym}_volume_change"] = _safe_pct(g["volume"]).rename(sym)
    wide = pd.DataFrame(feats, index=market_df.sort_values("timestamp_utc")["timestamp_utc"])
    return sanitize(wide)


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


def make_classification_labels(df: pd.DataFrame, threshold: float = 0.005, label_col: str = "future_return_1") -> np.ndarray:
    """分類 label（spec §8）：future_return > threshold → 1, < -threshold → -1, else 0。"""
    fr = df[label_col]
    return np.where(fr > threshold, 1, np.where(fr < -threshold, -1, 0)).astype(int)
