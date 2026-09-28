"""Accuracy v2 P0/P1: model governance, target contract, and one PIT factor."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import duckdb
import pytest

from market_ai_hub.feature_store.store import FeatureRecord, FeatureStore
from market_ai_hub.research.accuracy_v2_p1 import (
    PROTOCOL_VERSION,
    TARGET_NEXT_OSE_SETTLEMENT,
    TARGET_NEXT_PUBLISHED_SETTLEMENT,
    PredictionContract,
    PredictionContractError,
    build_pit_lagged_return_packet,
    cache_identity,
    make_jnu_contract,
)
from market_ai_hub.services.model_governance import (
    ModelRevisionMismatch,
    expected_model_revision,
    model_capability_inventory,
    model_use_gate,
    verify_loaded_revision,
)

JST = ZoneInfo("Asia/Tokyo")
DECISION = datetime(2026, 9, 18, 15, 45, tzinfo=JST)
FEATURE_VERSION = "accuracy-v2-test-1"
FACTOR_CONTRACT = "NQ_2612"


def _contract() -> PredictionContract:
    return make_jnu_contract(
        decision_time=DECISION,
        reference_price=65000.0,
        reference_price_available_at=datetime(2026, 9, 18, 6, 44, tzinfo=timezone.utc),
        exact_contract="JNU2612",
        target_measure=TARGET_NEXT_OSE_SETTLEMENT,
    )


def _insert_factor(
    store: FeatureStore,
    *,
    lineage: str,
    event: datetime,
    available: datetime,
    value: float,
    snapshot: str,
    relation: str = "DERIVATIVE_PROXY",
    stale: str = "FRESH",
    roll: str = "NONE",
    contract: str = FACTOR_CONTRACT,
    gate: str = "ELIGIBLE_DERIVED_DAILY",
) -> None:
    store.init()
    event_n = event.astimezone(timezone.utc).replace(tzinfo=None)
    available_n = available.astimezone(timezone.utc).replace(tzinfo=None)
    trading_date = event.astimezone(timezone.utc).date().isoformat()
    with duckdb.connect(str(store.db_path)) as con:
        con.execute(
            """
            INSERT INTO factor_observations VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                lineage, "US_TECH_RISK", "NQ_FUTURES", "FUTURE", relation,
                "PREVIOUS_SESSION", "PREVIOUS_SESSION_REFERENCE", "CME", "CME",
                "REGULAR_SESSION", trading_date, value, event_n, available_n,
                available_n, available_n, "BAR_CLOSE_TIMESTAMP", stale, "AVAILABLE",
                "SYNTHETIC_TEST", "SYNTHETIC", "TEST_FIXTURE", "1D", "SYNTHETIC",
                True, contract, "202612", roll, "CONTRACT",
                json.dumps([snapshot]), gate, "{}",
            ],
        )
    store.put(FeatureRecord(
        feature_name="quote_value",
        symbol=contract,
        event_time=event,
        available_at=available,
        feature_version=FEATURE_VERSION,
        source="SYNTHETIC:TEST_FIXTURE",
        data_grade="SYNTHETIC",
        value=value,
        lineage_id=lineage,
        economic_factor_id="US_TECH_RISK",
        representation_id="NQ_FUTURES",
        venue_id="CME",
        session_status="REGULAR_SESSION",
        trading_date=trading_date,
        timestamp_precision="BAR_CLOSE_TIMESTAMP",
        availability_status="AVAILABLE",
        quality_status="SYNTHETIC_TEST",
        resolved_role="PREVIOUS_SESSION_REFERENCE",
        point_in_time_safe=True,
        contract_code=contract,
        contract_month="202612",
        roll_status=roll,
        series_semantics="CONTRACT",
        source_snapshot_ids=[snapshot],
    ))


def _valid_store(tmp_path) -> FeatureStore:
    store = FeatureStore(root=tmp_path)
    _insert_factor(
        store,
        lineage="l1",
        event=datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc),
        available=datetime(2026, 9, 17, 20, 1, tzinfo=timezone.utc),
        value=24000.0,
        snapshot="s1",
    )
    _insert_factor(
        store,
        lineage="l2",
        event=datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc),
        available=datetime(2026, 9, 18, 5, 1, tzinfo=timezone.utc),
        value=24240.0,
        snapshot="s2",
    )
    return store


def _packet(store: FeatureStore, **kwargs):
    return build_pit_lagged_return_packet(
        contract=_contract(),
        representation_id="NQ_FUTURES",
        factor_contract=FACTOR_CONTRACT,
        feature_version=FEATURE_VERSION,
        evidence_origin="SYNTHETIC",
        store=store,
        model_revisions={"chronos-2": expected_model_revision("chronos-2")},
        **kwargs,
    )


def test_registry_separates_upstream_adapter_and_local_capability():
    inv = model_capability_inventory("chronos-2")
    assert inv["package_version"] == "2.3.2"
    assert inv["upstream_support"]["covariates"] is True
    assert inv["adapter_implemented"]["past_only_covariates"] is True
    assert inv["adapter_implemented"]["future_covariates"] is False
    assert inv["local_verified"]["covariates"] is False


def test_timesfm_research_allowed_serving_and_unknown_blocked():
    assert model_use_gate("timesfm-3.0", "RESEARCH")["allowed"] is True
    assert model_use_gate("timesfm-3.0", "SERVING")["allowed"] is False
    assert model_use_gate("timesfm-3.0", None)["allowed"] is False


def test_timesfm_adapter_default_purpose_is_fail_closed():
    from market_ai_hub.models.timesfm_model import TimesFM3Adapter

    assert TimesFM3Adapter(device="cpu").purpose == "UNKNOWN"


def test_chronos_load_passes_registry_revision(monkeypatch):
    expected = expected_model_revision("chronos-2")
    calls = {}
    loaded = SimpleNamespace(model=SimpleNamespace(config=SimpleNamespace(_commit_hash=expected)))

    class FakePipeline:
        @classmethod
        def from_pretrained(cls, model_id, **kwargs):
            calls.update(model_id=model_id, **kwargs)
            return loaded

    monkeypatch.setitem(sys.modules, "chronos", SimpleNamespace(BaseChronosPipeline=FakePipeline))
    from market_ai_hub.models.chronos_model import ChronosAdapter

    adapter = ChronosAdapter(device="cpu")
    adapter.load()
    assert calls["revision"] == expected
    assert adapter._revision_evidence["local_verified"] is True


def test_timesfm_load_passes_revision_and_research_gate(monkeypatch):
    expected = expected_model_revision("timesfm-3.0")
    calls = {}
    loaded = SimpleNamespace(config=SimpleNamespace(revision=expected))

    class FakeForecaster:
        @classmethod
        def from_pretrained(cls, model_id, **kwargs):
            calls.update(model_id=model_id, **kwargs)
            return loaded

    fake_module = SimpleNamespace(TimesFM3Forecaster=FakeForecaster)
    monkeypatch.setitem(sys.modules, "timesfm3.timesfm3_forecaster", fake_module)
    from market_ai_hub.models.timesfm_model import TimesFM3Adapter

    adapter = TimesFM3Adapter(device="cpu", purpose="RESEARCH")
    adapter.load()
    assert calls["revision"] == expected
    assert adapter._revision_evidence["local_verified"] is True


def test_runtime_revision_mismatch_fails_closed():
    loaded = SimpleNamespace(config=SimpleNamespace(revision="wrong-revision"))
    with pytest.raises(ModelRevisionMismatch):
        verify_loaded_revision("chronos-2", loaded)


def test_prediction_contract_rejects_late_reference_and_nowcast_masquerade():
    with pytest.raises(PredictionContractError, match="available after"):
        PredictionContract(
            decision_time=datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc),
            reference_price=1.0,
            reference_price_available_at=datetime(2026, 9, 18, 6, 1, tzinfo=timezone.utc),
            target_start=datetime(2026, 9, 18, 7, 0, tzinfo=timezone.utc),
            target_end=datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc),
            target_measure=TARGET_NEXT_OSE_SETTLEMENT,
            exact_contract="JNU2612",
            forecast_horizon="NEXT_OSE_SESSION",
            label_available_at=datetime(2026, 9, 19, 0, 0, tzinfo=timezone.utc),
        )
    with pytest.raises(PredictionContractError, match="nowcast"):
        PredictionContract(
            decision_time=datetime(2026, 9, 18, 7, 30, tzinfo=timezone.utc),
            reference_price=1.0,
            reference_price_available_at=datetime(2026, 9, 18, 7, 0, tzinfo=timezone.utc),
            target_start=datetime(2026, 9, 18, 7, 0, tzinfo=timezone.utc),
            target_end=datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc),
            target_measure=TARGET_NEXT_OSE_SETTLEMENT,
            exact_contract="JNU2612",
            forecast_horizon="NEXT_OSE_SESSION",
            label_available_at=datetime(2026, 9, 19, 0, 0, tzinfo=timezone.utc),
        )


def test_ose_holiday_session_and_publication_are_distinct_targets():
    settlement = _contract()
    published = make_jnu_contract(
        decision_time=DECISION,
        reference_price=65000.0,
        reference_price_available_at=datetime(2026, 9, 18, 6, 44, tzinfo=timezone.utc),
        exact_contract="JNU2612",
        target_measure=TARGET_NEXT_PUBLISHED_SETTLEMENT,
    )
    assert settlement.target_start.astimezone(JST).date().isoformat() == "2026-09-21"
    assert settlement.label_available_at.astimezone(JST).date().isoformat() == "2026-09-24"
    assert settlement.forecast_horizon == "NEXT_OSE_SESSION"
    assert published.forecast_horizon == "NEXT_PUBLISHED_OBSERVATION"
    assert published.target_start.astimezone(JST).date().isoformat() == "2026-09-24"
    assert published.target_measure != settlement.target_measure


def test_synthetic_pit_packet_is_engineering_pass_but_data_not_ready(tmp_path):
    packet = _packet(_valid_store(tmp_path))
    assert packet["engineering_status"] == "PASS"
    assert packet["data_status"] == "DATA_NOT_READY"
    assert packet["rejection_reason"] == "SYNTHETIC_ENGINEERING_ONLY"
    assert packet["features"]["factor_lagged_return"] == pytest.approx(0.01)
    assert packet["feature_available_at"] <= packet["decision_time"]
    assert "label" not in json.dumps(packet["features"]).lower()
    assert packet["source_identity"]["source_hash"]
    assert packet["cache_identity"]
    assert packet["source_identity"]["value_content_hash"]


def test_future_late_revision_does_not_change_past_packet(tmp_path):
    store = _valid_store(tmp_path)
    before = _packet(store)
    _insert_factor(
        store,
        lineage="future-revision",
        event=datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc),
        available=datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc),
        value=99999.0,
        snapshot="late-revision",
    )
    after = _packet(store)
    assert after["features"] == before["features"]
    assert after["cache_identity"] == before["cache_identity"]
    assert after["source_identity"]["lineage_ids"] == before["source_identity"]["lineage_ids"]


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        ({"stale": "STALE"}, "STALE"),
        ({"roll": "ROLLED"}, "ROLL_MISMATCH"),
        ({"relation": "SPOT_PROXY"}, "RELATION_MISMATCH"),
    ],
)
def test_stale_roll_and_proxy_mismatch_rejected(tmp_path, mutator, reason):
    store = FeatureStore(root=tmp_path)
    _insert_factor(
        store,
        lineage="l1",
        event=datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc),
        available=datetime(2026, 9, 17, 20, 1, tzinfo=timezone.utc),
        value=24000.0,
        snapshot="s1",
        **mutator,
    )
    _insert_factor(
        store,
        lineage="l2",
        event=datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc),
        available=datetime(2026, 9, 18, 5, 1, tzinfo=timezone.utc),
        value=24240.0,
        snapshot="s2",
        **mutator,
    )
    assert _packet(store)["rejection_reason"] == reason


def test_duplicate_timestamp_and_nonfinite_rejected(tmp_path):
    store = FeatureStore(root=tmp_path)
    event = datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc)
    _insert_factor(
        store, lineage="l1", event=event,
        available=datetime(2026, 9, 18, 5, 1, tzinfo=timezone.utc),
        value=24000.0, snapshot="s1",
    )
    _insert_factor(
        store, lineage="l2", event=event,
        available=datetime(2026, 9, 18, 5, 2, tzinfo=timezone.utc),
        value=24240.0, snapshot="s2",
    )
    assert _packet(store)["rejection_reason"] == "DUPLICATE_EVENT_TIME"

    store2 = FeatureStore(root=tmp_path / "inf")
    _insert_factor(
        store2, lineage="i1",
        event=datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc),
        available=datetime(2026, 9, 17, 20, 1, tzinfo=timezone.utc),
        value=24000.0, snapshot="s1",
    )
    _insert_factor(
        store2, lineage="i2",
        event=datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc),
        available=datetime(2026, 9, 18, 5, 1, tzinfo=timezone.utc),
        value=math.inf, snapshot="s2",
    )
    assert _packet(store2)["rejection_reason"] == "NONFINITE_VALUE"


def test_missing_bar_is_data_not_ready(tmp_path):
    store = FeatureStore(root=tmp_path)
    _insert_factor(
        store, lineage="l1",
        event=datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc),
        available=datetime(2026, 9, 18, 5, 1, tzinfo=timezone.utc),
        value=24000.0, snapshot="s1",
    )
    packet = _packet(store)
    assert packet["data_status"] == "DATA_NOT_READY"
    assert packet["rejection_reason"] == "INSUFFICIENT_HISTORY"


def test_missing_daily_bar_gap_is_rejected(tmp_path):
    store = FeatureStore(root=tmp_path)
    _insert_factor(
        store, lineage="g1",
        event=datetime(2026, 9, 10, 5, 0, tzinfo=timezone.utc),
        available=datetime(2026, 9, 10, 5, 1, tzinfo=timezone.utc),
        value=24000.0, snapshot="s1",
    )
    _insert_factor(
        store, lineage="g2",
        event=datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc),
        available=datetime(2026, 9, 18, 5, 1, tzinfo=timezone.utc),
        value=24240.0, snapshot="s2",
    )
    assert _packet(store)["rejection_reason"] == "MISSING_BAR_GAP"


def test_cross_venue_timezone_cutoff_is_absolute(tmp_path):
    packet = _packet(_valid_store(tmp_path))
    assert packet["decision_time"] == DECISION.astimezone(timezone.utc).isoformat()
    assert packet["feature_available_at"] < packet["decision_time"]


def test_cache_identity_invalidates_source_feature_model_and_protocol(tmp_path):
    packet = _packet(_valid_store(tmp_path))
    source = packet["source_identity"]
    feature = {
        "feature_name": "quote_value",
        "feature_version": FEATURE_VERSION,
        "formula": "latest_value/prior_value-1",
    }
    contract = _contract()
    base = cache_identity(
        contract=contract, source_identity=source, feature_identity=feature,
        model_revisions={"chronos-2": "r1"}, protocol_version=PROTOCOL_VERSION,
    )
    changed_source = cache_identity(
        contract=contract, source_identity={**source, "source_hash": "changed"},
        feature_identity=feature, model_revisions={"chronos-2": "r1"},
        protocol_version=PROTOCOL_VERSION,
    )
    changed_feature = cache_identity(
        contract=contract, source_identity=source,
        feature_identity={**feature, "feature_version": "v2"},
        model_revisions={"chronos-2": "r1"}, protocol_version=PROTOCOL_VERSION,
    )
    changed_model = cache_identity(
        contract=contract, source_identity=source, feature_identity=feature,
        model_revisions={"chronos-2": "r2"}, protocol_version=PROTOCOL_VERSION,
    )
    changed_protocol = cache_identity(
        contract=contract, source_identity=source, feature_identity=feature,
        model_revisions={"chronos-2": "r1"}, protocol_version="next",
    )
    assert len({base, changed_source, changed_feature, changed_model, changed_protocol}) == 5
