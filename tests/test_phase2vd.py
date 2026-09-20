"""Phase 2V-D — Forward Shadow static tests."""
import sys
from pathlib import Path
import yaml

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

def _doc(p): return (ROOT / p).read_text(encoding="utf-8")
def _yaml(p): return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))

PROTO = _yaml("research/phase2/protocols/FORWARD_SHADOW_PROTOCOL.yaml")
ACT = _yaml("research/phase2/manifests/FORWARD_SHADOW_ACTIVATION.yaml")
MANIFEST = _yaml("research/phase2/manifests/FORWARD_VALIDATION_MANIFEST.yaml")
REPORT = _doc("research/phase2/reports/FORWARD_SHADOW_REPORT.md")
SETUP = _doc("research/phase2/reports/PHASE2VD_FORWARD_SHADOW_SETUP_REPORT.md")

def test_forward_activation_timestamp():
    assert ACT.get("activated_at")
    assert ACT.get("build_id")
    assert ACT["protocol_version"] == 1

def test_no_historical_forecast_as_forward():
    assert PROTO["no_backfill_as_forward"] is True
    assert "activation timestamp 之前永遠不算 forward evidence" in PROTO["activation"]["boundary"]

def test_forecast_append_only():
    assert PROTO["immutability"]["append_only"] is True
    assert PROTO["immutability"]["no_post_actual_modification"] is True

def test_actual_cannot_modify_forecast():
    assert "不得修改 forecast" in _doc("scripts/settle_forward_predictions.ps1")

def test_same_origin_baseline():
    assert PROTO["baseline_same_origin"] is True

def test_model_version_cohort():
    assert PROTO["cohort"] == "VAR_V1_FORWARD"
    assert PROTO["model_freeze"]["new_model_rule"] == "model_version += 1，獨立 cohort"

def test_data_quality_can_skip():
    assert PROTO["data_quality_gate"]["on_failure"] == "FORECAST_SKIPPED_DATA_QUALITY"

def test_forward_metrics_separate():
    assert PROTO["metrics"]["price"] is not None
    assert PROTO["metrics"]["direction"] is not None
    assert "HISTORICAL EVIDENCE" in REPORT and "FORWARD EVIDENCE" in REPORT

def test_small_n_labels():
    assert PROTO["small_n_labels"]["n_lt_20"] == "TOO_EARLY"
    assert PROTO["small_n_labels"]["n_ge_150"] == "SUBSTANTIAL_FORWARD"

def test_non_executable_label_preserved():
    assert "NON_EXECUTABLE_FORECAST_EDGE" in PROTO["non_executable_label"]
    assert "RESEARCH_FORECAST_ONLY" in PROTO["non_executable_label"]

def test_no_trade_signal_generation():
    assert PROTO["mcp_trade_signal"] == "NONE"
    assert "BUY" not in PROTO["mcp_trade_signal"]

def test_scheduler_default_disabled():
    assert PROTO["scheduler_default"] == "DISABLED"

def test_settlement_append_only():
    assert "append-only" in PROTO["registry"]["backend"]
    assert "不得修改 forecast" in _doc("scripts/settle_forward_predictions.ps1")

def test_drift_no_auto_retrain():
    assert PROTO["drift_monitoring"]["drift_is_alert_only"] is True

def test_no_auto_promotion():
    assert PROTO["no_auto_promotion"] is True
