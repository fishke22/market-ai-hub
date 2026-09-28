from __future__ import annotations

from copy import deepcopy
import json

import pytest
import yaml

from market_ai_hub.research.taiwan_context_forward import (
    DEFAULT_PROTOCOL_PATH,
    PROTOCOL_SCHEMA_VERSION,
    TaiwanContextForwardProtocolError,
    _FROZEN_CHANNELS,
    load_taiwan_context_forward_protocol,
    summarize_taiwan_context_receipts,
)
from market_ai_hub.services.taiwan_context_receipts import TaiwanContextReceiptStore


def _snapshot(
    *,
    retrieved_at: str,
    cutoff: str = "2026-09-28T00:00:00Z",
    observation_period: str = "2026-09-24",
    provenance_suffix: str = "v1",
):
    channels = {}
    for channel, (provider, dataset, availability, factor_specs) in _FROZEN_CHANNELS.items():
        factors = {}
        for index, (factor_id, (units, period_semantics)) in enumerate(factor_specs.items()):
            factor_period = (
                "2026-08"
                if period_semantics == "REVENUE_MONTH"
                else "2026-08-24"
                if period_semantics == "ANNOUNCED_CORPORATE_ACTION"
                else observation_period
            )
            factors[factor_id] = {
                "factor_id": factor_id,
                "value": float(index + 1),
                "units": units,
                "observation_period": factor_period,
                "observation_period_semantics": period_semantics,
                "source": "FinMind",
                "source_dataset": dataset,
                "source_endpoint": "https://api.finmindtrade.com/api/v4/data",
                "published_at": None,
                "available_at": "2026-09-27T00:00:00Z",
                "retrieved_at": retrieved_at,
                "cutoff": cutoff,
                "PIT_eligible": True,
                "predictive_feature_allowed": False,
                "missing_reason": None,
                "provenance_hash": f"{channel}-{provenance_suffix}",
                "availability_semantics": availability,
            }
        channels[channel] = {
            "status": "AVAILABLE",
            "provider": provider,
            "dataset": dataset,
            "availability_semantics": availability,
            "pit_usable": True,
            "factors": factors,
        }
    return {
        "schema_version": "TAIWAN_STOCK_CONTEXT_V3",
        "source_semantics_version": "FINMIND_TWSE_RECEIPT_TARGET_CONTEXT_ASOF_V3",
        "symbol": "3706.TW",
        "stock_id": "3706",
        "cutoff": cutoff,
        "as_of": cutoff,
        "retrieved_at": retrieved_at,
        "role": "TARGET_CONTEXT_ONLY_NOT_PREDICTIVE_FEATURE",
        "predictive_feature_allowed": False,
        "historical_revision_safe": False,
        "channels": channels,
    }


def _write_protocol(tmp_path, mutate):
    raw = yaml.safe_load(DEFAULT_PROTOCOL_PATH.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "protocol.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def test_forward_protocol_freezes_candidate_and_blocked_semantics():
    protocol = load_taiwan_context_forward_protocol()
    assert protocol.protocol_id == "taiwan_context_forward_receipts_v1"
    assert len(protocol.candidates) == 28
    assert set(protocol.blocked_channels) == {"eps", "shareholding_concentration", "news"}
    assert protocol.raw["policy"]["predictive_feature_allowed"] is False
    assert protocol.raw["policy"]["predictive_experiment_data_ready"] is False


def test_forward_protocol_rejects_unit_or_safety_weakening(tmp_path):
    unit_path = _write_protocol(
        tmp_path,
        lambda raw: raw["protocol"]["tracked_channels"]["valuation"]["factors"][
            "pe_ratio"
        ].update({"units": "PERCENT"}),
    )
    with pytest.raises(TaiwanContextForwardProtocolError, match="units changed"):
        load_taiwan_context_forward_protocol(unit_path)

    safety_path = _write_protocol(
        tmp_path,
        lambda raw: raw["protocol"]["policy"].update(
            {"future_revision_backfill_allowed": True}
        ),
    )
    with pytest.raises(TaiwanContextForwardProtocolError, match="no-promotion"):
        load_taiwan_context_forward_protocol(safety_path)


def test_forward_protocol_rejects_unblocking_eps(tmp_path):
    path = _write_protocol(
        tmp_path,
        lambda raw: raw["protocol"]["blocked_channels"]["eps"].update(
            {"status": "TRACK_FORWARD_RECEIPTS"}
        ),
    )
    with pytest.raises(TaiwanContextForwardProtocolError, match="blocked channel weakened"):
        load_taiwan_context_forward_protocol(path)


def test_repeated_retrieval_and_revision_do_not_inflate_independent_observations(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    for retrieved_at, suffix in (
        ("2026-09-28T01:00:00Z", "v1"),
        ("2026-09-28T02:00:00Z", "v1"),
        ("2026-09-28T03:00:00Z", "v2"),
    ):
        store.capture(
            _snapshot(retrieved_at=retrieved_at, provenance_suffix=suffix),
            observed_at=retrieved_at,
        )

    inventory = summarize_taiwan_context_receipts(
        "3706",
        decision_time="2026-09-28T04:00:00Z",
        store=store,
    )
    pe = inventory["factors"]["pe_ratio"]
    assert inventory["receipt_count_total"] == 3
    assert pe["retrieval_count_as_of_decision"] == 3
    assert pe["source_version_count_as_of_decision"] == 2
    assert pe["independent_observation_count_as_of_decision"] == 1
    assert pe["repeated_retrieval_count_as_of_decision"] == 1
    assert pe["revised_observation_count_as_of_decision"] == 1
    assert inventory["predictive_experiment_data_ready"] is False


def test_new_period_is_independent_but_still_not_predictive_sample(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    store.capture(
        _snapshot(retrieved_at="2026-09-28T01:00:00Z", observation_period="2026-09-24"),
        observed_at="2026-09-28T01:00:00Z",
    )
    store.capture(
        _snapshot(
            retrieved_at="2026-09-29T01:00:00Z",
            cutoff="2026-09-29T00:00:00Z",
            observation_period="2026-09-25",
            provenance_suffix="v2",
        ),
        observed_at="2026-09-29T01:00:00Z",
    )
    inventory = summarize_taiwan_context_receipts(
        "3706", decision_time="2026-09-29T02:00:00Z", store=store
    )
    pe = inventory["factors"]["pe_ratio"]
    assert pe["independent_observation_count_as_of_decision"] == 2
    assert inventory["validation_claims"]["PREDICTIVE_GAIN"] is False
    assert inventory["predictive_feature_allowed"] is False


def test_receipt_time_blocks_future_leak_even_when_source_was_already_available(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    store.capture(
        _snapshot(retrieved_at="2026-09-28T03:00:00Z"),
        observed_at="2026-09-28T03:00:00Z",
    )
    before = summarize_taiwan_context_receipts(
        "3706", decision_time="2026-09-28T02:59:59Z", store=store
    )
    after = summarize_taiwan_context_receipts(
        "3706", decision_time="2026-09-28T03:00:00Z", store=store
    )
    assert before["factors"]["pe_ratio"]["independent_observation_count_as_of_decision"] == 0
    assert after["factors"]["pe_ratio"]["independent_observation_count_as_of_decision"] == 1
    assert after["factors"]["pe_ratio"]["latest_effective_replay_available_at"].startswith(
        "2026-09-28T03:00:00"
    )


def test_later_revision_is_invisible_to_earlier_decision(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    store.capture(
        _snapshot(retrieved_at="2026-09-28T01:00:00Z", provenance_suffix="v1"),
        observed_at="2026-09-28T01:00:00Z",
    )
    store.capture(
        _snapshot(retrieved_at="2026-09-28T03:00:00Z", provenance_suffix="v2"),
        observed_at="2026-09-28T03:00:00Z",
    )
    between = summarize_taiwan_context_receipts(
        "3706", decision_time="2026-09-28T02:00:00Z", store=store
    )
    after = summarize_taiwan_context_receipts(
        "3706", decision_time="2026-09-28T04:00:00Z", store=store
    )
    assert between["factors"]["pe_ratio"]["source_version_count_as_of_decision"] == 1
    assert after["factors"]["pe_ratio"]["source_version_count_as_of_decision"] == 2
    assert after["factors"]["pe_ratio"]["independent_observation_count_as_of_decision"] == 1


def test_future_malformed_receipt_cannot_change_past_inventory_status(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    store.capture(
        _snapshot(retrieved_at="2026-09-28T01:00:00Z"),
        observed_at="2026-09-28T01:00:00Z",
    )
    future = _snapshot(retrieved_at="2026-09-28T03:00:00Z", provenance_suffix="future")
    future["channels"]["valuation"]["factors"]["pe_ratio"]["units"] = "PERCENT"
    store.capture(future, observed_at="2026-09-28T03:00:00Z")

    past = summarize_taiwan_context_receipts(
        "3706", decision_time="2026-09-28T02:00:00Z", store=store
    )
    future_visible = summarize_taiwan_context_receipts(
        "3706", decision_time="2026-09-28T04:00:00Z", store=store
    )
    assert past["status"] == "READY_FOR_FORWARD_RECEIPT_ACCUMULATION"
    assert past["receipt_count_as_of_decision"] == 1
    assert past["receipt_count_total"] == 1
    assert len(past["receipt_ids"]) == 1
    assert all("future" not in receipt_id for receipt_id in past["receipt_ids"])
    assert future_visible["status"] == "BLOCKED_CANDIDATE_CONTRACT_MISMATCH"


def test_receipt_candidate_schema_drift_fails_closed(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    snapshot = _snapshot(retrieved_at="2026-09-28T01:00:00Z")
    snapshot["channels"]["valuation"]["factors"]["pe_ratio"]["units"] = "PERCENT"
    store.capture(snapshot, observed_at="2026-09-28T01:00:00Z")
    inventory = summarize_taiwan_context_receipts(
        "3706", decision_time="2026-09-28T02:00:00Z", store=store
    )
    assert inventory["status"] == "BLOCKED_CANDIDATE_CONTRACT_MISMATCH"
    assert any(
        item["factor_id"] == "pe_ratio" and item["reason"] == "UNITS_MISMATCH"
        for item in inventory["contract_violations"]
    )
    assert inventory["factors"]["pe_ratio"]["independent_observation_count_as_of_decision"] == 0


def test_inconsistent_pit_flag_fails_closed(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    snapshot = _snapshot(retrieved_at="2026-09-28T01:00:00Z")
    factor = snapshot["channels"]["valuation"]["factors"]["pe_ratio"]
    factor["available_at"] = "2026-09-29T00:00:00Z"
    factor["PIT_eligible"] = True
    store.capture(snapshot, observed_at="2026-09-28T01:00:00Z")
    inventory = summarize_taiwan_context_receipts(
        "3706", decision_time="2026-09-30T00:00:00Z", store=store
    )
    assert inventory["status"] == "BLOCKED_CANDIDATE_CONTRACT_MISMATCH"
    assert any(
        item["factor_id"] == "pe_ratio"
        and item["reason"] == "PIT_FLAG_INCONSISTENT_WITH_CUTOFF"
        for item in inventory["contract_violations"]
    )


def test_protocol_file_is_machine_readable_and_versioned():
    raw = yaml.safe_load(DEFAULT_PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert raw["schema_version"] == PROTOCOL_SCHEMA_VERSION
    assert json.loads(json.dumps(raw))["protocol"]["claims"]["PREDICTIVE_GAIN"] is False
