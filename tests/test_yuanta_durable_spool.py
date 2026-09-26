"""Offline crash/replay tests for the Yuanta durable quote spool."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from market_ai_hub.integrations.yuanta import live_quote_recorder as R
from market_ai_hub.integrations.yuanta import durable_spool as DS
from market_ai_hub.integrations.yuanta.durable_spool import (
    DurableQuoteSpool,
    DurableSpoolCorruption,
    DurableSpoolFull,
)


def quote(n=1, price=100):
    return {
        "market_no": 207,
        "instrument_code": "TEST",
        "received_at": f"2026-09-26T00:00:{n:02d}+00:00",
        "timestamp_quality": "LOCAL_RECEIVE_TIME_ONLY",
        "callback_type": "quote",
        "DealPrice": price,
    }


def make_spool(root, *, max_bytes=1_000_000, max_records=100):
    return DurableQuoteSpool(
        root / "spool", max_bytes=max_bytes, max_records=max_records,
    )


def test_spool_append_restart_flush_and_ack(tmp_path):
    spool = make_spool(tmp_path)
    spool.append(quote(1, 100))
    spool.append(quote(2, 101))
    restarted = make_spool(tmp_path)
    assert [x.seq for x in restarted.peek(10)] == [1, 2]

    buffer = R.QuoteBuffer(100, spool=restarted)
    output = buffer.flush(tmp_path)

    frame = pd.read_parquet(output)
    assert frame["DealPrice"].tolist() == [100, 101]
    assert frame["_wal_seq"].tolist() == [1, 2]
    assert restarted.stats()["pending_records"] == 0
    assert restarted.stats()["acked_seq"] == 2
    ack = json.loads((tmp_path / "spool/ack.json").read_text(encoding="utf-8"))
    assert ack["acked_seq"] == 2
    assert ack["state_sha256"] == DS.ack_state_sha256(
        version=1, acked_seq=2, batch_id=ack["batch_id"],
    )
    manifests = list(tmp_path.rglob("*.manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "COMMITTED"
    assert manifest["record_count"] == 2
    assert manifest["input_sha256"]
    assert manifest["parquet_sha256"]


def test_crash_after_parquet_publish_before_ack_is_idempotent(tmp_path, monkeypatch):
    spool = make_spool(tmp_path)
    spool.append(quote(1, 100))
    spool.append(quote(2, 101))
    buffer = R.QuoteBuffer(100, spool=spool)

    monkeypatch.setattr(
        spool, "ack_through",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("synthetic ack crash")),
    )
    with pytest.raises(OSError, match="synthetic ack crash"):
        buffer.flush(tmp_path)

    first_files = list(tmp_path.rglob("*.parquet"))
    assert len(first_files) == 1
    restarted = make_spool(tmp_path)
    assert restarted.stats()["pending_records"] == 2
    R.QuoteBuffer(100, spool=restarted).flush(tmp_path)

    assert len(list(tmp_path.rglob("*.parquet"))) == 1
    assert restarted.stats()["pending_records"] == 0
    assert restarted.stats()["acked_seq"] == 2


def test_valid_partial_is_promoted_on_restart(tmp_path):
    spool = make_spool(tmp_path)
    record = spool.append(quote(1))
    partial = record.path.with_suffix(".json.partial")
    record.path.replace(partial)

    restarted = make_spool(tmp_path)
    assert restarted.stats()["pending_records"] == 1
    assert restarted.peek(1)[0].path.exists()
    assert not partial.exists()


def test_truncated_partial_fails_closed(tmp_path):
    pending = tmp_path / "spool/pending"
    pending.mkdir(parents=True)
    (pending / "00000000000000000001-x.json.partial").write_text("{", encoding="utf-8")
    with pytest.raises(DurableSpoolCorruption, match="invalid spool record"):
        make_spool(tmp_path)


def test_corrupt_committed_record_fails_closed(tmp_path):
    spool = make_spool(tmp_path)
    record = spool.append(quote(1, 100))
    envelope = json.loads(record.path.read_text(encoding="utf-8"))
    envelope["payload"]["DealPrice"] = 999
    record.path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(DurableSpoolCorruption, match="invalid spool record"):
        make_spool(tmp_path)


def test_corrupt_ack_state_fails_closed(tmp_path):
    (tmp_path / "spool").mkdir()
    (tmp_path / "spool/ack.json").write_text('{"version":1,"acked_seq":"bad"}', encoding="utf-8")
    with pytest.raises(DurableSpoolCorruption, match="invalid spool ack state"):
        make_spool(tmp_path)


def test_valid_looking_ack_tamper_fails_checksum(tmp_path):
    spool = make_spool(tmp_path)
    spool.append(quote(1))
    batch = spool.peek(1)
    spool.ack_through(1, batch_id=spool.batch_id(batch))
    ack_path = tmp_path / "spool/ack.json"
    ack = json.loads(ack_path.read_text(encoding="utf-8"))
    ack["acked_seq"] = 999
    ack_path.write_text(json.dumps(ack), encoding="utf-8")
    with pytest.raises(DurableSpoolCorruption, match="invalid spool ack state"):
        make_spool(tmp_path)


def test_durable_replace_permission_retry_is_bounded(tmp_path, monkeypatch):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_text("payload", encoding="utf-8")
    real_replace = DS.os.replace
    calls = []

    def flaky(src, dst):
        calls.append((src, dst))
        if DS.os.name == "nt" and len(calls) < 3:
            raise PermissionError("synthetic sharing violation")
        return real_replace(src, dst)

    monkeypatch.setattr(DS.os, "replace", flaky)
    DS.durable_replace(source, destination, attempts=3)
    assert destination.read_text(encoding="utf-8") == "payload"
    assert len(calls) == (3 if DS.os.name == "nt" else 1)


def test_sequence_gap_fails_closed(tmp_path):
    spool = make_spool(tmp_path)
    first = spool.append(quote(1))
    spool.append(quote(2))
    first.path.unlink()
    with pytest.raises(DurableSpoolCorruption, match="sequence gap"):
        make_spool(tmp_path)


def test_quota_failure_is_visible_and_latest_does_not_advance(tmp_path):
    spool = make_spool(tmp_path, max_records=1)
    buffer = R.QuoteBuffer(10, spool=spool)
    assert buffer.append(quote(1, 100)) is True
    assert buffer.append(quote(2, 999)) is False

    latest, pending, dropped = buffer.snapshot()
    assert pending == 1
    assert dropped == 1
    assert latest["207:TEST"]["DealPrice"] == 100
    durability = buffer.durability_status()
    assert durability["spool_error"] == "DurableSpoolFull"


def test_byte_quota_rejects_before_commit(tmp_path):
    spool = make_spool(tmp_path, max_bytes=50)
    with pytest.raises(DurableSpoolFull, match="byte quota"):
        spool.append(quote(1))
    assert spool.stats()["pending_records"] == 0
    assert not list((tmp_path / "spool/pending").glob("*.json"))


def test_missing_manifest_is_reconstructed_without_duplicate(tmp_path):
    records = [
        {**quote(1), "_wal_seq": 1, "_wal_record_sha256": "a" * 64},
        {**quote(2), "_wal_seq": 2, "_wal_record_sha256": "b" * 64},
    ]
    output = R._write_parquet(tmp_path, records, batch_id="wal-test")
    manifest = next(tmp_path.rglob("*.manifest.json"))
    manifest.unlink()

    again = R._write_parquet(tmp_path, records, batch_id="wal-test")
    assert again == output
    assert manifest.exists()
    assert len(list(tmp_path.rglob("*.parquet"))) == 1


def test_existing_durable_batch_identity_mismatch_fails_closed(tmp_path):
    records = [
        {**quote(1), "_wal_seq": 1, "_wal_record_sha256": "a" * 64},
    ]
    output = R._write_parquet(tmp_path, records, batch_id="wal-test")
    frame = pd.read_parquet(output)
    frame["_wal_record_sha256"] = ["c" * 64]
    frame.to_parquet(output, index=False)

    with pytest.raises(RuntimeError, match="identity mismatch"):
        R._write_parquet(tmp_path, records, batch_id="wal-test")


def test_manifest_without_parquet_fails_closed(tmp_path):
    out = tmp_path / "parquet" / R._utcnow().strftime("%Y-%m-%d")
    out.mkdir(parents=True)
    (out / "part-wal-test.manifest.json").write_text(
        json.dumps({"status": "COMMITTED"}), encoding="utf-8",
    )
    records = [
        {**quote(1), "_wal_seq": 1, "_wal_record_sha256": "a" * 64},
    ]
    with pytest.raises(RuntimeError, match="manifest exists without parquet"):
        R._write_parquet(tmp_path, records, batch_id="wal-test")


def recorder_config(tmp_path):
    cfg = {
        "enabled": True,
        "recording": {
            "raw_jsonl": False, "normalized_parquet": True,
            "max_buffer_records": 10, "parquet_flush_seconds": 30,
        },
        "durable_spool": {
            "enabled": True, "dir": "spool",
            "max_bytes": 1_000_000, "max_records": 10,
        },
        "storage": {"status_file": "status.json", "latest_file": "latest.json"},
        "dynamic_requests": {"enabled": False},
        "tick_detail_measurements": {"enabled": False},
        "subscriptions": [],
        "daytime_context": [],
    }
    path = tmp_path / "recorder.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def allow_offline_start(monkeypatch):
    class Guard:
        def scan(self):
            return {"gate": "PASS", "findings": []}

    monkeypatch.setattr(
        "market_ai_hub.integrations.yuanta.order_api_guard.OrderApiExposureGuard",
        Guard,
    )
    monkeypatch.setattr(
        R, "read_profile_credential",
        lambda _profile: SimpleNamespace(username="MASKED_TEST_ACCOUNT"),
    )
    monkeypatch.setattr(
        R, "read_profile_password",
        lambda _profile: "MASKED_TEST_SECRET",
    )
    monkeypatch.setattr(R, "resolve_default_subscriptions", lambda _cfg, *, asof=None: [])


def test_startup_replays_spool_before_runtime_instantiate(tmp_path, monkeypatch):
    config_path = recorder_config(tmp_path)
    make_spool(tmp_path, max_records=10).append(quote(1, 123))
    allow_offline_start(monkeypatch)
    observations = []

    class FailAfterReplayRuntime:
        def __init__(self):
            observations.append(("init", make_spool(tmp_path, max_records=10).stats()["pending_records"]))
        def instantiate(self):
            observations.append(("instantiate", make_spool(tmp_path, max_records=10).stats()["pending_records"]))
            raise RuntimeError("stop after replay")
        def connection_snapshot(self):
            return {"state": "INITIAL", "system_code": None, "faulted": False}
        def close(self):
            return None
        def dispose(self):
            return None

    monkeypatch.setattr(R, "SparkRuntime", FailAfterReplayRuntime)
    rc = R._run_locked(config_path, tmp_path)

    assert rc == 1
    assert observations == [("init", 1), ("instantiate", 0)]
    assert len(list(tmp_path.rglob("*.parquet"))) == 1
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "START_FAILED"
    assert status["startup_stage"] == "INSTANTIATE"
    assert status["crash_durability"] == "DURABLE_SPOOL_FSYNC_BEFORE_ACCEPT"
    assert status["spool_pending_records"] == 0


def test_corrupt_spool_blocks_before_credentials_or_broker(tmp_path, monkeypatch):
    config_path = recorder_config(tmp_path)
    pending = tmp_path / "spool/pending"
    pending.mkdir(parents=True)
    (pending / "00000000000000000001-bad.json").write_text("{", encoding="utf-8")

    monkeypatch.setattr(
        R, "read_profile_credential",
        lambda _profile: pytest.fail("credentials must not be read"),
    )
    monkeypatch.setattr(
        R, "SparkRuntime",
        lambda: pytest.fail("runtime must not be constructed"),
    )

    rc = R._run_locked(config_path, tmp_path)
    assert rc == 1
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "START_FAILED"
    assert status["startup_stage"] == "SPOOL_RECOVERY"
    assert status["fatal_error"] == "DurableSpoolCorruption"
    assert status["crash_durability"] == "DURABLE_SPOOL_FAIL_CLOSED"
