"""Accuracy v2 P3-B: official TAIFEX TMF forward-safe settlement path."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from market_ai_hub.feature_store.store import FeatureStore
from market_ai_hub.providers.base import ProviderError
from market_ai_hub.providers.taifex import (
    TaifexDailySnapshot,
    TaifexProvider,
    _parse_daily_csv,
    _validate_daily_range,
)
from market_ai_hub.research.accuracy_v2_p1 import (
    PredictionContract,
    TARGET_NEXT_OSE_SETTLEMENT,
    build_pit_lagged_return_packet,
)
from market_ai_hub.research.accuracy_v2_p3b_taifex import (
    FEATURE_NAME,
    FEATURE_VERSION,
    materialize_tmf_settlement_snapshot,
)


HEADER = (
    "交易日期,契約,到期月份(週別),開盤價,最高價,最低價,收盤價,漲跌價,漲跌%,成交量,"
    "結算價,未沖銷契約數,最後最佳買價,最後最佳賣價,歷史最高價,歷史最低價,"
    "是否因訊息面暫停交易,交易時段,價差對單式委託成交量"
)


def _body(settle_23: str = "48400", settle_24: str = "48884") -> str:
    return "\n".join(
        [
            HEADER,
            f"2026/09/23,TMF,202610,48000,48500,47900,48410,10,0.02%,100,{settle_23},1000,48400,48410,49000,39000,,一般,,",
            "2026/09/23,TMF,202610,48300,48400,48000,48100,-300,-0.62%,80,-,-,48100,48110,49000,39000,,盤後,,",
            f"2026/09/24,TMF,202610,48420,48900,48300,48890,480,0.99%,120,{settle_24},1100,48880,48890,49000,39000,,一般,,",
            "2026/09/24,TMF,202610,48800,48900,48500,48600,-290,-0.59%,90,-,-,48600,48610,49000,39000,,盤後,,",
            "2026/09/24,TMF,202610/202611,10,20,5,15,0,0.00%,5,-,-,0,0,0,0,,一般,1,",
            "2026/09/23,TMF,202612,48000,48500,47900,48410,10,0.02%,10,0,100,48400,48410,49000,39000,,一般,,",
        ]
    )


def _snapshot(
    *,
    body: str | None = None,
    received_at: datetime | None = None,
    snapshot_id: str = "taifex-daily:test",
) -> TaifexDailySnapshot:
    frame = _parse_daily_csv(body or _body())
    return TaifexDailySnapshot(
        frame=frame,
        commodity="TMF",
        query_start="2026/09/23",
        query_end="2026/09/24",
        received_at=received_at or datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc),
        source_snapshot_id=snapshot_id,
    )


def test_taifex_daily_parser_repairs_official_trailing_empty_field_without_shift():
    frame = _parse_daily_csv(_body())
    assert len(frame.columns) == 19
    assert frame.iloc[0]["交易日期"] == "2026/09/23"
    assert frame.iloc[0]["契約"] == "TMF"
    assert frame.iloc[0]["到期月份(週別)"] == "202610"
    assert frame.iloc[0]["結算價"] == "48400"
    assert frame.iloc[1]["交易時段"] == "盤後"


def test_taifex_provider_rejects_html_and_more_than_one_month_before_network():
    with pytest.raises(ProviderError, match="HTML"):
        _parse_daily_csv("<!DOCTYPE html><html><script>alert('日期時間錯誤')</script></html>")

    _validate_daily_range("2026/09/01", "2026/10/01")
    with pytest.raises(ProviderError, match="one-month"):
        _validate_daily_range("2026/09/01", "2026/10/02")

    provider = TaifexProvider()
    called = {"post": 0}

    def _post(*args, **kwargs):
        called["post"] += 1
        return _body()

    provider.client.post = _post
    with pytest.raises(ProviderError, match="one-month"):
        provider.fetch_daily_snapshot("TMF", start="2026/06/01", end="2026/09/25")
    assert called["post"] == 0


def test_taifex_snapshot_binds_content_and_receipt_time(tmp_path, monkeypatch):
    provider = TaifexProvider()
    cache = tmp_path / "cache.json"
    cache.write_text(_body(), encoding="utf-8")
    fixed = datetime(2026, 9, 27, 8, 30, tzinfo=timezone.utc).timestamp()
    import os

    os.utime(cache, (fixed, fixed))
    monkeypatch.setattr(provider.client, "post", lambda *a, **k: _body())
    monkeypatch.setattr(provider.client, "_cache_path", lambda key: cache)
    snap = provider.fetch_daily_snapshot(
        "TMF",
        start="2026/09/23",
        end="2026/09/24",
    )
    assert snap.received_at == datetime.fromtimestamp(fixed, tz=timezone.utc)
    assert snap.source_snapshot_id.startswith("taifex-daily:")
    assert snap.frame.iloc[0]["交易日期"] == "2026/09/23"


def test_p3b_materializes_exact_contract_with_receipt_time_not_backdated(tmp_path):
    store = FeatureStore(root=tmp_path)
    snap = _snapshot()
    out = materialize_tmf_settlement_snapshot(snap, store=store)
    assert out["retroactive_availability_used"] is False
    assert out["ignored_non_regular_rows"] == 2
    assert out["ignored_non_exact_contract_rows"] == 1
    assert out["ignored_invalid_settlement_rows"] == 1
    assert out["counts"]["MATERIALIZED"] == 2
    assert out["contracts"] == ["TMF202610"]

    with store._conn() as con:
        rows = con.execute(
            """SELECT f.event_time, f.available_at, f.contract_code, f.value,
                      o.received_at, o.roll_status, o.series_semantics,
                      o.model_feature_gate_at_ingest, o.staleness_status
               FROM features f
               JOIN factor_observations o ON o.lineage_id=f.lineage_id
               WHERE f.representation_id='TMF_FUTURES'
               ORDER BY f.event_time"""
        ).fetchall()
    assert len(rows) == 2
    assert {r[2] for r in rows} == {"TMF202610"}
    assert {r[5] for r in rows} == {"NONE"}
    assert {r[6] for r in rows} == {"CONTRACT"}
    assert {r[7] for r in rows} == {"ELIGIBLE_DERIVED_DAILY"}
    assert {r[8] for r in rows} == {"CLOSED_MARKET_REFERENCE"}
    expected_available = snap.received_at.replace(tzinfo=None)
    assert all(r[1] == expected_available for r in rows)
    assert all(r[4] == expected_available for r in rows)


def test_p3b_rerun_is_idempotent_and_changed_settlement_is_blocked(tmp_path):
    store = FeatureStore(root=tmp_path)
    first = materialize_tmf_settlement_snapshot(_snapshot(), store=store)
    assert first["counts"]["MATERIALIZED"] == 2

    again = materialize_tmf_settlement_snapshot(_snapshot(), store=store)
    assert again["counts"]["ALREADY_MATERIALIZED"] == 2

    revised = materialize_tmf_settlement_snapshot(
        _snapshot(
            body=_body(settle_24="49999"),
            received_at=datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc),
            snapshot_id="taifex-daily:revision",
        ),
        store=store,
    )
    assert revised["counts"]["ALREADY_MATERIALIZED"] == 1
    assert revised["counts"]["BLOCKED"] == 1
    assert any(
        r["reason"] == "REVISION_OR_DUPLICATE_CONFLICT"
        for r in revised["results"]
    )


def test_p3b_received_before_session_close_is_blocked(tmp_path):
    store = FeatureStore(root=tmp_path)
    snap = _snapshot(
        received_at=datetime(2026, 9, 23, 4, 0, tzinfo=timezone.utc),
    )
    out = materialize_tmf_settlement_snapshot(snap, store=store)
    assert out["counts"]["BLOCKED"] == 2
    assert all(r["reason"] == "RECEIVED_BEFORE_SESSION_CLOSE" for r in out["results"])


def test_real_p1_packet_becomes_data_ready_only_after_receipt(tmp_path):
    store = FeatureStore(root=tmp_path)
    snap = _snapshot()
    out = materialize_tmf_settlement_snapshot(snap, store=store)
    assert out["counts"]["MATERIALIZED"] == 2

    decision = snap.received_at + timedelta(minutes=30)
    contract = PredictionContract(
        decision_time=decision,
        reference_price=50000.0,
        reference_price_available_at=decision - timedelta(minutes=1),
        target_start=decision + timedelta(hours=1),
        target_end=decision + timedelta(hours=8),
        target_measure=TARGET_NEXT_OSE_SETTLEMENT,
        exact_contract="JNU2612",
        forecast_horizon="NEXT_OSE_SESSION",
        label_available_at=decision + timedelta(days=1),
    )
    packet = build_pit_lagged_return_packet(
        contract=contract,
        representation_id="TMF_FUTURES",
        factor_contract="TMF202610",
        feature_name=FEATURE_NAME,
        feature_version=FEATURE_VERSION,
        evidence_origin="REAL",
        store=store,
        model_revisions={},
    )
    assert packet["engineering_status"] == "PASS"
    assert packet["data_status"] == "DATA_READY"
    assert packet["rejection_reason"] is None
    assert packet["source_identity"]["exact_contract"] == "TMF202610"
    assert packet["feature_available_at"] == snap.received_at.isoformat()

    before = PredictionContract(
        decision_time=snap.received_at - timedelta(seconds=1),
        reference_price=50000.0,
        reference_price_available_at=snap.received_at - timedelta(minutes=1),
        target_start=snap.received_at + timedelta(hours=1),
        target_end=snap.received_at + timedelta(hours=8),
        target_measure=TARGET_NEXT_OSE_SETTLEMENT,
        exact_contract="JNU2612",
        forecast_horizon="NEXT_OSE_SESSION",
        label_available_at=snap.received_at + timedelta(days=1),
    )
    blocked = build_pit_lagged_return_packet(
        contract=before,
        representation_id="TMF_FUTURES",
        factor_contract="TMF202610",
        feature_name=FEATURE_NAME,
        feature_version=FEATURE_VERSION,
        evidence_origin="REAL",
        store=store,
        model_revisions={},
    )
    assert blocked["data_status"] == "DATA_NOT_READY"
    assert blocked["rejection_reason"] == "NO_QUALIFIED_HISTORY"
