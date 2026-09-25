from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from market_ai_hub.feature_store.store import FeatureStore
from market_ai_hub.integrations.yuanta import live_quote_recorder as R
from market_ai_hub.integrations.yuanta.spark_runtime import (
    TickDetailCallbackTrace,
    TickDetailRequestTrace,
)
from market_ai_hub.research.v2 import terminal_close_materializer as TCM
from market_ai_hub.research.v2 import tick_detail_source as TD
from market_ai_hub.research.v2 import tick_detail_verification as TV

UTC = timezone.utc


def _dt(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 25, hour, minute, second, tzinfo=UTC)


class _Row:
    def __init__(self, hour: int, minute: int, second: int, price: float, seq: int, volume: int = 1):
        self.TimeStamp = datetime(2026, 9, 25, hour, minute, second)
        self.DealPrice = price
        self.DealVol = volume
        self.BuyPrice = price - 5
        self.SellPrice = price + 5
        self.SeqNo = seq
        self.InOutFlag = 0


class _Result:
    def __init__(self, rows, market: int = TD.OSE_MARKET_NO, stock: str = "JNU2612"):
        self.MarketNo = market
        self.StockCode = stock
        self.StickDetailList = list(rows)


def _result(*, raw_hour: int = 15, raw_minute: int = 44):
    return _Result([
        _Row(raw_hour, raw_minute, 50, 65900.0, 100),
        _Row(raw_hour, raw_minute, 59, 65905.0, 101),
    ])


def _batch(*, raw_hour: int = 15, raw_minute: int = 44):
    return TD.parse_tick_detail_result(
        _result(raw_hour=raw_hour, raw_minute=raw_minute),
        received_at=_dt(6, 46),
    )


class _FakeRuntime:
    def __init__(self, result=None, *, request_time=None, callback_time=None, accepted=True):
        self.on_tick_detail_callback = None
        self.result = result or _result()
        self.request_time = request_time or _dt(6, 45, 30)
        self.callback_time = callback_time or _dt(6, 46)
        self.accepted = accepted
        self.calls = []
        self.request = None
        self.callback = None
        self.emitted = False
        self.pending_trace = None

    def tick_detail_runtime_traces(self):
        requests = []
        callbacks = []
        if self.pending_trace is not None:
            requests.append({
                "request_id": self.pending_trace,
                "request_time_utc": self.request_time,
                "market_no": TD.OSE_MARKET_NO,
                "stock_code": "JNU2612",
                "last_count": 20,
                "accepted": True,
            })
        return {"requests": requests, "callbacks": callbacks}

    def request_tick_detail_last(self, account, market_no, stock_code, last_count):
        self.calls.append((account, market_no, stock_code, last_count))
        self.request = TickDetailRequestTrace(
            request_id="tick_detail_1",
            request_time_utc=self.request_time,
            market_no=market_no,
            stock_code=stock_code,
            last_count=last_count,
            accepted=self.accepted,
        )
        return self.accepted

    def latest_tick_detail_request(self):
        return self.request

    def pump(self, _seconds):
        if self.emitted or self.request is None or not self.accepted:
            return
        self.callback = TickDetailCallbackTrace(
            request_id=self.request.request_id,
            callback_received_at_utc=self.callback_time,
            callback_mark=1,
            callback_index=TV.CALLBACK_INDEX,
            returned_market_no=self.request.market_no,
            returned_stock_code=self.request.stock_code,
        )
        self.emitted = True
        if self.on_tick_detail_callback is not None:
            self.on_tick_detail_callback(1, self.result)

    def latest_tick_detail_exchange(self):
        if self.request is not None and self.callback is not None:
            return self.request, self.callback
        return None


def _cfg(enabled=True):
    return {
        "recording": {"max_dynamic_subscriptions": 2},
        "dynamic_requests": {"enabled": True, "allowed_markets": [207]},
        "tick_detail_measurements": {
            "enabled": enabled,
            "timeout_seconds": 1,
            "max_last_count": 20,
            "raw_dir": "evidence/tick_detail/raw",
            "evidence_dir": "evidence/tick_detail/verification",
        },
    }


def test_ose_local_timestamp_crosscheck_distinguishes_near_close_local_clock():
    check = TV.crosscheck_ose_local_timestamp_basis(
        _batch(),
        request_time=_dt(6, 45, 30),
        callback_received_at=_dt(6, 46),
    )
    assert check["status"] == TV.CROSSCHECK_PASS
    assert check["timestamp_crosscheck_passed"] is True
    assert check["timestamp_basis_status"] == TD.TIMESTAMP_BASIS_RUNTIME_VERIFIED
    assert check["values_exposed"] is False


def test_ose_local_timestamp_crosscheck_rejects_utc_like_raw_clock():
    check = TV.crosscheck_ose_local_timestamp_basis(
        _batch(raw_hour=6, raw_minute=44),
        request_time=_dt(6, 45, 30),
        callback_received_at=_dt(6, 46),
    )
    assert check["status"] == TV.CROSSCHECK_BLOCKED
    assert "NO_NEAR_CLOSE_TRADE_FOR_BASIS_CROSSCHECK" in check["reason"]
    assert "UTC_ALTERNATIVE_NOT_DISPROVEN" in check["reason"]


def test_measurement_is_disabled_by_default_and_does_not_touch_api(tmp_path, monkeypatch):
    rt = _FakeRuntime()
    monkeypatch.setattr(R, "_utcnow", lambda: _dt(6, 45, 30))
    ok, result = R._tick_detail_measurement(
        tmp_path, _cfg(enabled=False), rt, "MASKED_TEST_ACCOUNT",
        {"market_no": 207, "symbol": "JNU2612", "last_count": 20},
    )
    assert ok is False
    assert result["status"] == "TICK_DETAIL_MEASUREMENT_DISABLED"
    assert rt.calls == []


def test_measurement_outside_controlled_window_never_calls_api(tmp_path, monkeypatch):
    rt = _FakeRuntime()
    monkeypatch.setattr(R, "_utcnow", lambda: _dt(6, 44, 59))
    ok, result = R._tick_detail_measurement(
        tmp_path, _cfg(enabled=True), rt, "MASKED_TEST_ACCOUNT",
        {"market_no": 207, "symbol": "JNU2612", "last_count": 20},
    )
    assert ok is False
    assert result["status"] == "TICK_DETAIL_MEASUREMENT_OUTSIDE_WINDOW"
    assert rt.calls == []


def test_measurement_rejects_existing_unmatched_request(tmp_path, monkeypatch):
    rt = _FakeRuntime()
    rt.pending_trace = "tick_detail_old"
    monkeypatch.setattr(R, "_utcnow", lambda: _dt(6, 45, 30))
    ok, result = R._tick_detail_measurement(
        tmp_path, _cfg(enabled=True), rt, "MASKED_TEST_ACCOUNT",
        {"market_no": 207, "symbol": "JNU2612", "last_count": 20},
    )
    assert ok is False
    assert result["status"] == "TICK_DETAIL_MEASUREMENT_REQUEST_ALREADY_PENDING"
    assert rt.calls == []


def test_same_owner_measurement_records_raw_and_typed_evidence(tmp_path, monkeypatch):
    rt = _FakeRuntime()
    monkeypatch.setattr(R, "_utcnow", lambda: _dt(6, 45, 30))
    ok, result = R._tick_detail_measurement(
        tmp_path, _cfg(enabled=True), rt, "MASKED_TEST_ACCOUNT",
        {"market_no": 207, "symbol": "JNU2612", "last_count": 20},
    )
    assert ok is True
    assert result["status"] == "TICK_DETAIL_RUNTIME_EVIDENCE_RECORDED"
    assert result["values_exposed"] is False
    assert "price" not in json.dumps(result).lower()
    raw = tmp_path / result["raw_artifact"]
    evidence = tmp_path / result["evidence_artifact"]
    assert raw.exists() and evidence.exists()
    raw_payload = json.loads(raw.read_text(encoding="utf-8"))
    evidence_payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert raw_payload["source_snapshot_id"] == result["source_snapshot_id"]
    assert raw_payload["rows"][-1]["deal_price"] == 65905.0
    assert evidence_payload["evidence_id"] == result["evidence_id"]
    assert evidence_payload["runtime_build_id"]
    assert "deal_price" not in evidence_payload

    loaded_batch, loaded_evidence = TV.load_runtime_measurement(raw, evidence)
    materialized = TCM.materialize_ose_terminal_close(
        loaded_batch,
        contract_month="202612",
        verification_evidence=loaded_evidence,
        store=FeatureStore(root=tmp_path / "feature-store"),
    )
    assert materialized.status == TCM.STATUS_MATERIALIZED
    assert materialized.source_snapshot_ids == (
        loaded_batch.source_snapshot_id,
        loaded_evidence.evidence_id,
    )


def test_dynamic_control_action_writes_metadata_only_result(tmp_path, monkeypatch):
    rt = _FakeRuntime()
    monkeypatch.setattr(R, "_utcnow", lambda: _dt(6, 45, 30))
    inbox = tmp_path / "control/inbox"
    inbox.mkdir(parents=True)
    request = {
        "action": "tick_detail_measurement",
        "market_no": 207,
        "symbol": "JNU2612",
        "last_count": 20,
    }
    (inbox / "measure.json").write_text(json.dumps(request), encoding="utf-8")
    R._dynamic_requests(tmp_path, _cfg(enabled=True), rt, "MASKED_TEST_ACCOUNT", {})
    result_path = tmp_path / "control/processed/measure.result.json"
    assert result_path.exists()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "TICK_DETAIL_RUNTIME_EVIDENCE_RECORDED"
    assert payload["values_exposed"] is False
    assert "price" not in json.dumps(payload).lower()


def test_measurement_loader_rejects_tampered_raw_artifact(tmp_path, monkeypatch):
    rt = _FakeRuntime()
    monkeypatch.setattr(R, "_utcnow", lambda: _dt(6, 45, 30))
    ok, result = R._tick_detail_measurement(
        tmp_path, _cfg(enabled=True), rt, "MASKED_TEST_ACCOUNT",
        {"market_no": 207, "symbol": "JNU2612", "last_count": 20},
    )
    assert ok is True
    raw = tmp_path / result["raw_artifact"]
    evidence = tmp_path / result["evidence_artifact"]
    payload = json.loads(raw.read_text(encoding="utf-8"))
    payload["rows"][-1]["deal_price"] = 1.0
    raw.write_text(json.dumps(payload), encoding="utf-8")
    try:
        TV.load_runtime_measurement(raw, evidence)
    except ValueError as exc:
        assert "SOURCE_SNAPSHOT_ID_CANONICAL_MISMATCH" in str(exc)
    else:
        raise AssertionError("tampered raw artifact unexpectedly accepted")


def test_ose_local_timestamp_crosscheck_rejects_taipei_like_raw_clock():
    check = TV.crosscheck_ose_local_timestamp_basis(
        _batch(raw_hour=14, raw_minute=44),
        request_time=_dt(6, 45, 30),
        callback_received_at=_dt(6, 46),
    )
    assert check["status"] == TV.CROSSCHECK_BLOCKED
    assert "NO_NEAR_CLOSE_TRADE_FOR_BASIS_CROSSCHECK" in check["reason"]


def test_measurement_path_traversal_blocks_before_api(tmp_path, monkeypatch):
    rt = _FakeRuntime()
    cfg = _cfg(enabled=True)
    cfg["tick_detail_measurements"]["raw_dir"] = "../escape"
    monkeypatch.setattr(R, "_utcnow", lambda: _dt(6, 45, 30))
    try:
        R._tick_detail_measurement(
            tmp_path, cfg, rt, "MASKED_TEST_ACCOUNT",
            {"market_no": 207, "symbol": "JNU2612", "last_count": 20},
        )
    except ValueError as exc:
        assert "path must stay within recorder root" in str(exc)
    else:
        raise AssertionError("path traversal unexpectedly accepted")
    assert rt.calls == []


def test_measurement_loader_rejects_non_boolean_evidence_flags(tmp_path, monkeypatch):
    rt = _FakeRuntime()
    monkeypatch.setattr(R, "_utcnow", lambda: _dt(6, 45, 30))
    ok, result = R._tick_detail_measurement(
        tmp_path, _cfg(enabled=True), rt, "MASKED_TEST_ACCOUNT",
        {"market_no": 207, "symbol": "JNU2612", "last_count": 20},
    )
    assert ok is True
    raw = tmp_path / result["raw_artifact"]
    evidence = tmp_path / result["evidence_artifact"]
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["request_accepted"] = "false"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    try:
        TV.load_runtime_measurement(raw, evidence)
    except ValueError as exc:
        assert "REQUEST_ACCEPTED_MUST_BE_BOOL" in str(exc)
    else:
        raise AssertionError("non-boolean request_accepted unexpectedly accepted")


def test_measurement_blocks_when_running_process_build_is_stale(tmp_path, monkeypatch):
    rt = _FakeRuntime()
    monkeypatch.setattr(R, "_utcnow", lambda: _dt(6, 45, 30))
    monkeypatch.setattr(R, "_disk_build_id", lambda: "DISK_BUILD_NEW")
    ok, result = R._tick_detail_measurement(
        tmp_path, _cfg(enabled=True), rt, "MASKED_TEST_ACCOUNT",
        {"market_no": 207, "symbol": "JNU2612", "last_count": 20},
        runtime_build_id="PROCESS_BUILD_OLD",
    )
    assert ok is False
    assert result["status"] == "TICK_DETAIL_MEASUREMENT_RUNTIME_BUILD_STALE"
    assert rt.calls == []


def test_measurement_does_not_retry_same_contract_in_one_process(tmp_path, monkeypatch):
    rt = _FakeRuntime()
    rt.pending_trace = None
    rt.tick_detail_runtime_traces = lambda: {
        "requests": [{
            "request_id": "tick_detail_old",
            "market_no": 207,
            "stock_code": "JNU2612",
            "last_count": 20,
            "accepted": True,
        }],
        "callbacks": [{"request_id": "tick_detail_old"}],
    }
    monkeypatch.setattr(R, "_utcnow", lambda: _dt(6, 45, 30))
    ok, result = R._tick_detail_measurement(
        tmp_path, _cfg(enabled=True), rt, "MASKED_TEST_ACCOUNT",
        {"market_no": 207, "symbol": "JNU2612", "last_count": 20},
    )
    assert ok is False
    assert result["status"] == "TICK_DETAIL_MEASUREMENT_ALREADY_ATTEMPTED_IN_PROCESS"
    assert rt.calls == []


def test_runtime_verification_requirements_include_c2_2_provenance():
    req = TD.runtime_verification_requirements()
    assert req["runtime_evidence_schema_version"] == "W3.3-C2.2"
    assert req["controlled_measurement_default_enabled"] is False
    joined = " ".join(req["required_checks"])
    assert "runtime process build id" in joined
    assert "no prior same-contract" in joined
    assert "persisted and reload-validated" in joined
