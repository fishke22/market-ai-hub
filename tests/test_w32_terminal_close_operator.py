"""W3.2 persisted-artifact DAILY terminal-close operator tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

import pytest

from market_ai_hub.feature_store.store import FeatureStore
from market_ai_hub.research.v2 import forward_cycle as FC
from market_ai_hub.research.v2 import terminal_close_materializer as TCM
from market_ai_hub.research.v2 import tick_detail_source as TD
from market_ai_hub.research.v2 import tick_detail_verification as TV

UTC = timezone.utc


def _dt(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 9, 24, hour, minute, second, tzinfo=UTC)


def _pair(recorder: Path) -> tuple[Path, Path]:
    raw = TD.TickDetailBatch(
        market_no=TD.OSE_MARKET_NO,
        stock_code="JNU2612",
        rows=[
            TD.TickDetailRow(
                raw_timestamp=datetime(2026, 9, 24, 15, 44, 58),
                deal_price=42000.0,
                deal_volume=1,
                buy_price=41995.0,
                sell_price=42005.0,
                seq_no=101,
                in_out_flag=0,
            ),
            TD.TickDetailRow(
                raw_timestamp=datetime(2026, 9, 24, 15, 45, 1),
                deal_price=42005.0,
                deal_volume=1844,
                buy_price=42000.0,
                sell_price=42010.0,
                seq_no=102,
                in_out_flag=0,
            ),
        ],
        received_at=_dt(6, 46),
    )
    batch = replace(raw, source_snapshot_id=TD.canonical_tick_detail_snapshot_id(raw))
    evidence = TV.build_ose_runtime_verification_evidence(
        batch,
        runtime_request_id="tick_detail_operator_test",
        runtime_build_id="TEST_BUILD_OPERATOR",
        request_time=_dt(6, 45, 30),
        callback_received_at=batch.received_at,
        requested_market_no=TD.OSE_MARKET_NO,
        requested_stock_code=batch.stock_code,
        last_count=20,
        request_accepted=True,
        callback_index=TV.CALLBACK_INDEX,
        callback_mark=1,
        returned_market_no=batch.market_no,
        returned_stock_code=batch.stock_code,
        timestamp_basis_status=TD.TIMESTAMP_BASIS_RUNTIME_VERIFIED,
        timestamp_basis_method=TV.TIMESTAMP_BASIS_METHOD_OSE_LOCAL_CLOCK,
        timestamp_crosscheck_passed=True,
    )
    raw_path = recorder / "evidence/tick_detail/raw" / f"{batch.source_snapshot_id}.json"
    evidence_path = (
        recorder / "evidence/tick_detail/verification" / f"{evidence.evidence_id}.json"
    )
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps({
        **batch.identity_payload(),
        "timestamp_basis_status": batch.timestamp_basis_status,
        "source_snapshot_id": batch.source_snapshot_id,
    }, default=str), encoding="utf-8")
    evidence_path.write_text(json.dumps(evidence.model_dump(), default=str), encoding="utf-8")
    return raw_path, evidence_path


def _load_cli():
    path = Path(__file__).resolve().parents[1] / "scripts/materialize_ose_terminal_close.py"
    spec = importlib.util.spec_from_file_location("materialize_ose_terminal_close_cli", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_artifact_pair_materializes_forward_ready_daily_close(tmp_path):
    recorder = tmp_path / "recorder"
    raw, evidence = _pair(recorder)
    store = FeatureStore(root=tmp_path / "fs")

    result = TCM.materialize_ose_terminal_close_from_artifacts(
        raw,
        evidence,
        expected_contract_code="JNU2612",
        store=store,
    )
    assert result.status == TCM.STATUS_MATERIALIZED
    assert result.contract_month == "202612"
    assert result.trading_date == "2026-09-24"
    assert result.source_snapshot_ids[0].startswith("w33_")
    assert result.close == pytest.approx(42005.0)

    snapshot, status = FC.osaka_forward_input_from_feature_store(
        as_of=_dt(7, 0),
        contract_code="JNU2612",
        store=store,
    )
    assert status["status"] == "READY"
    assert snapshot is not None
    assert snapshot.close == pytest.approx(42005.0)
    assert snapshot.source_frequency == "DAILY"
    assert snapshot.series_semantics == "CONTRACT"


def test_expected_contract_mismatch_blocks_before_feature_store_init(tmp_path):
    recorder = tmp_path / "recorder"
    raw, evidence = _pair(recorder)
    store = FeatureStore(root=tmp_path / "fs")

    result = TCM.materialize_ose_terminal_close_from_artifacts(
        raw,
        evidence,
        expected_contract_code="JNU2703",
        store=store,
    )
    assert result.status == TCM.STATUS_BLOCKED
    assert result.reason == "EXPECTED_CONTRACT_CODE_MISMATCH"
    assert not store.db_path.exists()


def test_tampered_raw_artifact_fails_before_feature_store_init(tmp_path):
    recorder = tmp_path / "recorder"
    raw, evidence = _pair(recorder)
    payload = json.loads(raw.read_text(encoding="utf-8"))
    payload["rows"][-1]["deal_price"] = 99999.0
    raw.write_text(json.dumps(payload), encoding="utf-8")
    store = FeatureStore(root=tmp_path / "fs")

    with pytest.raises(ValueError, match="SOURCE_SNAPSHOT_ID_CANONICAL_MISMATCH"):
        TCM.materialize_ose_terminal_close_from_artifacts(raw, evidence, store=store)
    assert not store.db_path.exists()


def test_cli_rejects_artifact_outside_recorder_root(tmp_path):
    cli = _load_cli()
    recorder = tmp_path / "recorder"
    recorder.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="ARTIFACT_OUTSIDE_RECORDER_ROOT"):
        cli._resolve_artifact(recorder, str(outside))


def test_cli_rejects_empty_artifact_path(tmp_path):
    cli = _load_cli()
    recorder = tmp_path / "recorder"
    recorder.mkdir()
    with pytest.raises(ValueError, match="ARTIFACT_PATH_REQUIRED"):
        cli._resolve_artifact(recorder, "")


def test_cli_success_writes_canonical_feature_store_without_exposing_close(
    tmp_path, monkeypatch, capsys,
):
    data_root = tmp_path / "data-root"
    recorder = data_root / "live/yuanta"
    raw, evidence = _pair(recorder)
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(data_root))
    cli = _load_cli()

    rc = cli.main([
        "--raw-artifact", raw.relative_to(recorder).as_posix(),
        "--evidence-artifact", evidence.relative_to(recorder).as_posix(),
        "--expected-contract-code", "JNU2612",
    ])
    assert rc == 0
    public = json.loads(capsys.readouterr().out)
    assert public["status"] == TCM.STATUS_MATERIALIZED
    assert public["contract_code"] == "JNU2612"
    assert public["contract_month"] == "202612"
    assert public["values_exposed"] is False
    assert "close" not in public
    assert (data_root / "feature_store/features.duckdb").exists()
