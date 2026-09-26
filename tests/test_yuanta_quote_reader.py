"""Offline W2 reader/replay tests. No broker/SDK/login operations."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from market_ai_hub.research.v2.prediction_audit import lineage_from_observation
from market_ai_hub.integrations.yuanta import live_quote_recorder as R

from market_ai_hub.integrations.yuanta.quote_reader import (
    QuoteReaderError,
    extract_field,
    quote_to_factor_observation,
    read_latest,
    replay_parquet,
)


ASOF = datetime(2026, 9, 24, 16, 33, 0, tzinfo=timezone.utc)


def _config(tmp_path):
    p = tmp_path / "reader.yaml"
    p.write_text(yaml.safe_dump({
        "subscriptions": [
            {"key": "ose_micro", "factor": "JP_EQUITY", "representation": "OSE_MICRO_FUTURES",
             "market_no": 207, "code_prefix": "JNU", "session_variant": "BOTH"},
            {"key": "cme_nq", "factor": "US_TECH_RISK", "representation": "NQ_FUTURES",
             "market_no": 203, "code_prefix": "NQ_"},
        ],
        "daytime_context": [],
    }), encoding="utf-8")
    return p


def _quote(**overrides):
    base = {
        "provider": "YUANTA_SPARK",
        "callback_type": "SubscribeWatchlistAll",
        "market_no": 207,
        "instrument_code": "JNUPM2612",
        "subscription_key": "ose_micro",
        "received_at": "2026-09-24T16:32:50+00:00",
        "DealPrice": 65645.0,
        "BuyPrice": 65640.0,
        "SellPrice": 65650.0,
        "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
        "source_time_of_day": "01:32:50.000",
        "field_provenance": {
            "DealPrice": {"received_at": "2026-09-24T16:31:00+00:00",
                          "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
                          "source_time_of_day": "01:31:00.000", "callback_type": "x"},
            "BuyPrice": {"received_at": "2026-09-24T16:32:50+00:00",
                         "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
                         "source_time_of_day": "01:32:50.000", "callback_type": "x"},
            "SellPrice": {"received_at": "2026-09-24T16:32:49+00:00",
                          "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
                          "source_time_of_day": "01:32:49.000", "callback_type": "x"},
        },
        "freshness_semantics": "PER_FIELD_ONLY",
        "roll_status": "NONE",
    }
    base.update(overrides)
    return base


def test_stale_trade_fresh_bid_use_independent_field_provenance(tmp_path):
    cfg = _config(tmp_path)
    trade = quote_to_factor_observation(_quote(), field_kind="trade", asof=ASOF, config_path=cfg)
    bid = quote_to_factor_observation(_quote(), field_kind="bid", asof=ASOF, config_path=cfg)
    assert trade.received_at.isoformat().startswith("2026-09-24T16:31:00")
    assert bid.received_at.isoformat().startswith("2026-09-24T16:32:50")
    assert trade.quote_age_seconds > bid.quote_age_seconds
    assert trade.quality_status == "PER_FIELD_VERIFIED"
    assert bid.quality_status == "PER_FIELD_VERIFIED"
    assert trade.event_timestamp is None and bid.event_timestamp is None
    assert trade.resolved_role != "DIRECT_LIVE" and bid.resolved_role != "DIRECT_LIVE"

    assert trade.source_type == "BROKER_TRADE_QUOTE_REPLAY"
    assert bid.source_type == "BROKER_BID_QUOTE_REPLAY"
    assert trade.source_version.endswith(":DealPrice")
    assert bid.source_version.endswith(":BuyPrice")


def test_trade_alias_uses_newest_per_field_provenance():
    record = _quote(deal=65655.0)
    record["field_provenance"]["deal"] = {
        "received_at": "2026-09-24T16:32:55+00:00",
        "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
        "source_time_of_day": "01:32:55.000",
        "callback_type": "flag29",
    }
    field = extract_field(record, "trade")
    assert field.source_field == "deal"
    assert field.value == 65655.0
    assert field.received_at.isoformat().startswith("2026-09-24T16:32:55")


def test_source_time_of_day_never_gets_fake_date_and_session_is_v2_truth(tmp_path):
    obs = quote_to_factor_observation(_quote(), field_kind="trade", asof=ASOF, config_path=_config(tmp_path))
    assert obs.event_timestamp is None
    assert obs.timestamp_precision == "UNKNOWN"
    assert obs.session.session_status == "NIGHT_SESSION"
    assert obs.session.trading_date


def test_spark_day_code_is_rejected_during_ose_night_session(tmp_path):
    with pytest.raises(QuoteReaderError, match="SESSION_VARIANT_MISMATCH"):
        quote_to_factor_observation(
            _quote(instrument_code="JNU2612"),
            field_kind="trade",
            asof=ASOF,
            config_path=_config(tmp_path),
        )


def test_wrong_market_contract_and_unknown_product_fail_closed(tmp_path):
    cfg = _config(tmp_path)
    with pytest.raises(QuoteReaderError, match="MARKET_MISMATCH"):
        quote_to_factor_observation(_quote(market_no=203), field_kind="trade", asof=ASOF, config_path=cfg)
    with pytest.raises(QuoteReaderError, match="CONTRACT_MISMATCH"):
        quote_to_factor_observation(_quote(instrument_code="NQ_2612"), field_kind="trade", asof=ASOF, config_path=cfg)
    with pytest.raises(QuoteReaderError, match="UNKNOWN_SUBSCRIPTION_KEY"):
        quote_to_factor_observation(_quote(subscription_key="mystery"), field_kind="trade", asof=ASOF, config_path=cfg)


def test_legacy_schema_degrades_instead_of_claiming_field_freshness(tmp_path):
    record = _quote()
    record.pop("field_provenance")
    record.pop("freshness_semantics")
    field = extract_field(record, "trade")
    assert field.provenance_status == "LEGACY_TOP_LEVEL_RECEIPT_ONLY"
    obs = quote_to_factor_observation(record, field_kind="trade", asof=ASOF, config_path=_config(tmp_path))
    assert obs.quality_status.startswith("LEGACY_TOP_LEVEL_RECEIPT_ONLY")
    assert obs.resolved_role != "DIRECT_LIVE"


def test_missing_receipt_time_is_rejected(tmp_path):
    record = _quote()
    record["field_provenance"]["DealPrice"].pop("received_at")
    with pytest.raises(QuoteReaderError, match="MISSING_TRADE_RECEIVED_AT"):
        quote_to_factor_observation(record, field_kind="trade", asof=ASOF, config_path=_config(tmp_path))


def test_partial_file_write_failure_and_overflow_are_rejected(tmp_path):
    cfg = _config(tmp_path)
    partial = tmp_path / "part.partial"
    partial.write_bytes(b"not parquet")
    with pytest.raises(QuoteReaderError, match="PARTIAL_OR_UNSUPPORTED_FILE"):
        replay_parquet(partial, field_kind="trade", asof=ASOF, config_path=cfg)
    with pytest.raises(QuoteReaderError, match="PERSISTENCE_ERROR"):
        quote_to_factor_observation(_quote(), field_kind="trade", asof=ASOF,
                                    recorder_status={"persistence_error": "OSError"}, config_path=cfg)
    with pytest.raises(QuoteReaderError, match="BUFFER_OVERFLOW"):
        quote_to_factor_observation(_quote(), field_kind="trade", asof=ASOF,
                                    recorder_status={"dropped_records": 1}, config_path=cfg)


def test_durable_parquet_requires_committed_manifest(tmp_path):
    cfg = _config(tmp_path)
    row = {**_quote(), "_wal_seq": 1, "_wal_record_sha256": "a" * 64}
    p = tmp_path / "part-wal-test.parquet"
    pd.DataFrame([row]).to_parquet(p, index=False)
    with pytest.raises(QuoteReaderError, match="DURABLE_BATCH_MANIFEST_MISSING"):
        replay_parquet(p, field_kind="trade", asof=ASOF, config_path=cfg)


def test_durable_parquet_with_valid_manifest_replays(tmp_path):
    cfg = _config(tmp_path)
    row = {**_quote(), "_wal_seq": 1, "_wal_record_sha256": "a" * 64}
    p = R._write_parquet(tmp_path, [row], batch_id="wal-test")
    out = replay_parquet(Path(p), field_kind="trade", asof=ASOF, config_path=cfg)
    assert len(out) == 1
    assert out[0].contract_code == "JNUPM2612"


def test_durable_parquet_manifest_hash_mismatch_rejected(tmp_path):
    cfg = _config(tmp_path)
    row = {**_quote(), "_wal_seq": 1, "_wal_record_sha256": "a" * 64}
    p = Path(R._write_parquet(tmp_path, [row], batch_id="wal-test"))
    manifest_path = p.with_name(p.stem + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["parquet_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(QuoteReaderError, match="DURABLE_BATCH_MANIFEST_INVALID"):
        replay_parquet(p, field_kind="trade", asof=ASOF, config_path=cfg)


def test_out_of_order_parquet_receipts_rejected(tmp_path):
    cfg = _config(tmp_path)
    a = _quote()
    b = _quote()
    b["received_at"] = "2026-09-24T16:30:00+00:00"
    b["field_provenance"] = dict(b["field_provenance"])
    b["field_provenance"]["DealPrice"] = dict(b["field_provenance"]["DealPrice"])
    b["field_provenance"]["DealPrice"]["received_at"] = "2026-09-24T16:29:00+00:00"
    p = tmp_path / "part.parquet"
    pd.DataFrame([a, b]).to_parquet(p, index=False)
    with pytest.raises(QuoteReaderError, match="OUT_OF_ORDER_RECEIPT"):
        replay_parquet(p, field_kind="trade", asof=ASOF, config_path=cfg)


def test_latest_replay_is_deterministic_and_keeps_snapshot_lineage(tmp_path):
    cfg = _config(tmp_path)
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({"quotes": {"207:JNUPM2612": _quote()}}), encoding="utf-8")
    one = read_latest(latest, asof=ASOF, config_path=cfg)[0]
    two = read_latest(latest, asof=ASOF, config_path=cfg)[0]
    assert one.source_snapshot_ids == two.source_snapshot_ids
    assert one.contract_code == "JNUPM2612"
    assert one.contract_month == "202612"
    assert one.series_semantics == "CONTRACT"
    assert one.roll_status == "NONE"


def test_v2h_lineage_preserves_reader_quality_and_snapshot_ids(tmp_path):
    obs = quote_to_factor_observation(_quote(), field_kind="trade", asof=ASOF, config_path=_config(tmp_path))
    lineage = lineage_from_observation(obs)
    assert lineage.source_snapshot_ids == obs.source_snapshot_ids
    assert lineage.quality_status == obs.quality_status
    assert lineage.contract_code == obs.contract_code
    assert lineage.contract_month == obs.contract_month
    assert lineage.event_timestamp is None


def test_supported_subscription_key_with_missing_v2_representation_rejects(tmp_path):
    cfg = tmp_path / "reader.yaml"
    cfg.write_text(yaml.safe_dump({
        "subscriptions": [{"key": "cboe_vx", "factor": "US_VOLATILITY",
                           "representation": "VX_FUTURES", "market_no": 215, "code_prefix": "VX"}],
        "daytime_context": [],
    }), encoding="utf-8")
    with pytest.raises(QuoteReaderError, match="UNSUPPORTED_V2_REPRESENTATION"):
        quote_to_factor_observation(
            _quote(subscription_key="cboe_vx", market_no=215, instrument_code="VX2610"),
            field_kind="trade", asof=ASOF, config_path=cfg,
        )
