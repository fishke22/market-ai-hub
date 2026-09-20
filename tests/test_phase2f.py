"""Phase 2F — strategy research engine tests。"""
import numpy as np
import pandas as pd
import pytest

from market_ai_hub.automation.archive import AnalysisArchive, AnalysisRecord
from market_ai_hub.strategy.contract import FORBIDDEN_STATUSES, StrategyCandidate
from market_ai_hub.strategy.cost import CostModel
from market_ai_hub.strategy.edge_store import HistoricalEdgeStore, compute_edge
from market_ai_hub.strategy.fine_tune import get_adapter
from market_ai_hub.strategy.metrics import compute_strategy_metrics
from market_ai_hub.strategy.output import classify_output
from market_ai_hub.strategy.overfitting import guard_edge
from market_ai_hub.strategy.search import conditional_returns, search_condition_combos
from market_ai_hub.strategy.signal_dataset import build_signal_dataset, forward_returns
from market_ai_hub.strategy.tradingview_bridge import OPTIONAL_EXTERNAL_UI_SOURCE
from market_ai_hub.strategy.walk_forward import assert_frozen_test, walk_forward_split
from market_ai_hub.strategy.yuanta import YuantaQuoteOnlyGateway, YuantaRecorderContract


def _closes(n=120, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    price = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
    return pd.Series(price, index=idx)


def _forecasts(n=100, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-02", periods=n, freq="B", tz="UTC")
    return [
        {
            "information_cutoff": t,
            "forecast_id": f"f{i}",
            "model_name": "test_model",
            "horizon": "1d",
            "direction": "up" if rng.random() > 0.5 else "down",
            "point_forecast": 100.0 * (1 + rng.normal(0, 0.02)),
            "origin_price": 100.0,
        }
        for i, t in enumerate(idx)
    ]


# --- B: point-in-time ---
def test_strategy_point_in_time():
    closes = _closes()
    forecasts = _forecasts()
    regime = pd.DataFrame(
        {"trend_regime": ["bull"] * len(closes)}, index=closes.index
    )
    df = build_signal_dataset(closes, forecasts, regime)
    assert "decision_time" in df.columns and "fwd_1d" in df.columns
    # features 只有 as-of regime（trend_regime），無未來欄位
    assert "trend_regime" in df.columns


def test_strategy_no_lookahead():
    closes = _closes()
    forecasts = _forecasts()
    # regime 在後半段才變 bear；前半段決策不得看到 bear
    half = len(closes) // 2
    labels = ["bull"] * half + ["bear"] * (len(closes) - half)
    regime = pd.DataFrame({"trend_regime": labels}, index=closes.index)
    df = build_signal_dataset(closes, forecasts, regime)
    # 決策時間在前半段的 row，regime 必為 bull（backward asof join 不洩漏未來）
    early = df[df["decision_time"] < closes.index[half]]
    assert (early["trend_regime"] == "bull").all()


# --- D: edge min sample ---
def test_edge_min_sample():
    e = compute_edge(pd.Series([0.01, -0.02, 0.03]), min_sample=30)
    assert e.status == "INSUFFICIENT_EVIDENCE" and e.sample_size == 3


def test_edge_found():
    rng = np.random.default_rng(0)
    e = compute_edge(pd.Series(rng.normal(0.02, 0.01, 200)), min_sample=30)
    assert e.status == "EDGE_FOUND" and e.positive_rate > 0.9


# --- F: walk-forward split ---
def test_walk_forward_split():
    closes = _closes(120)
    ws = walk_forward_split(closes.index, n_splits=3)
    assert len(ws) >= 1
    for w in ws:
        assert assert_frozen_test(w)


# --- E: cost sensitivity ---
def test_cost_sensitivity():
    rng = np.random.default_rng(0)
    r = list(rng.normal(0.001, 0.01, 100))
    m_zero = compute_strategy_metrics(r, CostModel.preset("ZERO_COST"))
    m_stress = compute_strategy_metrics(r, CostModel.preset("STRESS_COST"))
    # 有成本 → expectancy 下降
    assert m_stress["expectancy"] < m_zero["expectancy"]
    assert m_zero["cost_sensitivity"] == 0.0
    assert m_stress["cost_sensitivity"] != 0.0


# --- H: overfitting guard ---
def test_guard_small_sample_not_edge():
    ok, reason = guard_edge(5, hit_rate=0.8)
    assert not ok and "insufficient trades" in reason


# --- J: output 三態 ---
def test_strategy_wait_valid():
    c = StrategyCandidate(strategy_id="s1", status="EXPERIMENTAL")
    assert classify_output(c, None) == "NO_EDGE"


def test_strategy_no_edge_valid():
    from market_ai_hub.strategy.contract import RESEARCH_OUTPUTS
    assert "NO_EDGE" in RESEARCH_OUTPUTS and "WAIT" in RESEARCH_OUTPUTS and "TRADE_CANDIDATE" in RESEARCH_OUTPUTS


def test_forbidden_status_rejected():
    with pytest.raises(ValueError):
        StrategyCandidate(strategy_id="x", status="PRODUCTION_TRADING")


# --- K: analysis archive link ---
def test_analysis_archive_link(tmp_path):
    a = AnalysisArchive(tmp_path)
    rec = AnalysisRecord(analysis_id="A1", information_cutoff="2024-06-01T00:00:00+00:00", target="^N225")
    a.save(rec)
    a.link_strategy("A1", "strat-1", "RESEARCH_CANDIDATE", "TREND_UP+RISK_ON edge CI>0")
    links = a.get_strategy_links("A1")
    assert len(links) == 1 and links[0]["strategy_candidate_id"] == "strat-1"


# --- L: finetune adapter disabled default ---
def test_finetune_adapter_disabled_default():
    assert get_adapter("xgboost").supported is True
    assert get_adapter("lightgbm").supported is True
    assert get_adapter("nhits").supported is True
    assert get_adapter("nbeatsx").supported is True
    assert get_adapter("moirai-2").supported is False  # foundation disabled
    assert get_adapter("ttm").supported is False


# --- M/N: tradingview optional only ---
def test_tradingview_optional_only():
    assert OPTIONAL_EXTERNAL_UI_SOURCE == "OPTIONAL_EXTERNAL_UI_SOURCE"


def test_tradingview_no_core_dependency():
    from market_ai_hub.strategy import tradingview_bridge as tvb
    assert not hasattr(tvb.TradingViewResearchBridge, "place_order")
    assert not hasattr(tvb.TradingViewResearchBridge, "broker_order")


def test_tradingview_no_credentials():
    from market_ai_hub.strategy import tradingview_bridge as tvb
    for f in ("cookie", "password", "session_secret"):
        assert not hasattr(tvb, f)


# --- O: yuanta realtime disabled ---
def test_yuanta_realtime_disabled():
    g = YuantaQuoteOnlyGateway()
    assert g.is_realtime_recorder_enabled() is False
    assert g.realtime_recorder_enabled is False
    assert YuantaRecorderContract().enabled is False


# --- C: search smoke ---
def test_search_condition_combos():
    closes = _closes(120)
    forecasts = _forecasts()
    regime = pd.DataFrame({"trend_regime": ["bull"] * len(closes)}, index=closes.index)
    df = build_signal_dataset(closes, forecasts, regime)
    edges = search_condition_combos(df, "Nikkei", "^N225", horizon="fwd_1d",
                                    base_cols=("trend_regime",), max_depth=1, min_sample=5)
    assert isinstance(edges, list)


def test_edge_store_roundtrip(tmp_path):
    store = HistoricalEdgeStore(root=tmp_path)
    e = compute_edge(pd.Series([0.01] * 40), market="Nikkei", instrument="^N225",
                     horizon="fwd_1d", conditions={"trend_regime": "bull"}, min_sample=5)
    store.record(e)
    rows = store.query(market="Nikkei")
    assert len(rows) == 1 and rows[0]["status"] == "EDGE_FOUND"
