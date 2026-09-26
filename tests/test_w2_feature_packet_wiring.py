"""W2 offline wiring: persisted quote -> V2-A.2 -> FeatureStore -> public packet provenance."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import pytest
import yaml

from market_ai_hub.automation.data_lake import default_data_root
from market_ai_hub.feature_store.store import FeatureStore
from market_ai_hub.integrations.yuanta.quote_reader import quote_to_factor_observation
from market_ai_hub.packet.builder import build_analysis_packet, clear_caches

ASOF = datetime(2026, 9, 24, 16, 32, 55, tzinfo=timezone.utc)


def _config(tmp_path: Path) -> Path:
    p = tmp_path / "reader.yaml"
    p.write_text(yaml.safe_dump({
        "subscriptions": [{
            "key": "ose_micro",
            "factor": "JP_EQUITY",
            "representation": "OSE_MICRO_FUTURES",
            "market_no": 207,
            "code_prefix": "JNU",
            "session_variant": "BOTH",
        }],
        "daytime_context": [],
    }), encoding="utf-8")
    return p


def _quote(*, with_event_time: bool = True) -> dict:
    q = {
        "provider": "YUANTA_SPARK",
        "callback_type": "SubscribeWatchlistAll",
        "market_no": 207,
        "instrument_code": "JNUPM2612",
        "subscription_key": "ose_micro",
        "received_at": "2026-09-24T16:32:50+00:00",
        "DealPrice": 65645.0,
        "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
        "source_time_of_day": "01:32:50.000",
        "field_provenance": {
            "DealPrice": {
                "received_at": "2026-09-24T16:32:50+00:00",
                "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
                "source_time_of_day": "01:32:50.000",
                "callback_type": "flag",
            }
        },
        "freshness_semantics": "PER_FIELD_ONLY",
        "roll_status": "NONE",
    }
    if with_event_time:
        q["event_timestamp"] = "2026-09-24T16:32:49+00:00"
    return q


def _live_obs(tmp_path: Path, asof: datetime = ASOF):
    obs = quote_to_factor_observation(
        _quote(), field_kind="trade", asof=asof, config_path=_config(tmp_path)
    )
    assert obs.resolved_role == "DIRECT_LIVE"
    assert obs.staleness_status == "FRESH"
    return obs


def test_canonical_data_root_unifies_datalake_and_feature_store(tmp_path, monkeypatch):
    root = tmp_path / "external data root"
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(root))
    monkeypatch.delenv("MARKET_AI_HUB_DATA_ROOT", raising=False)

    assert default_data_root() == root
    assert FeatureStore().db_path == root / "feature_store" / "features.duckdb"


def test_legacy_data_root_alias_is_only_fallback(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy-root"
    monkeypatch.delenv("MARKET_AI_DATA_ROOT", raising=False)
    monkeypatch.setenv("MARKET_AI_HUB_DATA_ROOT", str(legacy))
    assert default_data_root() == legacy


def test_read_only_observation_query_does_not_create_store(tmp_path, monkeypatch):
    root = tmp_path / "data"
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(root))
    store = FeatureStore()
    assert store.latest_observations(as_of=ASOF, representation_ids=["OSE_MICRO_FUTURES"]) == []
    assert not store.db_path.exists()


def test_live_observation_snapshot_materializes_provenance_feature(tmp_path, monkeypatch):
    root = tmp_path / "data"
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(root))
    store = FeatureStore()
    obs = _live_obs(tmp_path)

    result = store.put_observation(obs, as_of=ASOF)
    assert result["snapshot_status"] == "STORED"
    assert result["model_feature_status"] == "MATERIALIZED"

    df = store.get("JNUPM2612", "quote_value", as_of=ASOF)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["representation_id"] == "OSE_MICRO_FUTURES"
    assert row["contract_code"] == "JNUPM2612"
    assert row["contract_month"] == "202612"
    assert row["resolved_role"] == "DIRECT_LIVE"
    assert row["timestamp_precision"] == "TICK_TIMESTAMP"
    assert row["lineage_id"] == result["lineage_id"]
    assert "yuanta_quote_" in row["source_snapshot_ids_json"]


def test_replay_is_idempotent_for_snapshot_and_feature(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    store = FeatureStore()
    obs = _live_obs(tmp_path)

    first = store.put_observation(obs, as_of=ASOF)
    second = store.put_observation(obs, as_of=ASOF)
    assert first["snapshot_status"] == "STORED"
    assert second["snapshot_status"] == "IDEMPOTENT"
    assert second["model_feature_status"] == "IDEMPOTENT_FEATURE"
    assert len(store.get("JNUPM2612", "quote_value", as_of=ASOF)) == 1


def test_unknown_event_time_is_kept_as_snapshot_but_not_model_feature(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    cfg = _config(tmp_path)
    record = _quote(with_event_time=False)
    record.pop("field_provenance")
    record.pop("freshness_semantics")
    obs = quote_to_factor_observation(record, field_kind="trade", asof=ASOF, config_path=cfg)
    assert obs.event_timestamp is None

    store = FeatureStore()
    result = store.put_observation(obs, as_of=ASOF)
    assert result["snapshot_status"] == "STORED"
    assert result["model_feature_status"] == "BLOCKED_EVENT_TIME_UNKNOWN"
    assert store.get("JNUPM2612", "quote_value", as_of=ASOF).empty

    rows = store.latest_observations(as_of=ASOF, representation_ids=["OSE_MICRO_FUTURES"])
    assert rows[0]["quality_status"].startswith("LEGACY_TOP_LEVEL_RECEIPT_ONLY")
    assert rows[0]["event_timestamp"] is None

    import market_ai_hub.packet.builder as b
    summary = b._factor_observation_summary("OSAKA_MICRO", ASOF)
    assert summary[0]["packet_freshness"] == "UNKNOWN"
    assert summary[0]["staleness_status_at_ingest"] == rows[0]["staleness_status"]


def test_stale_quote_is_not_materialized_as_live_feature(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    late = datetime(2026, 9, 24, 16, 34, 10, tzinfo=timezone.utc)
    obs = quote_to_factor_observation(
        _quote(), field_kind="trade", asof=late, config_path=_config(tmp_path)
    )
    assert obs.staleness_status != "FRESH"

    result = FeatureStore().put_observation(obs, as_of=late)
    assert result["snapshot_status"] == "STORED"
    assert result["model_feature_status"] != "MATERIALIZED"


def test_old_feature_store_migrates_non_destructively(tmp_path):
    db = tmp_path / "data" / "feature_store" / "features.duckdb"
    db.parent.mkdir(parents=True)
    with duckdb.connect(str(db)) as con:
        con.execute("""CREATE TABLE features (
            feature_name VARCHAR, symbol VARCHAR, event_time TIMESTAMP,
            available_at TIMESTAMP, feature_version VARCHAR, source VARCHAR,
            data_grade VARCHAR, value DOUBLE)""")
        con.execute(
            "INSERT INTO features VALUES (?,?,?,?,?,?,?,?)",
            ["close", "^N225", datetime(2026, 9, 1), datetime(2026, 9, 1),
             "v1", "panel", "RESEARCH_PROXY", 100.0],
        )
        con.execute("CREATE TABLE schema_meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
        con.execute("INSERT INTO schema_meta VALUES ('schema_version','1')")

    store = FeatureStore(root=tmp_path)
    store.init()
    df = store.get("^N225", "close", as_of=datetime(2026, 9, 2, tzinfo=timezone.utc))
    assert len(df) == 1 and df.iloc[0]["value"] == 100.0
    with duckdb.connect(str(db)) as con:
        version = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        columns = {r[1] for r in con.execute("PRAGMA table_info('features')").fetchall()}
    assert version == "2"
    assert {"lineage_id", "representation_id", "source_snapshot_ids_json"} <= columns


def test_packet_exposes_source_lineage_without_overriding_reference_price(tmp_path, monkeypatch):
    root = tmp_path / "data"
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(root))
    store = FeatureStore()
    inserted = store.put_observation(_live_obs(tmp_path), as_of=ASOF)

    import market_ai_hub.packet.builder as b

    monkeypatch.setattr(b, "_now", lambda: ASOF)
    monkeypatch.setattr(b, "_load_latest_micro_settlement", lambda: None)
    monkeypatch.setattr(b, "_proxy_reference", lambda: None)

    def panel():
        idx = pd.date_range("2026-01-01", periods=260, freq="B", tz="UTC")
        return pd.DataFrame({"^N225": range(260)}, index=idx)

    monkeypatch.setattr(b, "_regime_panel", panel)
    clear_caches()
    packet = build_analysis_packet(
        market="osaka", detail_level="compact", save_analysis=False
    )

    assert packet["target_data_status"] == "MISSING"
    assert "feature_store:v2_factor_observations" in packet["data_reused"]
    assert len(packet["factor_observation_summary"]) == 1
    summary = packet["factor_observation_summary"][0]
    assert summary["lineage_id"] == inserted["lineage_id"]
    assert summary["representation_id"] == "OSE_MICRO_FUTURES"
    assert summary["contract_code"] == "JNUPM2612"
    assert summary["source_snapshot_ids"]
    assert summary["packet_freshness"] == "FRESH"
    assert summary["model_feature_gate_at_ingest"] == "ELIGIBLE"
    assert not any("probability" in key.lower() for key in summary)


def test_latest_observations_opens_existing_store_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    store = FeatureStore()
    store.put_observation(_live_obs(tmp_path), as_of=ASOF)

    real_connect = duckdb.connect
    read_only_flags = []

    def tracked_connect(*args, **kwargs):
        read_only_flags.append(kwargs.get("read_only"))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", tracked_connect)
    rows = store.latest_observations(
        as_of=ASOF,
        representation_ids=["OSE_MICRO_FUTURES"],
    )
    assert rows
    assert read_only_flags == [True]


def test_latest_observations_corrupt_store_fails_closed(tmp_path, monkeypatch):
    root = tmp_path / "data"
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(root))
    store = FeatureStore()
    store.db_path.parent.mkdir(parents=True, exist_ok=True)
    store.db_path.write_bytes(b"not-a-duckdb-file")

    rows = store.latest_observations(
        as_of=ASOF,
        representation_ids=["OSE_MICRO_FUTURES"],
    )
    assert rows == []
