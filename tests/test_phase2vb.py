"""Phase 2V-B — Historical OOS protocol / methodology static tests."""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, "src")

ROOT = Path(__file__).resolve().parents[1]


def _doc(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


def _yaml(p: str) -> dict:
    return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))


def _json(p: str):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


PROTO = _yaml("HISTORICAL_OOS_PROTOCOL.yaml")


def test_oos_protocol_frozen():
    assert PROTO["protocol_version"] == 1
    assert PROTO.get("frozen_at")
    assert "block_on" in PROTO


def test_direct_target_is_settlement():
    d = PROTO["targets"]["DIRECT"]
    assert d["semantic"] == "future_settlement_return"
    assert "NEXT_CLOSE" in d["forbidden_mislabels"]


def test_no_proxy_as_direct_target():
    assert PROTO["targets"]["DIRECT"]["id"] == "OSE_NIKKEI225_MICRO_FUTURES"
    assert PROTO["targets"]["PROXY"]["id"] == "^N225"
    assert "禁止合併成總排名" in PROTO["targets"]["PROXY"]["note"]


def test_walk_forward_not_random():
    assert PROTO["split"] == "expanding_walk_forward"
    assert PROTO["split_forbidden"] == "random train_test_split"


def test_point_in_time_every_origin():
    assert "available_at <= cutoff" in PROTO["point_in_time_rule"]
    assert PROTO["origins"] == "every_trading_day"


def test_same_exam_hash():
    m = _yaml("OOS_EXAM_MANIFEST.yaml")
    assert m.get("exam_hash")
    assert m.get("dataset_hash")
    assert m["target"] == "^N225 (REFERENCE_PROXY)"


def test_test_not_used_for_tuning():
    assert "test" in PROTO["tuning_scope"] and "training/validation only" in PROTO["tuning_scope"]


def test_block_bootstrap_used():
    assert PROTO["bootstrap"] == "moving_block_bootstrap"
    assert PROTO["bootstrap_ci"] == 0.95


def test_dm_overlap_corrected():
    assert PROTO["forecast_comparison"] == "Diebold-Mariano"
    assert "Newey-West" in PROTO["variance_correction"]


def test_multiple_testing_controlled():
    assert PROTO["multiple_testing"] == "Benjamini-Hochberg FDR"


def test_price_direction_separate():
    assert set(PROTO["price_metrics"]) != set(PROTO["direction_metrics"])
    assert "MAE" in PROTO["price_metrics"]
    assert "balanced_accuracy" in PROTO["direction_metrics"]


def test_uncalibrated_quantile_label():
    assert PROTO["quantile_label"] == "集成研究分位摘要（未校準）"
    assert PROTO["no_fake_brier"] is True


def test_regime_min_sample():
    assert PROTO["regime_min_sample"] == 30


def test_roll_period_tagged():
    assert PROTO["roll_period"] == ["PRE_ROLL", "ROLL", "POST_ROLL"]


def test_no_auto_champion():
    assert PROTO["no_auto_promote"] is True
    d = _doc("PHASE2VB_HISTORICAL_OOS_REPORT.md")
    assert "AUTO_PROMOTE=false" in d and "CHAMPION_CANDIDATE" in d
