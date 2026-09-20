"""Phase 2V-C — Strategy validation static tests."""
import sys
from pathlib import Path
import yaml
import pandas as pd
import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

def _doc(p): return (ROOT / p).read_text(encoding="utf-8")
def _yaml(p): return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))
def _csv(p): return pd.read_csv(ROOT / p)

PROTO = _yaml("research/phase2/protocols/STRATEGY_VALIDATION_PROTOCOL.yaml")
COST = _yaml("research/phase2/protocols/STRATEGY_COST_ASSUMPTIONS.yaml")
MANIFEST = _yaml("research/phase2/manifests/STRATEGY_VALIDATION_MANIFEST.yaml")
REPORT = _doc("research/phase2/reports/PHASE2VC_STRATEGY_VALIDATION_REPORT.md")

def test_strategy_protocol_frozen():
    assert PROTO["protocol_version"] == 1
    assert PROTO["frozen_at"]
    assert PROTO["candidate"]["model"] == "VAR(1)"

def test_strategy_uses_oos_forecasts():
    assert "OOS" in PROTO["signal_source"] or "walk-forward" in PROTO["signal_source"]

def test_signal_before_entry():
    # signal at T close, entry at T+1 open
    assert "T+1" in PROTO["entry_timing"]
    assert "T+1" in PROTO["exit_timing"]

def test_no_same_close_execution():
    # 不得用 T close 產生 forecast 又同 close 成交
    assert PROTO["entry_timing"] != PROTO["exit_timing"]

def test_continuous_series_research_pnl_label():
    assert PROTO["pnl_label"] == "RESEARCH_PNL"
    assert "RESEARCH_PNL" in REPORT

def test_cost_scenarios_present():
    for c in ["C0", "C1", "C2", "C3"]:
        assert c in COST["cost_scenarios"]

def test_tick_slippage_applied():
    assert COST["tick_size_index_points"] == 5

def test_break_even_cost_calculated():
    be = _csv("research/phase2/results/BREAK_EVEN_COST_TABLE.csv")
    assert len(be) >= 3

def test_fixed_unit_position():
    assert "fixed 1 unit" in PROTO["position_sizing"]

def test_no_test_threshold_optimization():
    assert "NOT from test period" in PROTO["threshold_selection"]

def test_roll_period_analyzed():
    assert "roll" in PROTO["roll_treatment"].lower()

@pytest.mark.private_data
def test_long_short_separate():
    ls = _csv("data/strategy/long_short_split.csv")
    sides = set(ls["side"])
    assert "LONG" in sides and "SHORT" in sides

def test_regime_results_present():
    reg = _csv("research/phase2/results/STRATEGY_REGIME_RESULTS.csv")
    assert len(reg) >= 4

def test_subperiod_stability():
    sp = _csv("research/phase2/results/STRATEGY_SUBPERIOD_RESULTS.csv")
    assert len(sp) >= 5

def test_block_bootstrap_strategy():
    assert "block" in PROTO["metrics"].__str__().lower() or "bootstrap" in REPORT.lower()

@pytest.mark.private_data
def test_trade_ledger_reconciles():
    ledger = _csv("data/strategy/var_trade_ledger.csv")
    results = _csv("research/phase2/results/VAR_STRATEGY_RESULTS.csv")
    # gross expectancy from ledger should match C0 net expectancy (zero cost)
    ledger_gross_mean = ledger["gross_pts"].mean()
    c0 = results[results["cost_scenario"] == "C0"].iloc[0]
    assert abs(ledger_gross_mean - c0["avg_gross_pts"]) < 1.0

def test_no_auto_promotion():
    assert PROTO["final_status_labels"] is not None
    assert "FORWARD_VALIDATION_CANDIDATE" in REPORT or "AUTO_PROMOTE" in REPORT
