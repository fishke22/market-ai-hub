"""W3.4 — JNU 新高+放量正向延續假說：凍結協議 / 觸發 / 預登記 / 結算。"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_ai_hub.research.v2 import breakout_forward as BF
from market_ai_hub.research.v2 import prediction_audit as PA

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _protocol():
    return BF.load_breakout_protocol(
        ROOT / "research" / "phase3" / "JNU_NH_VOL_BREAKOUT_PREREGISTRATION_v1.yaml")


def _params():
    return BF.frozen_params(_protocol())


# ── fixture frames ──
def _settlements(n=65, *, event_value=None, rising=True):
    dates = pd.bdate_range("2026-07-01", periods=n).strftime("%Y%m%d")
    vals = [63000.0 + i * 10.0 for i in range(n)]
    if event_value is not None:
        vals[-1] = float(event_value)
    return pd.DataFrame({
        "date": dates, "settlement": vals,
        "source": ["rb"] * n, "source_hash": [f"h{i:04d}" for i in range(n)],
    })


def _volumes(n=25, *, event_volume=200.0):
    dates = pd.bdate_range("2026-08-26", periods=n).strftime("%Y%m%d")
    vals = [100.0] * n
    vals[-1] = float(event_volume)
    return pd.DataFrame({"date": dates, "volume": vals,
                         "source_url": ["https://x"] * n})


# ── frozen protocol ──
def test_protocol_frozen_fields():
    p = _protocol()
    assert p["protocol_id"] == BF.PROTOCOL_ID_FROZEN
    assert p["protocol_version"] == 1
    ev = p["definition"]["event"]
    assert int(ev["new_high_lookback_sessions"]) == 60
    assert int(ev["volume_mean_sessions"]) == 20
    assert float(ev["volume_multiple"]) == 1.5
    assert float(p["definition"]["forecast"]["frozen_value"]) == BF.FROZEN_STANCE_VALUE
    assert p["definition"]["forecast"]["calibration_status_at_origin"] == "UNCALIBRATED"
    assert p["status"]["calibrated_probability"] == "FORBIDDEN"
    assert p["evaluation"]["promotion_policy"] == "FORBIDDEN"
    assert int(p["definition"]["origin"]["lateness_cap_days"]) == 2


# ── trigger ──
def test_trigger_fires_on_new_high_with_volume_expansion():
    s = _settlements()           # 65 rows, last = 63,640 → 新高(60)
    v = _volumes(event_volume=200.0)
    t = BF.evaluate_trigger(s, v, event_date=str(s["date"].iloc[-1]), params=_params())
    assert t.fired


def test_trigger_fires_and_fields():
    s = _settlements()
    v = _volumes(event_volume=300.0)
    event = str(s["date"].iloc[-1])
    t = BF.evaluate_trigger(s, v, event_date=event, params=_params())
    assert t.fired
    assert t.event_settlement == float(s["settlement"].iloc[-1])
    assert t.prior_high == float(s["settlement"].iloc[-2])
    assert t.event_volume == 300.0
    assert abs(t.volume_baseline - 100.0) < 1e-9
    assert t.source_snapshot_ids


def test_trigger_not_new_high():
    s = _settlements(event_value=63000.0)   # 遠低於前高
    v = _volumes(event_volume=300.0)
    t = BF.evaluate_trigger(s, v, event_date=str(s["date"].iloc[-1]), params=_params())
    assert not t.fired and t.reason == BF.TRIGGER_NOT_NEW_HIGH


def test_trigger_volume_not_expanded():
    s = _settlements()
    v = _volumes(event_volume=120.0)        # 120 <= 1.5*100
    t = BF.evaluate_trigger(s, v, event_date=str(s["date"].iloc[-1]), params=_params())
    assert not t.fired and t.reason == BF.TRIGGER_VOLUME_NOT_EXPANDED


def test_trigger_event_volume_missing():
    s = _settlements()
    v = _volumes().iloc[:-1]                # 無事件日成交量
    t = BF.evaluate_trigger(s, v, event_date=str(s["date"].iloc[-1]), params=_params())
    assert not t.fired and t.reason == BF.TRIGGER_VOLUME_MISSING


def test_trigger_warmup_insufficient():
    s = _settlements(n=30)                  # lookback=60 暖機不足
    v = _volumes(event_volume=300.0)
    t = BF.evaluate_trigger(s, v, event_date=str(s["date"].iloc[-1]), params=_params())
    assert not t.fired and t.reason == BF.TRIGGER_WARMUP_SETTLEMENT


def test_trigger_event_day_not_available():
    s = _settlements()
    v = _volumes(event_volume=300.0)
    t = BF.evaluate_trigger(s, v, event_date="20260999", params=_params())
    assert not t.fired and t.reason == BF.TRIGGER_NO_EVENT_DAY


# ── precommit / settle ──
def _fired_trigger():
    s = _settlements()
    v = _volumes(event_volume=300.0)
    return BF.evaluate_trigger(s, v, event_date=str(s["date"].iloc[-1]), params=_params())


def test_precommit_writes_two_horizons_and_is_idempotent(tmp_path, monkeypatch):
    db = PA.PredictionAuditDB(tmp_path / "audit.duckdb")
    trigger = _fired_trigger()
    r5 = BF.precommit_breakout(trigger, horizon="5d", contract_code="JNU2612",
                               contract_month="202612", db=db, now=NOW)
    r20 = BF.precommit_breakout(trigger, horizon="20d", contract_code="JNU2612",
                                contract_month="202612", db=db, now=NOW)
    assert r5["status"] == BF.STATUS_PRECOMMITTED
    assert r20["status"] == BF.STATUS_PRECOMMITTED
    r5b = BF.precommit_breakout(trigger, horizon="5d", contract_code="JNU2612",
                                contract_month="202612", db=db, now=NOW)
    assert r5b["status"] == BF.STATUS_ALREADY_PRECOMMITTED

    pred = db.get_prediction(r5["prediction_id"])
    assert pred.horizon == "5d" and pred.model == BF.MODEL_NAME
    assert pred.label_window_start >= NOW and pred.label_window_end > NOW
    assert pred.label_window_id == r5["target_trading_date"]
    arts = db.get_forecast_artifacts(pred.prediction_id)
    assert len(arts) == 1 and arts[0].artifact_type == "EVENT_PROBABILITY"
    assert arts[0].event_threshold_value == trigger.event_settlement
    assert arts[0].value == BF.FROZEN_STANCE_VALUE
    assert arts[0].calibration_status_at_origin == "UNCALIBRATED"
    for a in arts:
        assert not PA.is_public_probability(a)


def test_settle_flow_up_then_idempotent(tmp_path, monkeypatch):
    db = PA.PredictionAuditDB(tmp_path / "audit.duckdb")
    trigger = _fired_trigger()
    r5 = BF.precommit_breakout(trigger, horizon="5d", contract_code="JNU2612",
                               contract_month="202612", db=db, now=NOW)
    pred = db.get_prediction(r5["prediction_id"])

    def fake_history(month):
        return pd.DataFrame({
            "date": [pred.label_window_id],
            "settlement": [float(trigger.event_settlement) + 500.0],
            "source": ["rb"], "source_hash": ["t1"],
        })

    monkeypatch.setattr(BF, "load_settlement_history", fake_history)
    monkeypatch.setattr(BF, "_now_utc", lambda: NOW + timedelta(days=20))
    results = BF.settle_breakout(db=db)
    settled = [r for r in results if r["prediction_id"] == pred.prediction_id]
    assert settled and settled[0]["status"] == "SETTLED"
    assert settled[0]["actual"] == 1
    outs = db.get_outcomes(pred.prediction_id)
    assert len(outs) == 1 and outs[0].actual_value == 1.0
    again = BF.settle_breakout(db=db)
    again = [r for r in again if r["prediction_id"] == pred.prediction_id]
    assert again and again[0]["status"] == "ALREADY_SETTLED"
    summary = BF.w34_evidence_summary(db=db)
    assert summary["status"] == "UNPROVEN" and summary["promotion"] == "FORBIDDEN"
    assert summary["horizons"]["5d"]["settled"] == 1
    assert summary["horizons"]["5d"]["hits"] == 1
    assert summary["horizons"]["5d"]["hit_rate"] == 1.0


def test_settle_flow_down_case(tmp_path, monkeypatch):
    db = PA.PredictionAuditDB(tmp_path / "audit.duckdb")
    trigger = _fired_trigger()
    r5 = BF.precommit_breakout(trigger, horizon="5d", contract_code="JNU2612",
                               contract_month="202612", db=db, now=NOW)
    pred = db.get_prediction(r5["prediction_id"])
    monkeypatch.setattr(
        BF, "load_settlement_history",
        lambda month: pd.DataFrame({
            "date": ["20260999"], "settlement": [0.0], "source": ["rb"], "source_hash": ["t0"],
        }),
    )
    monkeypatch.setattr(BF, "_now_utc", lambda: NOW + timedelta(days=20))
    results = BF.settle_breakout(db=db)
    assert any(r["prediction_id"] == pred.prediction_id
               and r["status"] == "OUTCOME_NOT_ELIGIBLE" for r in results)


def test_settle_not_mature_yet(tmp_path, monkeypatch):
    db = PA.PredictionAuditDB(tmp_path / "audit.duckdb")
    trigger = _fired_trigger()
    r5 = BF.precommit_breakout(trigger, horizon="20d", contract_code="JNU2612",
                               contract_month="202612", db=db, now=NOW)
    monkeypatch.setattr(BF, "_now_utc", lambda: NOW + timedelta(days=1))
    results = BF.settle_breakout(db=db)
    assert any(r["prediction_id"] == r5["prediction_id"]
               and r["status"] == "NOT_MATURE" for r in results)


# ── 接線：nightly sync 腳本對 W3.4 步驟的 gate 容忍 ──
def test_sync_script_runs_w34_fail_soft(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "jpx_sync", ROOT / "scripts" / "update_jpx_micro_direct.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "refresh_current_settlement",
                        lambda days=10: {"status": "OK", "trade_date": "20261002",
                                         "micro_months": ["202610", "202611", "202612"]})
    monkeypatch.setattr(mod, "refresh_public_archive", lambda mc=3: {"status": "OK"})
    monkeypatch.setattr(mod, "refresh_open_interest", lambda l=45: {"status": "PARTIAL", "errors": {}})
    monkeypatch.setattr(mod, "run_w34_breakout",
                        lambda months: {"schema": "W3.4", "status": "NO_FIRE",
                                        "reason": "WARMUP_INSUFFICIENT_VOLUME",
                                        "values_exposed": False})
    result = mod.run()
    assert result["settlement"]["status"] == "OK"
    assert result["archive"]["status"] == "OK"
    assert result["w34_breakout"]["status"] == "NO_FIRE"
    assert result["w34_breakout"]["values_exposed"] is False