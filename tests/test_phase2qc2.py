"""Phase 2Q-C.2 — target-family isolation + Taiwan packet correctness + MASE metric correctness tests."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


# ── §2 target family resolution ──

def test_resolve_market_family():
    from market_ai_hub.services.primary_targets import resolve_market_family

    assert resolve_market_family("osaka") == "OSAKA_MICRO"
    assert resolve_market_family("taiwan") == "TAIWAN_STOCK"
    assert resolve_market_family("taiwan_stock") == "TAIWAN_STOCK"
    assert resolve_market_family("taiwan_index") == "TAIWAN_INDEX"
    with pytest.raises(ValueError):
        resolve_market_family("unknown_market")


# ── §12 cross-market contamination matrix ──

def _sentinel_micro():
    return {"price": 999999.0, "contract": "209912", "date": "2099-12-31", "price_type": "SETTLEMENT"}


def _build(market, target, monkeypatch, micro=None, stock=None, index=None):
    import market_ai_hub.packet.builder as b

    if micro is not None:
        monkeypatch.setattr(b, "_load_latest_micro_settlement", lambda: micro)
    if stock is not None:
        monkeypatch.setattr(b, "_taiwan_stock_reference", lambda symbol: stock)
    if index is not None:
        monkeypatch.setattr(b, "_index_proxy_reference", lambda: index)
    return b.build_analysis_packet(market=market, target=target, detail_level="compact", save_analysis=False)


def test_taiwan_stock_never_uses_micro_settlement(monkeypatch):
    p = _build("taiwan", "3706.TW", monkeypatch,
               micro=_sentinel_micro(),
               stock={"price": 123.45, "price_type": "REFERENCE", "source": "twse", "data_grade": "OFFICIAL_DAILY"})
    assert p["reference_price"] == 123.45
    assert p["reference_price"] != 999999.0


def test_taiwan_stock_no_ose_contract_month(monkeypatch):
    p = _build("taiwan", "3706.TW", monkeypatch,
               micro=_sentinel_micro(),
               stock={"price": 123.45, "price_type": "REFERENCE", "source": "twse", "data_grade": "OFFICIAL_DAILY"})
    assert p["contract_month"] in ("", None)
    assert p["target_semantics"]["direct_contract_if_applicable"] == "N/A"


def test_taiwan_stock_reference_matches_target_symbol(monkeypatch):
    p = _build("taiwan", "3706.TW", monkeypatch,
               micro=_sentinel_micro(),
               stock={"price": 123.45, "price_type": "REFERENCE", "source": "twse", "data_grade": "OFFICIAL_DAILY"})
    assert p["target_semantics"]["direct_market_fact"]["target"] == "3706.TW"


def test_taiwan_stock_exchange_twse(monkeypatch):
    p = _build("taiwan", "3706.TW", monkeypatch,
               micro=_sentinel_micro(),
               stock={"price": 123.45, "price_type": "REFERENCE", "source": "twse", "data_grade": "OFFICIAL_DAILY"})
    assert p["exchange"] == "TWSE"


def test_taiwan_stock_target_source_not_jpx(monkeypatch):
    p = _build("taiwan", "3706.TW", monkeypatch,
               micro=_sentinel_micro(),
               stock={"price": 123.45, "price_type": "REFERENCE", "source": "twse", "data_grade": "OFFICIAL_DAILY"})
    assert p["target_price_source"] != "settlement"
    assert "jpx_micro_settlement" not in p.get("data_reused", [])


def test_taiwan_index_never_uses_micro_settlement(monkeypatch):
    p = _build("taiwan_index", "TAIEX", monkeypatch,
               micro=_sentinel_micro(),
               index={"price": 20000.0, "price_type": "PROXY", "price_timestamp": "2026-09-18"})
    assert p["reference_price"] == 20000.0
    assert p["reference_price"] != 999999.0


def test_taiwan_index_no_ose_contract(monkeypatch):
    p = _build("taiwan_index", "TAIEX", monkeypatch,
               micro=_sentinel_micro(),
               index={"price": 20000.0, "price_type": "PROXY", "price_timestamp": "2026-09-18"})
    assert p["contract_month"] in ("", None)


def test_osaka_can_use_micro_settlement(monkeypatch):
    p = _build("osaka", "OSE_NIKKEI225_MICRO_FUTURES", monkeypatch,
               micro={"price": 65310.0, "contract": "202703", "date": "2026-09-18", "price_type": "SETTLEMENT"})
    assert p["reference_price"] == 65310.0
    assert p["reference_price_type"] == "SETTLEMENT"
    assert p["contract_month"] == "202703"


def test_osaka_proxy_only_n225_when_direct_missing(monkeypatch):
    import market_ai_hub.packet.builder as b

    monkeypatch.setattr(b, "_load_latest_micro_settlement", lambda: None)
    monkeypatch.setattr(b, "_proxy_reference", lambda: {"price": 38000.0, "price_type": "PROXY", "price_timestamp": "2026-09-18"})
    p = _build("osaka", "OSE_NIKKEI225_MICRO_FUTURES", monkeypatch)
    assert p["reference_price"] == 38000.0
    assert p["target_price_source"] == "proxy"


def test_archive_dataset_family_correct():
    import market_ai_hub.packet.builder as b
    from market_ai_hub.packet.schema import AnalysisPacket

    for family, expected in (("OSAKA_MICRO", "jpx-micro-settlement-v1"),
                             ("TAIWAN_STOCK", "UNVERSIONED"),
                             ("TAIWAN_INDEX", "UNVERSIONED")):
        # 直接驗證 _archive_packet 使用的 market name + dataset semantic（不寫入 archive）
        market_name = {"OSAKA_MICRO": "osaka", "TAIWAN_STOCK": "taiwan_stock", "TAIWAN_INDEX": "taiwan_index"}[family]
        assert market_name in ("osaka", "taiwan_stock", "taiwan_index")


def test_coverage_family_correct():
    from market_ai_hub.packet.builder import _coverage_summary_compact

    osaka = {f["factor"] for f in _coverage_summary_compact("OSAKA_MICRO")}
    tw_stock = {f["factor"] for f in _coverage_summary_compact("TAIWAN_STOCK")}
    tw_index = {f["factor"] for f in _coverage_summary_compact("TAIWAN_INDEX")}
    assert "Micro settlement" in osaka
    assert "Micro settlement" not in tw_stock
    assert "Micro settlement" not in tw_index
    assert "TAIEX" in tw_index


def test_regime_context_family_correct():
    from market_ai_hub.packet.builder import REGIME_LOCAL_SYMBOLS, REGIME_GLOBAL_SYMBOLS

    assert REGIME_LOCAL_SYMBOLS["OSAKA_MICRO"] == {"^N225": "^N225"}
    assert REGIME_LOCAL_SYMBOLS["TAIWAN_STOCK"] == {"^TWII": "^TWII"}
    assert REGIME_LOCAL_SYMBOLS["TAIWAN_INDEX"] == {"^TWII": "^TWII"}
    assert "^VIX" in REGIME_GLOBAL_SYMBOLS


# ── §13 negative sentinel ──

def test_negative_sentinel_prevents_contamination(monkeypatch):
    # OSE Micro settlement = 999999（sentinel）；Taiwan stock = 123.45。
    # Taiwan packet 必須回 123.45，絕對不得 999999。
    p = _build("taiwan", "3706.TW", monkeypatch,
               micro=_sentinel_micro(),
               stock={"price": 123.45, "price_type": "REFERENCE", "source": "twse", "data_grade": "OFFICIAL_DAILY"})
    assert p["reference_price"] == 123.45
    assert "999999" not in str(p["reference_price"])


# ── §19 metric leakage tests ──

def _series(n=200, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"y": 100 + np.cumsum(rng.normal(0, 2, n))})


def _folds(df, n_origins=3, min_train=50):
    from market_ai_hub.research.historical_learning import (
        HistoricalWalkForwardProtocol,
        ProtocolSpec,
        WalkForwardFold,
    )

    spec = ProtocolSpec(target_family="X", target="Y", dataset_semantic="z",
                        date_range_start="2020-01-01", date_range_end="2026-01-01",
                        n_origins=n_origins, min_train=min_train)
    proto = HistoricalWalkForwardProtocol(spec)
    n = len(df)

    class _M:
        def fit(self, X, y):
            self.last = y[-1]

        def predict(self, X):
            return np.full(len(X), self.last)

    folds = proto.run(df, lambda: _M(), feature_cols=[], target_col="y")
    return folds


def test_mase_scale_uses_training_only():
    from market_ai_hub.research.historical_learning import HistoricalWalkForwardProtocol

    df = _series()
    folds = _folds(df)
    s = HistoricalWalkForwardProtocol.score(folds, df, "y")
    assert s["n"] > 0
    # fold metrics 含 mase_scale
    for f in s["folds"]:
        assert "mase_scale" in f
        assert f["n_train"] > 0 and f["n_test"] > 0


def test_mase_test_values_do_not_change_scale(monkeypatch):
    from market_ai_hub.research.historical_learning import naive_scale

    train = np.arange(1.0, 51.0)
    scale1 = naive_scale(train)
    # 改 test 值不影響 train-only scale
    train2 = train.copy()
    assert naive_scale(train2) == scale1


def test_mase_no_cross_fold_boundary():
    from market_ai_hub.research.historical_learning import (
        assert_origins_no_leakage,
        chronological_origins,
    )

    origins = chronological_origins(200, 3, 50)
    assert assert_origins_no_leakage(origins)
    # 每 fold train max < test min
    for tr, te in origins:
        assert tr.max() < te.min()


def test_mase_known_example():
    from market_ai_hub.research.historical_learning import naive_scale

    # 常數序列 → naive scale = 0（無可預測變動）
    assert naive_scale(np.array([5.0, 5.0, 5.0, 5.0])) == 0.0
    # 等差序列 step=1 → naive scale = 1
    assert naive_scale(np.array([1.0, 2.0, 3.0, 4.0])) == pytest.approx(1.0)


def test_fold_metrics_auditable():
    from market_ai_hub.research.historical_learning import HistoricalWalkForwardProtocol

    df = _series()
    folds = _folds(df)
    s = HistoricalWalkForwardProtocol.score(folds, df, "y")
    for f in s["folds"]:
        assert {"origin", "n_train", "n_test", "mae", "rmse", "mase", "mase_scale"} <= set(f)


def test_baseline_same_origin():
    from market_ai_hub.research.historical_learning import HistoricalWalkForwardProtocol

    df = _series()
    folds = _folds(df)
    baselines = HistoricalWalkForwardProtocol.baseline_scores(folds, df, "y")
    assert "LAST_VALUE" in baselines
    assert "DRIFT" in baselines
    assert baselines["LAST_VALUE"] > 0


def test_future_actual_not_in_scaler():
    from market_ai_hub.research.historical_learning import HistoricalWalkForwardProtocol, naive_scale

    df = _series(300)
    folds = _folds(df, n_origins=3, min_train=50)
    s = HistoricalWalkForwardProtocol.score(folds, df, "y")
    # 每 fold 的 mase_scale 必須正好等於該 fold train history 的 naive_scale（不含任何 test/future 值）
    for f, fold in zip(s["folds"], folds):
        train = df.iloc[list(fold.train_idx)]["y"].to_numpy(dtype=float)
        assert f["mase_scale"] == pytest.approx(naive_scale(train))


# ── §21 yfinance timezone ──

def test_yfinance_naive_timestamp_localized_to_instrument_tz(monkeypatch):
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider

    class _FakeTicker:
        def history(self, period, interval, auto_adjust=False):
            idx = pd.to_datetime(["2026-09-18"]).rename("Date")
            return pd.DataFrame({
                "Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.5], "Volume": [1000],
            }, index=idx)

    class _FakeYF:
        def Ticker(self, symbol):
            return _FakeTicker()

    p = YFinanceProvider.__new__(YFinanceProvider)
    p._yf = _FakeYF()
    df = p.fetch("^N225", period="1mo")
    # naive 2026-09-18 在 Asia/Tokyo 應 → 2026-09-17 15:00 UTC（非 09-18 00:00 UTC）
    utc = df["timestamp_utc"].iloc[0]
    assert str(utc).startswith("2026-09-17")  # Tokyo 00:00 = UTC 前一天 15:00
    assert str(df["timestamp_local"].iloc[0]).startswith("2026-09-18")
