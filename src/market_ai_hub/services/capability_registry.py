"""Machine-readable capability registry for MARKET_AI_HUB."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from market_ai_hub.integrations.open_source_research import open_source_adapter_status
from market_ai_hub.research.accuracy_v2_p5_engine import p5_forward_evidence_summary
from market_ai_hub.research.future_data_acquisition import future_data_readiness
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.data_continuity import jnu_data_continuity_status
from market_ai_hub.config.runtime_paths import data_root
from market_ai_hub.services.model_catalog import live_model_cards


CAPABILITY_SCHEMA_VERSION = "AV2.CAPABILITIES.1"


def _cap(
    capability_id: str,
    *,
    available: bool,
    data_ready: bool,
    evidence_level: str,
    user_visible: bool = True,
    blocked_reason: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "available": bool(available),
        "data_ready": bool(data_ready),
        "evidence_level": str(evidence_level),
        "user_visible": bool(user_visible),
        "blocked_reason": str(blocked_reason or ""),
        "details": dict(details or {}),
    }


def capability_registry_snapshot() -> dict[str, Any]:
    continuity = jnu_data_continuity_status()
    cards = live_model_cards()
    p5 = p5_forward_evidence_summary()
    future = future_data_readiness()
    adapters = open_source_adapter_status()

    target_ready = bool(
        continuity.get("mode") == "NORMAL_TARGET_DATA"
        and continuity.get("target_reference_available")
    )
    chronos = cards.get("chronos-2")
    timesfm = cards.get("timesfm-3.0")
    chronos_ok = bool(chronos and chronos.engineering_status == "PASS")
    timesfm_ok = bool(timesfm and timesfm.engineering_status == "PASS")
    nautilus = adapters.get("nautilus_trader") or {}
    p5_settled = int(p5.get("settled_canonical_origin_count", 0) or 0)
    quote_archive_ready = (data_root() / "live" / "yuanta" / "parquet").exists()
    dated_event_store_ready = (data_root() / "events" / "events.duckdb").exists()

    capabilities = [
        _cap(
            "system_health_and_build",
            available=True,
            data_ready=True,
            evidence_level="ENGINEERING_PASS",
        ),
        _cap(
            "jnu_exact_contract_analysis",
            available=True,
            data_ready=target_ready,
            evidence_level="ENGINEERING_PASS",
            blocked_reason=(
                "" if target_ready else str(continuity.get("reason") or "DATA_CONTINUITY_MODE")
            ),
            details={
                "target_semantics": "NEXT_PUBLISHED_SETTLEMENT_OBSERVATION",
                "current_mode": continuity.get("mode"),
            },
        ),
        _cap(
            "jnu_data_continuity_context",
            available=True,
            data_ready=bool(continuity.get("target_reference_available")),
            evidence_level=(
                "OFFICIAL_DATA"
                if continuity.get("target_reference_available")
                else "ENGINEERING_PASS"
            ),
            details={
                "current_mode": continuity.get("mode"),
                "context_confidence_grade": continuity.get("context_confidence_grade"),
                "not_probability": True,
            },
        ),
        _cap(
            "jnu_p4_baseline_interval_context",
            available=True,
            data_ready=bool(continuity.get("target_reference_available")),
            evidence_level="DEVELOPMENT_DIAGNOSTIC",
            blocked_reason="NO_PREDICTIVE_GAIN_CANDIDATE",
            details={
                "point_champion": "ZERO_RETURN_NAIVE",
                "interval_is_probability": False,
            },
        ),
        _cap(
            "jnu_trading_path_decision_support",
            available=True,
            data_ready=quote_archive_ready,
            evidence_level="DESCRIPTIVE_DECISION_SUPPORT_ONLY",
            blocked_reason=(
                "" if quote_archive_ready else "NO_TRUE_MICRO_QUOTE_ARCHIVE"
            ),
            details={
                "settlement_forecast_separate": True,
                "true_micro_only": True,
                "cross_contract_arithmetic_fail_closed": True,
                "support_resistance_auto_generated": False,
                "calibrated_probability": False,
            },
        ),
        _cap(
            "official_event_context_for_decision_support",
            available=True,
            data_ready=dated_event_store_ready,
            evidence_level=(
                "OFFICIAL_DATA"
                if dated_event_store_ready
                else "ENGINEERING_PASS"
            ),
            blocked_reason=(
                "LIVE_NEWS_FUSION_DEFERRED_P6"
                if dated_event_store_ready
                else "NO_MATERIALIZED_DATED_EVENT_STORE_LIVE_NEWS_DEFERRED_P6"
            ),
            details={
                "role": "CONTEXT_RISK_ABSTENTION_ONLY",
                "provider_calendar_framework_available": True,
                "dated_event_store_exists": dated_event_store_ready,
                "news_sentiment_probability_allowed": False,
            },
        ),
        _cap(
            "itrader_text_advisory",
            available=True,
            data_ready=True,
            evidence_level="ENGINEERING_PASS",
            blocked_reason="UI_MAPPING_PARTIALLY_VERIFIED_NO_BROKER_ACTION",
            details={
                "no_order": True,
                "no_account_access": True,
                "no_position_query": True,
                "no_broker_mutation": True,
            },
        ),
        _cap(
            "chronos_price_research",
            available=chronos_ok,
            data_ready=target_ready,
            evidence_level="ENGINEERING_PASS",
            blocked_reason="PREDICTIVE_GAIN_NOT_ESTABLISHED_CURRENT_ACCURACY_V2",
            details={
                "predictive_validation_status": (
                    chronos.predictive_validation_status if chronos else "UNAVAILABLE"
                ),
                "serving_role": "RESEARCH_PRICE_REFERENCE",
            },
        ),
        _cap(
            "timesfm_price_research",
            available=timesfm_ok,
            data_ready=target_ready,
            evidence_level="ENGINEERING_PASS",
            blocked_reason="RESEARCH_ONLY_LICENSE_AND_PREDICTIVE_GAIN_UNESTABLISHED",
            details={
                "predictive_validation_status": (
                    timesfm.predictive_validation_status if timesfm else "UNAVAILABLE"
                ),
                "serving_allowed": False,
            },
        ),
        _cap(
            "research_price_ensemble",
            available=chronos_ok and timesfm_ok,
            data_ready=target_ready,
            evidence_level="ENGINEERING_PASS",
            blocked_reason="NO_FORWARD_PREDICTIVE_GAIN",
            details={"automatic_model_promotion": False},
        ),
        _cap(
            "public_source_collection",
            available=bool(future.get("active_public_collectors")),
            data_ready=True,
            evidence_level="OFFICIAL_DATA",
            details={
                "active_public_collectors": future.get("active_public_collectors") or [],
                "orders_allowed": False,
                "account_access_allowed": False,
                "recorder_restart_allowed": False,
            },
        ),
        _cap(
            "p5_forward_evidence_accumulation",
            available=True,
            data_ready=target_ready,
            evidence_level=(
                "FORWARD_EVIDENCE"
                if p5_settled > 0
                else "ENGINEERING_PASS"
            ),
            blocked_reason=(
                "" if target_ready else "BLOCKED_DATA_CONTINUITY_MODE"
            ),
            details={
                "settled_canonical_origins": p5_settled,
                "minimum_settled_for_evaluation": 20,
                "automatic_model_promotion": False,
            },
        ),
        _cap(
            "calibrated_public_probability",
            available=bool(p5.get("CALIBRATED", False)),
            data_ready=p5_settled >= 20,
            evidence_level="CALIBRATED" if p5.get("CALIBRATED") else "NONE",
            blocked_reason=(
                "" if p5.get("CALIBRATED") else "INSUFFICIENT_VALIDATED_FORWARD_CALIBRATION"
            ),
        ),
        _cap(
            "trading_edge_claim",
            available=False,
            data_ready=False,
            evidence_level="NONE",
            blocked_reason="NO_ECONOMIC_EDGE",
        ),
        _cap(
            "p7_independent_offline_engine",
            available=bool(nautilus.get("configured_executable_exists")),
            data_ready=True,
            evidence_level="ENGINEERING_PASS",
            details={
                "status": nautilus.get("status"),
                "live_execution_allowed": False,
            },
        ),
        _cap(
            "analysis_packet_and_audit",
            available=True,
            data_ready=True,
            evidence_level="ENGINEERING_PASS",
        ),
        _cap(
            "automatic_model_promotion",
            available=False,
            data_ready=False,
            evidence_level="NONE",
            blocked_reason="MANUAL_REVIEW_AND_NEW_INDEPENDENT_EVIDENCE_REQUIRED",
        ),
        _cap(
            "live_trading",
            available=False,
            data_ready=False,
            evidence_level="NONE",
            blocked_reason="QUOTE_ONLY_NO_ORDER_AUTHORIZATION",
        ),
    ]

    return {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "build": build_fingerprint(),
        "current_mode": continuity.get("mode"),
        "target_reference_available": continuity.get("target_reference_available"),
        "capabilities": capabilities,
        "summary": {
            "available_count": sum(1 for c in capabilities if c["available"]),
            "data_ready_count": sum(1 for c in capabilities if c["data_ready"]),
            "blocked_count": sum(1 for c in capabilities if c["blocked_reason"]),
            "predictive_gain_established": False,
            "calibrated_probability_available": bool(p5.get("CALIBRATED", False)),
            "trading_edge_established": False,
            "live_trading_enabled": False,
        },
    }
