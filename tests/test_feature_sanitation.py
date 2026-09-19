"""Feature sanitation + XGBoost 不崩潰測試（V1 remediation Phase 4）。"""
import numpy as np
import pandas as pd
import pytest


def _base_df(close, volume, n=100):
    ts = pd.date_range("2026-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({
        "timestamp_utc": ts, "timestamp_local": ts, "symbol": "X",
        "open": close, "high": np.asarray(close) + 1, "low": np.asarray(close) - 1,
        "close": close, "volume": volume, "provider": "t", "data_grade": "RESEARCH_PROXY",
    })


def _no_inf(feat):
    cols = ["returns", "log_returns", "rolling_volatility", "atr", "rsi", "ema_10", "ema_20",
            "sma_20", "distance_from_ma20", "rolling_high_20", "rolling_low_20",
            "realized_volatility_20", "volume_change", "time_of_day", "day_of_week"]
    assert not np.isinf(feat[cols].to_numpy()).any(), "features contain ±inf"


def test_zero_volume_no_inf():
    from market_ai_hub.features.features import build_features

    volume = pd.Series([0.0] * 50 + [1000.0] * 50)
    feat = build_features(_base_df(pd.Series(np.linspace(100, 120, 100)), volume))
    _no_inf(feat)


def test_zero_close_no_inf():
    from market_ai_hub.features.features import build_features

    close = pd.Series([100.0] * 40 + [0.0] + [100.0] * 59)
    feat = build_features(_base_df(close, pd.Series([1000.0] * 100)))
    _no_inf(feat)
    # log return 在 close=0 處應為 NaN（missing），不是 -inf
    assert pd.isna(feat["log_returns"].iloc[41]) or pd.isna(feat["log_returns"].iloc[40])


def test_extreme_return_and_large_finite():
    from market_ai_hub.features.features import build_features

    close = pd.Series(np.linspace(100, 200, 99).tolist() + [1e9])
    feat = build_features(_base_df(close, pd.Series([1000.0] * 100)))
    assert not np.isinf(feat[["returns", "log_returns"]].to_numpy()).any()


def test_missing_values_ok():
    from market_ai_hub.features.features import build_features

    close = pd.Series([100.0] * 90 + [np.nan] * 10)
    feat = build_features(_base_df(close, pd.Series([1000.0] * 100)))
    assert feat["close"].isna().any() or feat["returns"].isna().any()


def test_xgboost_fits_sanitized_matrix():
    """3706.TW 崩潰路徑重現：含 inf 的 feature 在 sanitation 後 XGBoost 必須能 fit/predict。"""
    from market_ai_hub.features.features import build_features
    from market_ai_hub.models.baseline_ml import FEATURE_INPUT, BaselineClassifier

    # 故意製造 0 成交量（產生 inf 來源）與 0 收盤
    volume = pd.Series([0.0] * 20 + [1000.0] * 80)
    close = pd.Series([100.0] * 30 + [0.0] * 5 + [110.0] * 65)
    feat = build_features(_base_df(close, volume))
    valid = feat[FEATURE_INPUT].notna().all(axis=1) & feat["future_return_1"].notna()
    X = feat.loc[valid, FEATURE_INPUT]
    assert not np.isinf(X.to_numpy()).any()
    y = (feat.loc[valid, "future_return_1"] > 0.005).astype(int) - (feat.loc[valid, "future_return_1"] < -0.005).astype(int)
    m = BaselineClassifier("xgb")
    m.fit(X.iloc[:-1], y.iloc[:-1].to_numpy())  # 不 raise = gradient_index.h 修復
    pred = m.predict(X.iloc[[-1]])
    assert len(pred) == 1
    m2 = BaselineClassifier("lgbm")
    m2.fit(X.iloc[:-1], y.iloc[:-1].to_numpy())
    assert len(m2.predict(X.iloc[[-1]])) == 1


def test_lr_rf_impute_missing():
    from market_ai_hub.features.features import build_features
    from market_ai_hub.models.baseline_ml import FEATURE_INPUT, BaselineClassifier

    close = pd.Series([100.0] * 30 + [0.0] * 5 + [110.0] * 65)
    feat = build_features(_base_df(close, pd.Series([0.0] * 20 + [1000.0] * 80)))
    valid = feat[FEATURE_INPUT].notna().all(axis=1) & feat["future_return_1"].notna()
    X = feat.loc[valid, FEATURE_INPUT]
    y = (feat.loc[valid, "future_return_1"] > 0.005).astype(int) - (feat.loc[valid, "future_return_1"] < -0.005).astype(int)
    for name in ("lr", "rf"):
        m = BaselineClassifier(name)
        m.fit(X.iloc[:-1], y.iloc[:-1].to_numpy())
        assert len(m.predict(X.iloc[[-1]])) == 1
