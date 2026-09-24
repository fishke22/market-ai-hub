"""W2 model-input gate: broker TICK reaches the model boundary but cannot impersonate 1d bars."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from market_ai_hub.feature_store.model_input import build_model_input
from market_ai_hub.feature_store.store import FeatureStore
from market_ai_hub.integrations.yuanta.quote_reader import quote_to_factor_observation
from market_ai_hub.packet.builder import _model_input_readiness

BASE = datetime(2026, 9, 24, 16, 32, 55, tzinfo=timezone.utc)


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


def _record(*, code="JNUPM2612", value=65645.0,
            event="2026-09-24T16:32:49+00:00",
            received="2026-09-24T16:32:50+00:00") -> dict:
    return {
        "provider": "YUANTA_SPARK",
        "callback_type": "SubscribeWatchlistAll",
        "market_no": 207,
        "instrument_code": code,
        "subscription_key": "ose_micro",
        "received_at": received,
        "DealPrice": value,
        "event_timestamp": event,
        "field_provenance": {
            "DealPrice": {
                "received_at": received,
                "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
                "source_time_of_day": "01:32:50.000",
                "callback_type": "flag",
            }
        },
        "freshness_semantics": "PER_FIELD_ONLY",
        "roll_status": "NONE",
    }


def _store_obs(store: FeatureStore, cfg: Path, record: dict, *, asof=BASE):
    obs = quote_to_factor_observation(
        record, field_kind="trade", asof=asof, config_path=cfg
    )
    result = store.put_observation(obs, as_of=asof)
    assert result["model_feature_status"] in ("MATERIALIZED", "IDEMPOTENT_FEATURE")
    return obs


def test_missing_store_returns_status_without_creating_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    store = FeatureStore()
    result = build_model_input(
        "OSE_MICRO_FUTURES", as_of=BASE, requested_frequency="1D", store=store
    )
    assert result.status == "NO_FEATURE_STORE"
    assert not store.db_path.exists()


def test_tick_input_reaches_boundary_but_daily_model_abstains(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    store = FeatureStore()
    cfg = _config(tmp_path)
    _store_obs(store, cfg, _record())

    result = build_model_input(
        "OSE_MICRO_FUTURES",
        as_of=BASE,
        contract_code="JNUPM2612",
        requested_frequency="1D",
        min_points=1,
        store=store,
    )
    assert result.status == "INCOMPATIBLE_FREQUENCY"
    assert result.source_frequency == "TICK"
    public = result.public_status()
    assert public["values_exposed"] is False
    assert "series" not in public


def test_tick_compatible_input_is_homogeneous_and_lineaged(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    store = FeatureStore()
    cfg = _config(tmp_path)
    _store_obs(
        store, cfg,
        _record(value=65640, event="2026-09-24T16:32:47+00:00",
                received="2026-09-24T16:32:48+00:00"),
    )
    _store_obs(store, cfg, _record(value=65645))

    result = build_model_input(
        "OSE_MICRO_FUTURES",
        as_of=BASE,
        contract_code="JNUPM2612",
        requested_frequency="TICK",
        min_points=2,
        store=store,
    )
    assert result.status == "READY"
    assert result.row_count == 2
    assert result.series is not None
    assert result.series.tolist() == [65640.0, 65645.0]
    assert len(result.lineage_ids) == 2
    assert result.source_snapshot_ids


def test_min_history_gate_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    store = FeatureStore()
    cfg = _config(tmp_path)
    _store_obs(store, cfg, _record())

    result = build_model_input(
        "OSE_MICRO_FUTURES",
        as_of=BASE,
        contract_code="JNUPM2612",
        requested_frequency="TICK",
        min_points=20,
        store=store,
    )
    assert result.status == "INSUFFICIENT_HISTORY"
    assert result.row_count == 1
    assert result.series is None


def test_contracts_are_never_mixed_implicitly(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    store = FeatureStore()
    cfg = _config(tmp_path)
    _store_obs(
        store, cfg,
        _record(code="JNUPM2612", value=65645,
                event="2026-09-24T16:32:47+00:00",
                received="2026-09-24T16:32:48+00:00"),
    )
    _store_obs(store, cfg, _record(code="JNUPM2703", value=65700))

    result = build_model_input(
        "OSE_MICRO_FUTURES",
        as_of=BASE,
        requested_frequency="TICK",
        min_points=1,
        store=store,
    )
    assert result.status == "MIXED_CONTRACTS"


def test_cutoff_excludes_later_available_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    store = FeatureStore()
    cfg = _config(tmp_path)
    _store_obs(
        store, cfg,
        _record(value=65640, event="2026-09-24T16:32:47+00:00",
                received="2026-09-24T16:32:48+00:00"),
    )
    later_asof = datetime(2026, 9, 24, 16, 33, 5, tzinfo=timezone.utc)
    _store_obs(
        store, cfg,
        _record(value=65650, event="2026-09-24T16:33:00+00:00",
                received="2026-09-24T16:33:01+00:00"),
        asof=later_asof,
    )

    cutoff = datetime(2026, 9, 24, 16, 32, 55, tzinfo=timezone.utc)
    result = build_model_input(
        "OSE_MICRO_FUTURES",
        as_of=cutoff,
        contract_code="JNUPM2612",
        requested_frequency="TICK",
        min_points=1,
        store=store,
    )
    assert result.status == "READY"
    assert result.row_count == 1
    assert result.series.tolist() == [65640.0]


def test_duplicate_event_time_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    store = FeatureStore()
    cfg = _config(tmp_path)
    _store_obs(
        store, cfg,
        _record(value=65640, event="2026-09-24T16:32:49+00:00",
                received="2026-09-24T16:32:50+00:00"),
    )
    _store_obs(
        store, cfg,
        _record(value=65645, event="2026-09-24T16:32:49+00:00",
                received="2026-09-24T16:32:51+00:00"),
    )

    result = build_model_input(
        "OSE_MICRO_FUTURES",
        as_of=BASE,
        contract_code="JNUPM2612",
        requested_frequency="TICK",
        min_points=1,
        store=store,
    )
    assert result.status == "DUPLICATE_EVENT_TIME"


def test_packet_readiness_reports_current_daily_model_incompatibility(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path / "data"))
    store = FeatureStore()
    cfg = _config(tmp_path)
    _store_obs(store, cfg, _record())

    readiness = _model_input_readiness("OSAKA_MICRO", BASE)
    assert readiness["status"] == "INCOMPATIBLE_FREQUENCY"
    assert readiness["source_frequency"] == "TICK"
    assert readiness["requested_frequency"] == "1D"
    assert readiness["values_exposed"] is False


def test_taiwan_stock_has_no_broker_direct_target_mapping():
    readiness = _model_input_readiness("TAIWAN_STOCK", BASE)
    assert readiness["status"] == "NOT_APPLICABLE"
