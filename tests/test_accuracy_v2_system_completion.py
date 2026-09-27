from __future__ import annotations

from copy import deepcopy

import yaml

from market_ai_hub.services.system_completion import (
    DEFAULT_SYSTEM_COMPLETION_PATH,
    SYSTEM_COMPLETION_SCHEMA_VERSION,
    SystemCompletionProtocolError,
    system_completion_snapshot,
)


def _policy_copy(tmp_path, mutate):
    raw = yaml.safe_load(DEFAULT_SYSTEM_COMPLETION_PATH.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "completion.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def test_system_completion_reports_no_current_actionable_engineering_gaps():
    out = system_completion_snapshot()
    assert out["schema_version"] == SYSTEM_COMPLETION_SCHEMA_VERSION
    assert out["status"] == "ENGINEERING_COMPLETE_WAITING_FOR_EXTERNAL_EVIDENCE"
    assert out["all_currently_actionable_engineering_complete"] is True
    assert out["actionable_engineering_gap_count"] == 0
    assert out["conditional_packages"]["P6"]["engineering_completion_blocker"] is False
    assert all(
        item["engineering_completion_blocker"] is False
        for item in out["deferred_non_blocking"].values()
    )
    assert out["deferred_non_blocking"]["broker_order_execution"]["quote_only"] is True
    assert out["authorization_boundaries"]["live_trading"]["authorized"] is False
    assert out["authorization_boundaries"]["live_trading"]["quote_only"] is True
    assert out["sealed_evidence"]["hpq1_old_final"]["rerun_allowed"] is False
    assert out["sealed_evidence"]["p2_final"]["minimum_new_forward_origins"] == 20
    assert out["claims"] == {
        "PREDICTIVE_GAIN": False,
        "CALIBRATED": False,
        "TRADING_EDGE": False,
        "live_execution_enabled": False,
    }


def test_system_completion_missing_required_component_is_actionable_gap(tmp_path):
    out = system_completion_snapshot(root=tmp_path)
    assert out["status"] == "ENGINEERING_INCOMPLETE_ACTION_REQUIRED"
    assert out["all_currently_actionable_engineering_complete"] is False
    assert out["actionable_engineering_gap_count"] == len(out["required_engineering"])
    assert all(item["status"] == "MISSING" for item in out["required_engineering"])


def test_system_completion_rejects_p6_becoming_completion_blocker(tmp_path):
    path = _policy_copy(
        tmp_path,
        lambda raw: raw["completion"]["conditional_packages"]["P6"].update(
            {"engineering_completion_blocker": True}
        ),
    )
    try:
        system_completion_snapshot(policy_path=path)
    except SystemCompletionProtocolError as exc:
        assert "P6 conditional boundary changed" in str(exc)
    else:
        raise AssertionError("P6 boundary weakening must fail closed")


def test_system_completion_rejects_live_trading_authorization(tmp_path):
    path = _policy_copy(
        tmp_path,
        lambda raw: raw["completion"]["authorization_boundaries"]["live_trading"].update(
            {"authorized": True}
        ),
    )
    try:
        system_completion_snapshot(policy_path=path)
    except SystemCompletionProtocolError as exc:
        assert "authorization boundary weakened" in str(exc)
    else:
        raise AssertionError("live trading authorization weakening must fail closed")


def test_system_completion_rejects_claim_promotion(tmp_path):
    path = _policy_copy(
        tmp_path,
        lambda raw: raw["completion"]["claims"].update({"PREDICTIVE_GAIN": True}),
    )
    try:
        system_completion_snapshot(policy_path=path)
    except SystemCompletionProtocolError as exc:
        assert "claim boundary weakened" in str(exc)
    else:
        raise AssertionError("predictive claim weakening must fail closed")


def test_system_completion_requires_first_class_public_data_markers(tmp_path):
    raw = yaml.safe_load(DEFAULT_SYSTEM_COMPLETION_PATH.read_text(encoding="utf-8"))
    source_root = DEFAULT_SYSTEM_COMPLETION_PATH.parents[1]
    for item in raw["completion"]["required_engineering"].values():
        src = source_root / item["path"]
        dst = tmp_path / item["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    taiex = tmp_path / "src/market_ai_hub/providers/twse.py"
    taiex.write_text(
        taiex.read_text(encoding="utf-8").replace(
            "def fetch_taiex_daily(", "def removed_taiex_daily("
        ),
        encoding="utf-8",
    )
    out = system_completion_snapshot(root=tmp_path)
    assert out["all_currently_actionable_engineering_complete"] is False
    assert any(
        gap["component_id"] == "taiex_official_daily"
        and gap["reason"] == "REQUIRED_MARKER_MISSING"
        for gap in out["actionable_engineering_gaps"]
    )
