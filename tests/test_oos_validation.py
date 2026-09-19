"""V1.1 OOS validation pipeline + promotion rule tests（deterministic，不靠模型）。"""
from __future__ import annotations

import numpy as np
import pytest

from market_ai_hub.services.validation import (
    PROMOTION_RULES,
    determine_validation_status,
    evaluate_against_baselines,
)


def test_promotion_rules_are_in_code():
    exp = PROMOTION_RULES["UNVALIDATED_TO_EXPERIMENTAL"]
    val = PROMOTION_RULES["EXPERIMENTAL_TO_VALIDATED"]
    assert exp["min_rolling_origins"] == 3
    assert exp["min_oos_samples"] == 10
    assert val["mase_max"] == 1.0
    assert val["min_windows"] == 2


def _good_result(n_origins=3, n_oos=10):
    return {
        "status": "OK",
        "n_origins": n_origins,
        "eval": {
            "n_oos": n_oos,
            "beats_naive_mae": True,
            "beats_drift_mae": False,
            "model": {"mase": 0.9},
        },
    }


def test_unvalidated_when_no_run():
    status, reasons = determine_validation_status({"status": "INSUFFICIENT_DATA"})
    assert status == "UNVALIDATED"
    assert reasons


def test_unvalidated_when_below_thresholds():
    status, reasons = determine_validation_status(_good_result(n_origins=2, n_oos=5))
    assert status == "UNVALIDATED"
    assert any("門檻未達" in r for r in reasons)


def test_experimental_when_beats_naive_but_not_validated_thresholds():
    status, reasons = determine_validation_status(_good_result(n_origins=3, n_oos=10))
    assert status == "EXPERIMENTAL"
    assert any("VALIDATED 門檻未達" in r for r in reasons)


def test_validated_requires_drift_and_mase():
    r = _good_result(n_origins=8, n_oos=50)
    r["eval"]["beats_drift_mae"] = True
    r["eval"]["model"]["mase"] = 0.8
    status, _ = determine_validation_status(r)
    assert status == "VALIDATED"


def test_not_validated_if_mase_over_1():
    r = _good_result(n_origins=8, n_oos=50)
    r["eval"]["beats_drift_mae"] = True
    r["eval"]["model"]["mase"] = 1.3
    status, _ = determine_validation_status(r)
    assert status == "EXPERIMENTAL"


def test_evaluate_baselines_shapes():
    rng = np.random.default_rng(3)
    actuals = rng.normal(100, 1, 20)
    prevs = rng.normal(100, 1, 20)
    ev = evaluate_against_baselines("X", actuals, prevs, prevs.tolist(), steps=1)
    assert ev["status"] == "OK"
    # 模型預測 = prev = last-price naive 的預測 → 兩者 MAE 相同，beats=False
    assert ev["model"]["mae"] == pytest.approx(ev["last_price_naive"]["mae"])
    assert ev["beats_naive_mae"] is False


def test_ts_validation_store_roundtrip(tmp_path, monkeypatch):
    import market_ai_hub.services.validation as v

    (tmp_path / "data").mkdir(exist_ok=True)
    monkeypatch.setattr(v, "project_root", lambda: tmp_path)
    store = v.TsValidationStore()
    result = _good_result()
    result["model"] = "chronos-2"
    result["symbol"] = "^N225"
    result["interval"] = {"coverage": 0.75, "calibration_error": 0.05}
    store.save(result, "EXPERIMENTAL")
    rec = store.latest("chronos-2", "^N225")
    assert rec is not None
    assert rec["model"] == "chronos-2"
    assert rec["result"]["eval"]["beats_naive_mae"] is True
