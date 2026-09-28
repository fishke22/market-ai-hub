"""Forward receipt accumulation and frozen candidate semantics for Taiwan context.

This module is data-governance only. It counts immutable receipt observations,
source revisions, and retrievals separately. It never promotes a factor into a
model, never backfills a decision with a later receipt, and never interprets a
receipt count as predictive evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from market_ai_hub.config.settings import project_root
from market_ai_hub.services.taiwan_context_receipts import (
    RECEIPT_POLICY_VERSION,
    RECEIPT_SCHEMA_VERSION,
    TaiwanContextReceiptStore,
)
from market_ai_hub.services.taiwan_stock_context import (
    CONTEXT_SCHEMA_VERSION,
    build_taiwan_stock_context,
)
from market_ai_hub.services.taiwan_stock_data import normalize_taiwan_symbol


PROTOCOL_SCHEMA_VERSION = "TWCTXFORWARD.1"
PROTOCOL_ID = "taiwan_context_forward_receipts_v1"
DEFAULT_PROTOCOL_PATH = project_root() / "config" / "taiwan_context_forward_protocol.yaml"


class TaiwanContextForwardProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateFactor:
    factor_id: str
    channel: str
    source_provider: str
    source_dataset: str
    units: str
    period_semantics: str
    availability_semantics: str


@dataclass(frozen=True)
class TaiwanContextForwardProtocol:
    protocol_id: str
    raw: dict[str, Any]
    candidates: dict[str, CandidateFactor]
    blocked_channels: dict[str, dict[str, str]]

    @property
    def hash(self) -> str:
        payload = {
            "schema_version": PROTOCOL_SCHEMA_VERSION,
            "protocol_id": self.protocol_id,
            "protocol": self.raw,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


_FROZEN_CHANNELS: dict[str, tuple[str, str, str, dict[str, tuple[str, str]]]] = {
    "valuation": (
        "FinMind",
        "TaiwanStockPER",
        "SOURCE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
        {
            "pe_ratio": ("RATIO", "TRADING_DATE"),
            "pbr": ("RATIO", "TRADING_DATE"),
            "dividend_yield": ("PERCENT", "TRADING_DATE"),
        },
    ),
    "monthly_revenue": (
        "FinMind",
        "TaiwanStockMonthRevenue",
        "CREATE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
        {
            "monthly_revenue": ("TWD", "REVENUE_MONTH"),
            "monthly_revenue_mom": ("DECIMAL_RETURN", "REVENUE_MONTH"),
            "monthly_revenue_yoy": ("DECIMAL_RETURN", "REVENUE_MONTH"),
        },
    ),
    "dividend_ex_right": (
        "FinMind",
        "TaiwanStockDividend",
        "ANNOUNCEMENT_TIME_IF_PRESENT_ELSE_ANNOUNCEMENT_DATE_PLUS_ONE_LOCAL_DAY",
        {
            "cash_ex_dividend_trading_date": ("DATE", "ANNOUNCED_CORPORATE_ACTION"),
            "stock_ex_dividend_trading_date": ("DATE", "ANNOUNCED_CORPORATE_ACTION"),
            "cash_earnings_distribution": (
                "SOURCE_NATIVE_AMOUNT_UNIT_UNSPECIFIED",
                "ANNOUNCED_CORPORATE_ACTION",
            ),
            "stock_earnings_distribution": (
                "SOURCE_NATIVE_AMOUNT_UNIT_UNSPECIFIED",
                "ANNOUNCED_CORPORATE_ACTION",
            ),
        },
    ),
    "institutional_flow": (
        "FinMind",
        "TaiwanStockInstitutionalInvestorsBuySell",
        "SOURCE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
        {
            "foreign_investor_net": ("SHARES", "TRADING_DATE"),
            "investment_trust_net": ("SHARES", "TRADING_DATE"),
            "dealer_net": ("SHARES", "TRADING_DATE"),
            "foreign_dealer_self_net": ("SHARES", "TRADING_DATE"),
            "institutional_total_net": ("SHARES", "TRADING_DATE"),
        },
    ),
    "margin_short": (
        "FinMind",
        "TaiwanStockMarginPurchaseShortSale",
        "SOURCE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
        {
            "margin_purchase_buy": ("SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED", "TRADING_DATE"),
            "margin_purchase_sell": ("SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED", "TRADING_DATE"),
            "margin_purchase_today_balance": (
                "SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED",
                "TRADING_DATE",
            ),
            "short_sale_buy": ("SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED", "TRADING_DATE"),
            "short_sale_sell": ("SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED", "TRADING_DATE"),
            "short_sale_today_balance": (
                "SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED",
                "TRADING_DATE",
            ),
        },
    ),
    "securities_lending": (
        "FinMind",
        "TaiwanStockSecuritiesLending",
        "SOURCE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
        {
            "securities_lending_total_volume": (
                "SOURCE_NATIVE_VOLUME_UNIT_UNSPECIFIED",
                "TRADING_DATE",
            ),
            "securities_lending_trade_count": ("COUNT", "TRADING_DATE"),
        },
    ),
    "shareholding": (
        "FinMind",
        "TaiwanStockShareholding",
        "SOURCE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
        {
            "foreign_investment_shares": ("SHARES", "TRADING_DATE"),
            "foreign_investment_shares_ratio": ("PERCENT", "TRADING_DATE"),
            "foreign_investment_remaining_shares": ("SHARES", "TRADING_DATE"),
            "foreign_investment_remaining_ratio": ("PERCENT", "TRADING_DATE"),
            "shares_issued": ("SHARES", "TRADING_DATE"),
        },
    ),
}

_FROZEN_BLOCKED = {
    "eps": (
        "BLOCKED_PUBLICATION_SEMANTICS_UNVERIFIED",
        "EXACT_PUBLICATION_TIMESTAMP_AND_REPORT_DEFINITION_NOT_VERIFIED",
    ),
    "shareholding_concentration": (
        "BLOCKED_FREE_SOURCE_UNAVAILABLE",
        "FINMIND_DATASET_REQUIRES_NON_FREE_TIER",
    ),
    "news": (
        "BLOCKED_VERIFIED_TARGET_SOURCE_UNAVAILABLE",
        "NO_VERIFIED_REPRODUCIBLE_TARGET_SPECIFIC_FREE_NEWS_SOURCE",
    ),
}


def _utc(value: Any, *, field: str) -> pd.Timestamp:
    try:
        ts = pd.Timestamp(value)
    except Exception as exc:
        raise TaiwanContextForwardProtocolError(f"{field} invalid") from exc
    if pd.isna(ts) or ts.tzinfo is None:
        raise TaiwanContextForwardProtocolError(f"{field} must be timezone-aware")
    return ts.tz_convert("UTC")


def _hash(kind: str, *parts: Any) -> str:
    payload = [kind, *parts]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()[:32]


def _validate_protocol(raw: dict[str, Any]) -> tuple[
    dict[str, CandidateFactor],
    dict[str, dict[str, str]],
]:
    if raw.get("protocol_id") != PROTOCOL_ID:
        raise TaiwanContextForwardProtocolError("Taiwan context forward protocol id changed")
    if raw.get("role") != "DATA_CONTEXT_GOVERNANCE_ONLY":
        raise TaiwanContextForwardProtocolError("Taiwan context forward role changed")
    if raw.get("context_schema_version") != CONTEXT_SCHEMA_VERSION:
        raise TaiwanContextForwardProtocolError("context schema contract mismatch")
    if raw.get("receipt_schema_version") != RECEIPT_SCHEMA_VERSION:
        raise TaiwanContextForwardProtocolError("receipt schema contract mismatch")
    if raw.get("receipt_policy_version") != RECEIPT_POLICY_VERSION:
        raise TaiwanContextForwardProtocolError("receipt policy contract mismatch")

    policy = dict(raw.get("policy") or {})
    required_true = (
        "public_or_existing_free_sources_only",
        "no_broker_or_account_access",
        "no_recorder_restart_or_runtime_handover",
        "no_order_action",
        "receipt_time_revision_safe_is_not_source_pit_eligibility",
        "replay_available_at_is_max_source_available_at_and_receipt_time",
        "same_period_revision_is_recorded_as_new_source_version",
    )
    if any(policy.get(key) is not True for key in required_true):
        raise TaiwanContextForwardProtocolError("Taiwan forward safety policy weakened")
    required_false = (
        "scheduler_install_allowed",
        "historical_backfill_allowed",
        "future_revision_backfill_allowed",
        "repeated_retrieval_counts_as_independent_observation",
        "same_period_revision_counts_as_independent_observation",
        "predictive_feature_allowed",
        "predictive_experiment_data_ready",
        "automatic_feature_promotion",
    )
    if any(policy.get(key) is not False for key in required_false):
        raise TaiwanContextForwardProtocolError("Taiwan forward no-promotion policy weakened")

    identity = dict(raw.get("identity") or {})
    if identity.get("observation_identity_fields") != [
        "stock_id",
        "factor_id",
        "observation_period",
    ]:
        raise TaiwanContextForwardProtocolError("observation identity changed")
    if identity.get("source_version_identity_fields") != [
        "stock_id",
        "factor_id",
        "observation_period",
        "provenance_hash",
    ]:
        raise TaiwanContextForwardProtocolError("source-version identity changed")
    if identity.get("retrieval_identity_field") != "receipt_id":
        raise TaiwanContextForwardProtocolError("retrieval identity changed")

    tracked = raw.get("tracked_channels")
    if not isinstance(tracked, dict) or set(tracked) != set(_FROZEN_CHANNELS):
        raise TaiwanContextForwardProtocolError("tracked channel set changed")
    candidates: dict[str, CandidateFactor] = {}
    for channel, (provider, dataset, availability, expected_factors) in _FROZEN_CHANNELS.items():
        channel_raw = dict(tracked.get(channel) or {})
        if channel_raw.get("source_provider") != provider:
            raise TaiwanContextForwardProtocolError(f"source provider changed: {channel}")
        if channel_raw.get("source_dataset") != dataset:
            raise TaiwanContextForwardProtocolError(f"source dataset changed: {channel}")
        if channel_raw.get("availability_semantics") != availability:
            raise TaiwanContextForwardProtocolError(f"availability semantics changed: {channel}")
        factors = channel_raw.get("factors")
        if not isinstance(factors, dict) or set(factors) != set(expected_factors):
            raise TaiwanContextForwardProtocolError(f"factor set changed: {channel}")
        for factor_id, (units, period_semantics) in expected_factors.items():
            factor_raw = dict(factors.get(factor_id) or {})
            if factor_raw.get("units") != units:
                raise TaiwanContextForwardProtocolError(f"factor units changed: {factor_id}")
            if factor_raw.get("period_semantics") != period_semantics:
                raise TaiwanContextForwardProtocolError(
                    f"factor period semantics changed: {factor_id}"
                )
            if factor_id in candidates:
                raise TaiwanContextForwardProtocolError(f"duplicate factor id: {factor_id}")
            candidates[factor_id] = CandidateFactor(
                factor_id=factor_id,
                channel=channel,
                source_provider=provider,
                source_dataset=dataset,
                units=units,
                period_semantics=period_semantics,
                availability_semantics=availability,
            )

    blocked = raw.get("blocked_channels")
    if not isinstance(blocked, dict) or set(blocked) != set(_FROZEN_BLOCKED):
        raise TaiwanContextForwardProtocolError("blocked channel set changed")
    blocked_out: dict[str, dict[str, str]] = {}
    for channel, (status, reason) in _FROZEN_BLOCKED.items():
        item = dict(blocked.get(channel) or {})
        if item.get("status") != status or item.get("reason") != reason:
            raise TaiwanContextForwardProtocolError(f"blocked channel weakened: {channel}")
        blocked_out[channel] = {"status": status, "reason": reason}

    claims = dict(raw.get("claims") or {})
    for key in (
        "PREDICTIVE_GAIN",
        "CALIBRATED",
        "TRADING_EDGE",
        "independent_receipt_observation_is_predictive_sample",
    ):
        if claims.get(key) is not False:
            raise TaiwanContextForwardProtocolError(f"claim gate weakened: {key}")
    return candidates, blocked_out


def load_taiwan_context_forward_protocol(
    path: str | Path | None = None,
) -> TaiwanContextForwardProtocol:
    p = Path(path) if path is not None else DEFAULT_PROTOCOL_PATH
    payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if payload.get("schema_version") != PROTOCOL_SCHEMA_VERSION:
        raise TaiwanContextForwardProtocolError("Taiwan context forward schema mismatch")
    raw = payload.get("protocol")
    if not isinstance(raw, dict):
        raise TaiwanContextForwardProtocolError("Taiwan context forward protocol missing")
    candidates, blocked = _validate_protocol(raw)
    return TaiwanContextForwardProtocol(
        protocol_id=PROTOCOL_ID,
        raw=dict(raw),
        candidates=candidates,
        blocked_channels=blocked,
    )


def _factor_event(
    envelope: dict[str, Any],
    spec: CandidateFactor,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    context = dict(envelope.get("context") or {})
    if context.get("schema_version") != CONTEXT_SCHEMA_VERSION:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "CONTEXT_SCHEMA_MISMATCH",
        }
    channel = dict((context.get("channels") or {}).get(spec.channel) or {})
    if not channel:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "TRACKED_CHANNEL_MISSING",
        }
    if not str(channel.get("status") or "").startswith("AVAILABLE"):
        return None, None
    if channel.get("provider") != spec.source_provider:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "SOURCE_PROVIDER_MISMATCH",
        }
    if channel.get("dataset") != spec.source_dataset:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "SOURCE_DATASET_MISMATCH",
        }
    if channel.get("availability_semantics") != spec.availability_semantics:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "AVAILABILITY_SEMANTICS_MISMATCH",
        }
    factor = dict((channel.get("factors") or {}).get(spec.factor_id) or {})
    if not factor:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "TRACKED_FACTOR_MISSING",
        }
    if factor.get("units") != spec.units:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "UNITS_MISMATCH",
        }
    if factor.get("observation_period_semantics") != spec.period_semantics:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "PERIOD_SEMANTICS_MISMATCH",
        }
    if factor.get("source") != spec.source_provider:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "FACTOR_SOURCE_PROVIDER_MISMATCH",
        }
    if factor.get("source_dataset") != spec.source_dataset:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "FACTOR_SOURCE_DATASET_MISMATCH",
        }
    if factor.get("availability_semantics") != spec.availability_semantics:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "FACTOR_AVAILABILITY_SEMANTICS_MISMATCH",
        }
    if factor.get("predictive_feature_allowed") is not False:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "PREDICTIVE_FEATURE_GATE_WEAKENED",
        }
    if factor.get("value") is None:
        return None, None
    if factor.get("PIT_eligible") is not True:
        return None, None
    if not factor.get("available_at"):
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "PIT_FLAG_WITHOUT_AVAILABLE_AT",
        }
    if not factor.get("observation_period") or not factor.get("provenance_hash"):
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "OBSERVATION_IDENTITY_INCOMPLETE",
        }

    available_at = _utc(factor["available_at"], field="available_at")
    cutoff = _utc(factor.get("cutoff") or context.get("cutoff"), field="factor cutoff")
    retrieved_at = _utc(envelope["retrieved_at"], field="retrieved_at")
    context_cutoff = _utc(context.get("cutoff"), field="context cutoff")
    envelope_cutoff = _utc(envelope.get("cutoff"), field="receipt cutoff")
    factor_retrieved_at = _utc(factor.get("retrieved_at"), field="factor retrieved_at")
    context_retrieved_at = _utc(context.get("retrieved_at"), field="context retrieved_at")
    if cutoff != context_cutoff or cutoff != envelope_cutoff:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "CUTOFF_IDENTITY_MISMATCH",
        }
    if factor_retrieved_at != retrieved_at or context_retrieved_at != retrieved_at:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "RETRIEVAL_TIME_IDENTITY_MISMATCH",
        }
    if available_at > cutoff:
        return None, {
            "receipt_id": envelope.get("receipt_id"),
            "factor_id": spec.factor_id,
            "reason": "PIT_FLAG_INCONSISTENT_WITH_CUTOFF",
        }
    effective = max(available_at, retrieved_at)
    observation_period = str(factor["observation_period"])
    provenance_hash = str(factor["provenance_hash"])
    stock_id = str(envelope["stock_id"])
    observation_id = "tw-observation:" + _hash(
        "observation", stock_id, spec.factor_id, observation_period
    )
    source_version_id = "tw-source-version:" + _hash(
        "source-version",
        stock_id,
        spec.factor_id,
        observation_period,
        provenance_hash,
    )
    return {
        "receipt_id": envelope["receipt_id"],
        "stock_id": stock_id,
        "factor_id": spec.factor_id,
        "channel": spec.channel,
        "observation_period": observation_period,
        "observation_id": observation_id,
        "source_version_id": source_version_id,
        "provenance_hash": provenance_hash,
        "source_available_at": available_at.isoformat(),
        "receipt_retrieved_at": retrieved_at.isoformat(),
        "effective_replay_available_at": effective.isoformat(),
        "source_pit_eligible": True,
        "receipt_time_revision_safe_after_effective_available_at": True,
        "predictive_feature_allowed": False,
    }, None


def summarize_taiwan_context_receipts(
    stock_id: str,
    *,
    decision_time: datetime | str | pd.Timestamp | None = None,
    store: TaiwanContextReceiptStore | None = None,
    protocol: TaiwanContextForwardProtocol | None = None,
) -> dict[str, Any]:
    protocol = protocol or load_taiwan_context_forward_protocol()
    store = store or TaiwanContextReceiptStore()
    normalized_stock_id = normalize_taiwan_symbol(stock_id)
    decision = (
        _utc(decision_time, field="decision_time")
        if decision_time is not None
        else pd.Timestamp(datetime.now(timezone.utc))
    )

    envelopes: list[dict[str, Any]] = []
    integrity_failures: list[dict[str, str]] = []
    for receipt_id in store.receipt_ids():
        try:
            envelope = store.load(receipt_id)
        except Exception as exc:
            integrity_failures.append(
                {"receipt_id": receipt_id, "reason": type(exc).__name__}
            )
            continue
        if str(envelope.get("stock_id") or "") != normalized_stock_id:
            continue
        envelopes.append(envelope)

    visible_envelopes = [
        envelope
        for envelope in envelopes
        if _utc(envelope["retrieved_at"], field="retrieved_at") <= decision
    ]
    visible_receipt_ids = sorted(
        str(envelope["receipt_id"]) for envelope in visible_envelopes
    )
    factor_events: dict[str, list[dict[str, Any]]] = {
        factor_id: [] for factor_id in protocol.candidates
    }
    contract_violations: list[dict[str, Any]] = []
    for envelope in visible_envelopes:
        for factor_id, spec in protocol.candidates.items():
            event, violation = _factor_event(envelope, spec)
            if violation is not None:
                contract_violations.append(violation)
            if event is None:
                continue
            if _utc(event["effective_replay_available_at"], field="effective_replay_available_at") <= decision:
                factor_events[factor_id].append(event)

    factors: dict[str, dict[str, Any]] = {}
    for factor_id, spec in protocol.candidates.items():
        events = factor_events[factor_id]
        observation_ids = {event["observation_id"] for event in events}
        source_versions = {event["source_version_id"] for event in events}
        versions_by_observation: dict[str, set[str]] = {}
        receipts_by_source_version: dict[str, set[str]] = {}
        for event in events:
            versions_by_observation.setdefault(event["observation_id"], set()).add(
                event["source_version_id"]
            )
            receipts_by_source_version.setdefault(event["source_version_id"], set()).add(
                event["receipt_id"]
            )
        revised = sum(1 for versions in versions_by_observation.values() if len(versions) > 1)
        repeated = sum(max(0, len(receipts) - 1) for receipts in receipts_by_source_version.values())
        latest = max(
            events,
            key=lambda event: (
                _utc(event["effective_replay_available_at"], field="effective"),
                event["receipt_id"],
            ),
            default=None,
        )
        factors[factor_id] = {
            "channel": spec.channel,
            "source_provider": spec.source_provider,
            "source_dataset": spec.source_dataset,
            "units": spec.units,
            "period_semantics": spec.period_semantics,
            "availability_semantics": spec.availability_semantics,
            "retrieval_count_as_of_decision": len(events),
            "source_version_count_as_of_decision": len(source_versions),
            "independent_observation_count_as_of_decision": len(observation_ids),
            "repeated_retrieval_count_as_of_decision": repeated,
            "revised_observation_count_as_of_decision": revised,
            "latest_observation_period": (
                latest["observation_period"] if latest is not None else None
            ),
            "latest_effective_replay_available_at": (
                latest["effective_replay_available_at"] if latest is not None else None
            ),
            "predictive_feature_allowed": False,
        }

    status = "READY_FOR_FORWARD_RECEIPT_ACCUMULATION"
    if integrity_failures:
        status = "BLOCKED_RECEIPT_INTEGRITY_FAILURE"
    elif contract_violations:
        status = "BLOCKED_CANDIDATE_CONTRACT_MISMATCH"
    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "protocol_id": protocol.protocol_id,
        "protocol_hash": protocol.hash,
        "status": status,
        "stock_id": normalized_stock_id,
        "decision_time": decision.isoformat(),
        "receipt_count_total": len(visible_envelopes),
        "receipt_count_as_of_decision": len(visible_envelopes),
        "receipt_ids": visible_receipt_ids,
        "integrity_failures": integrity_failures,
        "contract_violations": contract_violations,
        "factors": factors,
        "tracked_factor_count": len(protocol.candidates),
        "factors_with_observation_as_of_decision": sum(
            1
            for factor in factors.values()
            if factor["independent_observation_count_as_of_decision"] > 0
        ),
        "blocked_channels": protocol.blocked_channels,
        "counting_semantics": {
            "independent_observation": "UNIQUE_STOCK_FACTOR_OBSERVATION_PERIOD",
            "source_revision": "UNIQUE_OBSERVATION_PLUS_PROVENANCE_HASH",
            "retrieval": "UNIQUE_RECEIPT_ID",
            "repeated_retrieval_increases_independent_observation_count": False,
            "same_period_revision_increases_independent_observation_count": False,
            "same_period_revision_is_preserved": True,
        },
        "replay_semantics": {
            "effective_available_at": "MAX_SOURCE_AVAILABLE_AT_AND_RECEIPT_RETRIEVED_AT",
            "future_receipt_visible_to_past_decision": False,
            "receipt_time_revision_safe_is_source_pit_eligibility": False,
            "historical_backfill_allowed": False,
        },
        "predictive_feature_allowed": False,
        "predictive_experiment_data_ready": False,
        "validation_claims": {
            "PREDICTIVE_GAIN": False,
            "CALIBRATED": False,
            "TRADING_EDGE": False,
        },
    }


def collect_taiwan_context_forward_receipt(
    symbol: str,
    *,
    as_of: datetime | str | pd.Timestamp | None = None,
    store: TaiwanContextReceiptStore | None = None,
    finmind: Any | None = None,
    twse: Any | None = None,
) -> dict[str, Any]:
    protocol = load_taiwan_context_forward_protocol()
    store = store or TaiwanContextReceiptStore()
    cutoff = _utc(
        datetime.now(timezone.utc) if as_of is None else as_of,
        field="as_of",
    )
    context = build_taiwan_stock_context(
        symbol,
        as_of=cutoff,
        finmind=finmind,
        twse=twse,
        include_twse_official=True,
    )
    receipt = store.capture(context)
    inventory = summarize_taiwan_context_receipts(
        normalize_taiwan_symbol(symbol),
        decision_time=datetime.now(timezone.utc),
        store=store,
        protocol=protocol,
    )
    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "protocol_id": protocol.protocol_id,
        "protocol_hash": protocol.hash,
        "symbol": symbol,
        "stock_id": normalize_taiwan_symbol(symbol),
        "receipt": receipt,
        "inventory": inventory,
        "counts_as_predictive_sample": False,
        "predictive_feature_allowed": False,
        "predictive_experiment_data_ready": False,
        "broker_used": False,
        "account_accessed": False,
        "recorder_touched": False,
        "runtime_handover": False,
        "scheduler_installed": False,
        "order_action": False,
    }
