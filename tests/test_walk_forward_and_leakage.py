"""Walk-forward split 與 no-future-leakage 測試。"""
import numpy as np
import pandas as pd
import pytest

from market_ai_hub.backtest.walk_forward import (
    compute_metrics,
    strategy_metrics,
    walk_forward_splits,
)
from market_ai_hub.features.features import build_features


def _series_df(n=300):
    ts = pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(100 + np.sin(np.arange(n) / 10) * 5 + np.arange(n) * 0.1)
    df = pd.DataFrame(
        {
            "timestamp_utc": ts, "timestamp_local": ts, "symbol": "X",
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": 1000.0, "provider": "t", "data_grade": "RESEARCH_PROXY",
        }
    )
    return df


def test_walk_forward_chronological():
    df = _series_df()
    splits = walk_forward_splits(df, n_splits=5, min_train=60)
    assert len(splits) == 5
    for sp in splits:
        # train 最後一筆時間 < test 第一筆時間（時間順序，無 overlap）
        assert sp.train.index[-1] < sp.test.index[0]
        assert len(sp.train) + len(sp.test) <= len(df)


def test_walk_forward_insufficient_data():
    df = _series_df(50)
    assert walk_forward_splits(df, n_splits=5, min_train=60) == []


def test_no_future_leakage_features():
    """feature 在 t 只能使用 <= t 的資料：把最後 k 列砍掉，前面 feature 不變。"""
    df = _series_df()
    feat_full = build_features(df)
    df_cut = df.iloc[:-20]
    feat_cut = build_features(df_cut)
    cols = ["returns", "log_returns", "atr", "rsi", "ema_10", "ema_20", "sma_20",
            "rolling_high_20", "rolling_low_20"]
    overlap = feat_full[cols].iloc[:-20].reset_index(drop=True)
    cut = feat_cut[cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(overlap, cut)


def test_future_return_is_label_only():
    """future_return_1 必須是 shift(-1)，不得用於特徵計算。"""
    df = _series_df(60)
    feat = build_features(df)
    fr = feat["future_return_1"]
    close = df["close"]
    expected = (close.shift(-1) / close - 1).reset_index(drop=True)
    assert np.allclose(fr.iloc[:-1], expected.iloc[:-1], equal_nan=True)
    assert np.isnan(fr.iloc[-1])


def test_compute_metrics_sane():
    actual = np.array([0.01, -0.01, 0.02, 0.0])
    pred = np.array([0.012, -0.008, 0.015, 0.0])
    m = compute_metrics(actual, pred, ["up", "down", "up", "flat"])
    assert 0 <= m["directional_accuracy"] <= 1
    assert m["mae"] >= 0 and m["rmse"] >= 0
    assert m["n_samples"] == 4


def test_strategy_metrics_use_real_realized_returns_not_label_proxy():
    realized = np.array([0.02, -0.03, 0.01])
    directions = ["up", "down", "flat"]
    m = strategy_metrics(realized, directions)

    # Gross strategy returns are +2%, +3%, 0%, not a fixed +/-0.5% proxy.
    assert m["average_return"] == pytest.approx((0.02 + 0.03) / 3)
    assert m["expectancy"] == pytest.approx(0.025)
    assert m["hit_rate"] == pytest.approx(1.0)
    assert m["profit_factor"] is None
    assert m["economic_metrics_status"] == "GROSS_REALIZED_RETURN_DIAGNOSTIC_NO_COSTS"
    assert m["transaction_costs_included"] is False
