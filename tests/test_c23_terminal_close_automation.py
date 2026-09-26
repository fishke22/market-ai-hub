"""C2.3 terminal-close automation and W3.2 operator regression."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from market_ai_hub.research.v2 import forward_cycle as FC


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "scripts" / "run_w32_osaka_forward_cycle.py"
MAINTENANCE = ROOT / "scripts" / "run_c23_terminal_close_maintenance.ps1"
REGISTER = ROOT / "scripts" / "register_c23_terminal_close_task.ps1"
WATCHDOG = ROOT / "scripts" / "ensure_jnu_data_capture.ps1"


def _load_operator():
    spec = importlib.util.spec_from_file_location("w32_operator", OPERATOR)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeAudit:
    def __init__(self):
        self.predictions = {
            "w32-pending": SimpleNamespace(
                prediction_id="w32-pending",
                target_family=FC.TARGET_FAMILY,
                instrument=FC.INSTRUMENT,
                horizon=FC.HORIZON,
                model=FC.MODEL_NAME,
                model_version=FC.MODEL_VERSION,
                sample_origin="FORWARD_PRECOMMITTED",
            ),
            "other-market": SimpleNamespace(
                prediction_id="other-market",
                target_family="TAIWAN_INDEX",
                instrument="TX",
                horizon=FC.HORIZON,
                model=FC.MODEL_NAME,
                model_version=FC.MODEL_VERSION,
                sample_origin="FORWARD_PRECOMMITTED",
            ),
            "w32-settled": SimpleNamespace(
                prediction_id="w32-settled",
                target_family=FC.TARGET_FAMILY,
                instrument=FC.INSTRUMENT,
                horizon=FC.HORIZON,
                model=FC.MODEL_NAME,
                model_version=FC.MODEL_VERSION,
                sample_origin="FORWARD_PRECOMMITTED",
            ),
        }

    def list_prediction_ids(self):
        return list(self.predictions)

    def get_prediction(self, prediction_id):
        return self.predictions.get(prediction_id)

    def get_outcomes(self, prediction_id):
        return [object()] if prediction_id == "w32-settled" else []


def test_w32_operator_settles_pending_scope_then_precommits(monkeypatch):
    mod = _load_operator()
    audit = FakeAudit()
    settled = []
    precommits = []

    def fake_settle(prediction_id, *, db, store):
        settled.append(prediction_id)
        return FC.ForwardCycleResult(
            status=FC.STATUS_SETTLED,
            prediction_id=prediction_id,
            outcome_id="outcome-1",
            target_trading_date="2026-09-28",
        )

    def fake_precommit(*, contract_code, db, store):
        precommits.append(contract_code)
        return FC.ForwardCycleResult(
            status=FC.STATUS_PRECOMMITTED,
            prediction_id="new-prediction",
            target_trading_date="2026-09-29",
        )

    monkeypatch.setattr(mod.FC, "settle_osaka_from_feature_store", fake_settle)
    monkeypatch.setattr(mod.FC, "precommit_osaka_from_feature_store", fake_precommit)
    result = mod.run_cycle("jnu2612", db=audit, store=object())

    assert settled == ["w32-pending"]
    assert precommits == ["JNU2612"]
    assert result["precommit"]["status"] == FC.STATUS_PRECOMMITTED
    assert result["values_exposed"] is False
    assert all("close" not in json.dumps(x).lower() for x in result["settlements"])


def test_w32_operator_rejects_non_exact_contract():
    mod = _load_operator()
    with pytest.raises(ValueError, match="EXPECTED_EXACT_JNU_CONTRACT"):
        mod.run_cycle("JNU_CONT", db=FakeAudit(), store=object())


def test_maintenance_script_guards_window_before_broker_mutation():
    text = MAINTENANCE.read_text(encoding="utf-8")
    window = text.index('if ($Window.status -ne "QUERY_WINDOW_READY")')
    stop = text.index("& $Stop | Out-Host")
    start = text.index("& $Start -EnableTickDetailMeasurements")
    request = text.index("& $Request -Symbol $Symbol")
    assert window < stop < start < request
    assert "TICK_DETAIL_RUNTIME_EVIDENCE_RECORDED" in text
    assert "materialize_ose_terminal_close.py" in text
    assert "run_w32_osaka_forward_cycle.py" in text
    assert "values_exposed = $false" in text
    assert "broker_order_action = $false" in text


def test_maintenance_is_idempotent_and_restores_safe_default():
    text = MAINTENANCE.read_text(encoding="utf-8")
    assert 'status -eq "SUCCESS"' in text
    assert "C23_TERMINAL_CLOSE_ALREADY_DONE" in text
    assert "Local\\MARKET_AI_HUB_C23_TERMINAL_CLOSE" in text
    assert "$HandoverAttempted = $true" in text
    assert "$MaintenanceStarted" not in text
    finally_pos = text.index("finally {")
    assert text.index("& $Stop | Out-Host", finally_pos) > finally_pos
    assert text.index("& $Start | Out-Host", finally_pos) > finally_pos


def test_watchdog_yields_to_fresh_c23_handover():
    text = WATCHDOG.read_text(encoding="utf-8")
    assert "C23_MAINTENANCE_IN_PROGRESS" in text
    assert '$age -ge 0 -and $age -lt 15' in text


def test_registration_polls_timezone_aware_window_with_dry_run():
    text = REGISTER.read_text(encoding="utf-8")
    assert "param([switch]$DryRun, [switch]$PreserveExisting)" in text
    assert "RepetitionInterval (New-TimeSpan -Minutes 5)" in text
    assert "-MultipleInstances IgnoreNew" in text
    assert "OSE_SESSION_DATE_AND_15_45_TO_17_00_JST" in text
    assert "max_attempts_per_trading_date = 3" in text
    assert "broker_order_action = $false" in text


def test_measurement_queue_path_is_capturable_stdout():
    text = (ROOT / "scripts" / "request_yuanta_tick_detail_measurement.ps1").read_text(encoding="utf-8")
    assert 'Write-Output "YUANTA_TICK_DETAIL_MEASUREMENT_QUEUED $p"' in text
    assert 'Write-Host "YUANTA_TICK_DETAIL_MEASUREMENT_QUEUED $p"' not in text


def test_maintenance_bounds_attempts_per_trading_date():
    text = MAINTENANCE.read_text(encoding="utf-8")
    assert "$AttemptCount -ge 3" in text
    assert "MAX_THREE_ATTEMPTS_PER_TRADING_DATE" in text
    assert "$AttemptCount += 1" in text
