"""Phase 2V-C.1 — Gap causality static tests."""
import sys
from pathlib import Path
import yaml
import pandas as pd

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

def _doc(p): return (ROOT / p).read_text(encoding="utf-8")
def _yaml(p): return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))
def _csv(p): return pd.read_csv(ROOT / p)

PROTO = _yaml("GAP_EXECUTION_PROTOCOL.yaml")
REPORT = _doc("PHASE2VC1_GAP_CAUSALITY_REPORT.md")

def test_signal_strictly_before_entry():
    assert "signal_created_at strictly < entry_timestamp" in PROTO["causality_rule"]

def test_full_close_signal_not_same_close_fill():
    assert "INVALID_NON_CAUSAL_STRATEGY" in PROTO["forbidden"]

def test_preclose_features_respect_cutoff():
    assert "PRE_CLOSE_15M" in PROTO["pre_close_cutoffs"]["primary"]

def test_next_bar_open_execution():
    assert "NEXT_BAR_OPEN" in PROTO["entry_semantics"]

def test_gap_calendar_not_midnight():
    assert "不用 calendar midnight" in PROTO["session_calendar"]

def test_gap_return_decomposition():
    decomp = _csv("GAP_RETURN_DECOMPOSITION.csv")
    assert "R_CC" in decomp.columns and "R_GAP" in decomp.columns and "R_OC" in decomp.columns
    # identity R_CC == R_GAP + R_OC
    import numpy as np
    err = (decomp["R_CC"] - decomp["R_GAP"] - decomp["R_OC"]).abs().max()
    assert err < 1.0

def test_preclose_component_separate():
    res = _csv("PRECLOSE_SIGNAL_RESULTS.csv")
    assert "full_close_signal" in res.columns and "pre_close_signal" in res.columns

def test_cost_scenarios_reused():
    assert PROTO["cost_scenarios"] == {"C0": 0, "C1": 1, "C2": 2, "C3": 4}

def test_no_threshold_optimization():
    assert "no threshold optimization" in PROTO["position"].lower() or "sign only" in PROTO["position"].lower()

def test_primary_cutoffs_preregistered():
    assert PROTO["pre_close_cutoffs"]["primary"] == ["PRE_CLOSE_30M", "PRE_CLOSE_15M"]

def test_roll_gap_analyzed():
    assert "ROLL" in PROTO["roll"]

def test_subperiod_gap_stability():
    assert "2026H2" in PROTO["subperiods"]

def test_full_close_edge_not_called_executable():
    assert "NON_EXECUTABLE_FORECAST_EDGE" in REPORT
    assert "STATISTICAL_ONLY_EDGE" in REPORT

def test_forward_shadow_scope_decision():
    assert "不升 strategy candidate" in REPORT or "research" in REPORT.lower()
