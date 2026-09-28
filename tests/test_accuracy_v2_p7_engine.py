from pathlib import Path

import pytest

from market_ai_hub.research.accuracy_v2_p7 import load_p7_protocol
from market_ai_hub.research import accuracy_v2_p7_engine as p7e


def _fake_result(digest="same"):
    return {
        "status": "OK",
        "engine_version": "1.231.0",
        "bars_seen": 64,
        "fill_count": 2,
        "positions_open": 0,
        "positions_closed": 1,
        "fills": [
            {"ts_init": 1, "ts_last": 1, "side": "BUY", "avg_px": 100.0},
            {"ts_init": 2, "ts_last": 2, "side": "SELL", "avg_px": 100.25},
        ],
        "account": {"total": "1000000.25", "free": "1000000.25", "currency": "USD"},
        "no_network_market_data": True,
        "no_live_adapter": True,
        "no_external_order_action": True,
        "result_digest": digest,
    }


def test_p7_cost_diagnostic_is_proxy_and_monotonic():
    out = p7e.cost_diagnostic()
    assert out["status"] == "COST_DIAGNOSTIC_PASS"
    assert out["presets"]["ZERO_COST"]["round_trip_cost_bps"] == 0.0
    assert out["presets"]["BASE_COST"]["round_trip_cost_bps"] == 26.0
    assert out["presets"]["STRESS_COST"]["round_trip_cost_bps"] == 120.0
    assert out["actual_execution_cost_claim"] is False
    assert out["trading_edge_claim"] is False


def test_p7_parity_contract_requires_two_equal_real_digests(monkeypatch, tmp_path):
    monkeypatch.setattr(
        p7e,
        "verify_isolated_engine",
        lambda protocol=None: {
            "status": "VERIFIED",
            "actual_version": "1.231.0",
            "expected_version": "1.231.0",
        },
    )
    monkeypatch.setattr(p7e, "_run_isolated_once", lambda **kwargs: _fake_result("abc"))
    out = p7e.run_parity_acceptance(workspace=tmp_path)
    assert out["status"] == "PARITY_PASS"
    assert out["PARITY_PASS"] is True
    assert out["checks"]["repeated_result_digest_equal"] is True
    assert out["predictive_performance_claim"] is False
    assert out["trading_edge_claim"] is False


def test_p7_parity_fails_if_repeat_digest_differs(monkeypatch, tmp_path):
    monkeypatch.setattr(
        p7e,
        "verify_isolated_engine",
        lambda protocol=None: {
            "status": "VERIFIED",
            "actual_version": "1.231.0",
            "expected_version": "1.231.0",
        },
    )
    results = iter([_fake_result("a"), _fake_result("b")])
    monkeypatch.setattr(p7e, "_run_isolated_once", lambda **kwargs: next(results))
    out = p7e.run_parity_acceptance(workspace=tmp_path)
    assert out["status"] == "PARITY_FAIL"
    assert out["checks"]["repeated_result_digest_equal"] is False


def test_p7_engine_not_ready_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        p7e,
        "verify_isolated_engine",
        lambda protocol=None: {"status": "NOT_INSTALLED"},
    )
    out = p7e.run_parity_acceptance(workspace=tmp_path)
    assert out["status"] == "ENGINE_NOT_READY"
    assert out["PARITY_PASS"] is False


def test_p7_protocol_canonical_python_is_under_data_root(monkeypatch, tmp_path):
    monkeypatch.setattr(p7e, "data_root", lambda: tmp_path)
    p = load_p7_protocol()
    exe = p7e.canonical_nautilus_python(p)
    assert exe == tmp_path / Path(p.raw["engine"]["canonical_relative_python"])
