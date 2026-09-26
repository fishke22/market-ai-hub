"""Phase 2C tests：feature store no-lookahead / timestamp / available_at /
regime reproducibility / no-lookahead / insufficient sample / event stale。"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from market_ai_hub.feature_store.panel import PANEL, PANEL_SYMBOLS, EVENT_SCHEDULE_FEATURES
from market_ai_hub.feature_store.store import FeatureRecord, FeatureStore, build_panel_features
from market_ai_hub.regime.engine import MarketRegimeEngine
from market_ai_hub.regime.events import EventEngine, event_phase
from market_ai_hub.regime.protection import RegimeProtection, shrinkage, wilson_ci


def test_trend_does_not_invent_confidence_interval():
    result = MarketRegimeEngine().compute(_panel())["trend_regime"]
    assert result.get("confidence_interval") is None
    assert result["confidence_status"] == "NOT_ESTIMATED"


# ── Feature Store ──

def _closes(symbol, n=30, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-09-01", periods=n, freq="B", tz="UTC")
    return pd.Series(100 + rng.normal(0, 1, n).cumsum(), index=idx)


def test_panel_has_16_symbols():
    assert len(PANEL_SYMBOLS) == 16
    assert "^N225" in PANEL_SYMBOLS and "US10Y" in PANEL_SYMBOLS and "BTC-USD" in PANEL_SYMBOLS


def test_event_schedule_features_present():
    names = {e["name"] for e in EVENT_SCHEDULE_FEATURES}
    assert {"boj_schedule", "fomc_schedule", "cpi", "nfp", "holiday", "ose_holiday_session", "contract_expiry"} <= names


def test_feature_record_aware_timestamps():
    rec = FeatureRecord(feature_name="close", symbol="^N225",
                        event_time=datetime(2026, 9, 18), available_at=datetime(2026, 9, 18),
                        feature_version="v1", source="panel", data_grade="RESEARCH_PROXY", value=100.0)
    assert rec.event_time.tzinfo is not None
    assert rec.available_at.tzinfo is not None


def _utc_naive(ts):
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    return t


def test_feature_store_no_lookahead(tmp_path):
    store = FeatureStore(root=tmp_path)
    as_of = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    recs = build_panel_features({"^N225": _closes("^N225", n=30)}, as_of=as_of)
    for r in recs:
        store.put(r)
    df = store.get("^N225", "close", as_of=as_of)
    assert not df.empty
    assert (df["available_at"].apply(_utc_naive) <= _utc_naive(as_of)).all()


def test_feature_store_excludes_future(tmp_path):
    store = FeatureStore(root=tmp_path)
    as_of = datetime(2026, 9, 10, tzinfo=timezone.utc)
    recs = build_panel_features({"^N225": _closes("^N225", n=30)}, as_of=as_of)
    for r in recs:
        store.put(r)
    df = store.get("^N225", "close", as_of=as_of)
    assert (df["available_at"].apply(_utc_naive) <= _utc_naive(as_of)).all()


def test_timestamp_alignment_and_available_at():
    as_of = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    recs = build_panel_features({"^N225": _closes("^N225", n=5)}, as_of=as_of)
    for r in recs:
        assert r.available_at == r.event_time  # 日終可用，對齊
        assert r.available_at.tzinfo is not None


def test_feature_versioning(tmp_path):
    store = FeatureStore(root=tmp_path)
    as_of = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    recs = build_panel_features({"^N225": _closes("^N225", n=5)}, as_of=as_of, feature_version="v1")
    for r in recs:
        store.put(r)
    recs2 = build_panel_features({"^N225": _closes("^N225", n=5)}, as_of=as_of, feature_version="v2")
    for r in recs2:
        store.put(r)
    assert set(store.versions()) == {"v1", "v2"}


# ── Regime Engine ──

def _panel(n=260):
    idx = pd.date_range("2026-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({
        "^N225": 100 + np.cumsum(np.random.default_rng(0).normal(0.001, 0.01, n)),
        "USDJPY=X": 150 + np.cumsum(np.random.default_rng(1).normal(0, 0.1, n)),
        "^VIX": 18 + np.random.default_rng(2).normal(0, 2, n),
        "US10Y": 4.5 + np.random.default_rng(3).normal(0, 0.05, n),
        "US2Y": 4.4 + np.random.default_rng(4).normal(0, 0.03, n),
    }, index=idx)


def test_regime_reproducible():
    panel = _panel()
    e = MarketRegimeEngine()
    r1 = e.compute(panel)
    r2 = e.compute(panel)
    assert r1 == r2  # deterministic


def test_regime_no_lookahead():
    panel = _panel()
    e = MarketRegimeEngine()
    as_of = panel.index[200]
    r = e.compute(panel, as_of=as_of)
    # 只用 as_of 之前資料；重跑只到 as_of 應與全量在 as_of 時一致
    r_cut = e.compute(panel[panel.index <= as_of])
    assert r == r_cut


def test_regime_insufficient_sample():
    e = MarketRegimeEngine(minimum_sample_size=20)
    # 只有 5 根 ^N225 → trend 需要 200、vol 需要 21 → INSUFFICIENT
    panel = _panel(5)
    r = e.compute(panel)
    assert r["trend_regime"]["status"] == "REGIME_EVIDENCE=INSUFFICIENT"
    assert r["volatility_regime"]["status"] == "REGIME_EVIDENCE=INSUFFICIENT"


def test_regime_has_seven_regimes():
    r = MarketRegimeEngine().compute(_panel())
    assert set(r.keys()) == {
        "trend_regime", "volatility_regime", "risk_regime", "rates_regime",
        "fx_regime", "event_regime", "liquidity_regime",
    }


# ── Protection ──

def test_shrinkage_to_global():
    # n 小 → 收縮靠近 global；n 大 → 靠近 stat
    assert shrinkage(0.9, 0.5, 0, k=20) == pytest.approx(0.5)
    assert shrinkage(0.9, 0.5, 20, k=20) == pytest.approx(0.7)
    assert shrinkage(0.9, 0.5, 1000, k=20) > 0.85


def test_wilson_ci():
    lo, hi = wilson_ci(0.5, 100)
    assert lo < 0.5 < hi
    assert wilson_ci(0.5, 0)[0] != wilson_ci(0.5, 0)[0]  # nan


def test_protection_insufficient():
    p = RegimeProtection(minimum_sample_size=20)
    assert not p.is_sufficient(5)
    r = p.insufficient_result("trend_regime", 5)
    assert r["status"] == "REGIME_EVIDENCE=INSUFFICIENT"


# ── Event Engine ──

def test_event_phase_boundaries():
    assert event_phase(["2026-09-24"], "2026-09-21") == "PRE_EVENT"
    assert event_phase(["2026-09-24"], "2026-09-24") == "EVENT_WINDOW"
    assert event_phase(["2026-09-24"], "2026-09-27") == "POST_EVENT"
    assert event_phase(["2026-09-24"], "2026-09-01") == "NONE"


def test_event_stale_trigger():
    eng = EventEngine()
    breaking = datetime(2026, 9, 24, tzinfo=timezone.utc)
    forecasts = [
        {"forecast_id": "f1", "information_cutoff": datetime(2026, 9, 23, tzinfo=timezone.utc)},  # 事件前 → stale
        {"forecast_id": "f2", "information_cutoff": datetime(2026, 9, 25, tzinfo=timezone.utc)},  # 事件後 → 不 stale
    ]
    stale = eng.stale_forecast_ids(forecasts, breaking_event_time=breaking)
    assert stale == ["f1"]


def test_event_stale_recorded_breaking_event():
    eng = EventEngine()
    eng.record_breaking_event("FOMC", datetime(2026, 9, 24, tzinfo=timezone.utc))
    forecasts = [{"forecast_id": "f1", "information_cutoff": datetime(2026, 9, 23, tzinfo=timezone.utc)}]
    assert eng.stale_forecast_ids(forecasts) == ["f1"]
