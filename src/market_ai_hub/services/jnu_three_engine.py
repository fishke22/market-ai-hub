"""JNU Research three-engine contract adapter.

JNU Research owns the semantic contract. MARKET_AI_HUB only maps governed local
facts into that contract and keeps fusion lossless: no majority vote, no implicit
confidence promotion, and no validation-claim promotion.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
import hashlib
import json
import math

CONTRACT_VERSION = "1.0"
TARGET = "OSE_NIKKEI225_MICRO_FUTURES"
ENGINE = "MARKET_AI_HUB"
VALIDATION_FALSE = {"PREDICTIVE_GAIN": False, "CALIBRATED": False, "TRADING_EDGE": False}

DIRECTIONAL_BIASES = frozenset(
    {"BULLISH_CONDITIONAL", "BEARISH_CONDITIONAL", "NEUTRAL_CONDITIONAL", "ABSTAIN"}
)
CONFIDENCE_CLASSES = frozenset({"LOW", "MEDIUM"})
MARKET_REGIMES = frozenset({"TREND_UP", "TREND_DOWN", "BOX_BALANCE", "MIXED", "UNKNOWN"})
EVIDENCE_DIMENSIONS = ("STRUCTURE", "QUANT", "MACRO", "EVENT_RISK", "DATA_QUALITY")
LOCAL_VALIDATION_COMPONENTS = (
    "yuanta_runtime",
    "jnu_exact_live_contract",
    "session_semantics",
    "chronos_runtime",
    "timesfm_research_runtime",
    "mcp_runtime",
)
LOCAL_VALIDATION_STATES = frozenset({"PENDING", "VERIFIED", "FAILED", "NOT_APPLICABLE"})


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_analysis_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "jnu-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def _require_enum(field: str, value: str, allowed: frozenset[str]) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValueError(f"{field}: unsupported value {value!r}; allowed={sorted(allowed)}")
    return normalized


def _validate_acceptance_checks(checks: list[Any] | None) -> list[Any]:
    """Preserve checks, but never allow an Acceptance claim without an explicit level."""
    copied = deepcopy(list(checks or []))
    for check in copied:
        if not isinstance(check, dict):
            continue
        markers = {
            str(check.get(key) or "").strip().upper()
            for key in ("status", "result", "event", "type", "classification")
        }
        claims_acceptance = check.get("acceptance") is True or "ACCEPTANCE" in markers
        if not claims_acceptance:
            continue
        level = check.get("level")
        try:
            numeric_level = float(level)
        except (TypeError, ValueError):
            numeric_level = math.nan
        if not math.isfinite(numeric_level):
            raise ValueError("acceptance_checks: Acceptance requires an explicit finite level")
    return copied


def _normalize_local_validation(
    values: dict[str, str] | None,
) -> tuple[str, dict[str, str]]:
    components = {name: "PENDING" for name in LOCAL_VALIDATION_COMPONENTS}
    for raw_name, raw_state in (values or {}).items():
        name = str(raw_name)
        if name not in components:
            raise ValueError(f"local_validation: unsupported component {name!r}")
        state = str(raw_state or "").strip().upper()
        if state not in LOCAL_VALIDATION_STATES:
            raise ValueError(
                f"local_validation.{name}: unsupported state {raw_state!r}; "
                f"allowed={sorted(LOCAL_VALIDATION_STATES)}"
            )
        components[name] = state

    states = set(components.values())
    if "FAILED" in states:
        summary = "LOCAL_VALIDATION_FAILED"
    elif states <= {"VERIFIED", "NOT_APPLICABLE"}:
        summary = "LOCAL_VALIDATION_VERIFIED"
    elif states == {"PENDING"}:
        summary = "LOCAL_VALIDATION_PENDING"
    else:
        summary = "LOCAL_VALIDATION_PARTIAL"
    return summary, components


def _dimension_record(record: dict[str, Any], dimension: str) -> dict[str, Any]:
    base = {
        "engine": record.get("engine"),
        "analysis_id": record.get("analysis_id"),
        "source_analysis_id": record.get("source_analysis_id"),
    }
    fields = {
        "STRUCTURE": (
            "market_regime",
            "support_zones",
            "resistance_zones",
            "acceptance_checks",
            "expected_path",
            "alternative_path",
        ),
        "QUANT": (
            "directional_bias",
            "confidence_class",
            "model_evidence",
            "validation_claims",
        ),
        "MACRO": ("macro_context", "cross_market_state"),
        "EVENT_RISK": ("event_risk", "invalidation", "flip_conditions"),
        "DATA_QUALITY": (
            "data_mode",
            "evidence_quality",
            "unknown_fields",
            "local_validation_status",
        ),
    }[dimension]
    base["evidence"] = {field: deepcopy(record.get(field)) for field in fields}
    return base


def _dimension_index(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        dimension: [_dimension_record(record, dimension) for record in records]
        for dimension in EVIDENCE_DIMENSIONS
    }


def market_ai_hub_contract_view(
    *,
    data_as_of: str,
    contract_month: str | None = None,
    market_regime: str = "UNKNOWN",
    directional_bias: str = "ABSTAIN",
    confidence_class: str = "LOW",
    data_mode: str | None = None,
    support_zones: list[Any] | None = None,
    resistance_zones: list[Any] | None = None,
    acceptance_checks: list[Any] | None = None,
    expected_path: Any = None,
    alternative_path: Any = None,
    model_evidence: dict[str, Any] | None = None,
    evidence_quality: dict[str, Any] | None = None,
    unknown_fields: list[str] | None = None,
    source_analysis_id: str | None = None,
    local_validation: dict[str, str] | None = None,
) -> dict[str, Any]:
    claims = deepcopy(VALIDATION_FALSE)
    evidence = deepcopy(model_evidence) if model_evidence else {}
    quality = deepcopy(evidence_quality or {})
    local_summary, local_components = _normalize_local_validation(local_validation)
    quality["local_validation_components"] = local_components

    payload = {
        "contract_version": CONTRACT_VERSION,
        "engine": ENGINE,
        "generated_at": _iso_now(),
        "target": TARGET,
        "contract_month": contract_month,
        "data_as_of": data_as_of,
        "data_mode": data_mode,
        "market_regime": _require_enum("market_regime", market_regime, MARKET_REGIMES),
        "directional_bias": _require_enum(
            "directional_bias", directional_bias, DIRECTIONAL_BIASES
        ),
        "confidence_class": _require_enum(
            "confidence_class", confidence_class, CONFIDENCE_CLASSES
        ),
        "support_zones": list(support_zones or []),
        "resistance_zones": list(resistance_zones or []),
        "acceptance_checks": _validate_acceptance_checks(acceptance_checks),
        "expected_path": expected_path,
        "alternative_path": alternative_path,
        "macro_context": None,
        "event_risk": None,
        "cross_market_state": None,
        "invalidation": None,
        "flip_conditions": None,
        "model_evidence": evidence,
        "evidence_quality": quality,
        "unknown_fields": list(unknown_fields or []),
        "validation_claims": claims,
        "source_analysis_id": source_analysis_id,
        "contract_authority": "fishke22/jerry-backtest-lab:config/jnu_three_engine_analysis_contract_v1.json",
        "local_validation_status": local_summary,
    }
    payload["analysis_id"] = stable_analysis_id(
        {k: v for k, v in payload.items() if k not in {"generated_at", "analysis_id"}}
    )
    return payload


def fuse_engine_records(
    records: list[dict[str, Any]],
    *,
    data_as_of: str,
    local_validation: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Lossless evidence-fusion envelope; deliberately not a voting engine."""
    copied = [deepcopy(r) for r in records]
    biases = [r.get("directional_bias") for r in copied if r.get("directional_bias")]
    conflicts = len(set(biases)) > 1
    local_summary, local_components = _normalize_local_validation(local_validation)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "engine": "EVIDENCE_FUSION",
        "generated_at": _iso_now(),
        "target": TARGET,
        "contract_month": next(
            (r.get("contract_month") for r in copied if r.get("contract_month")), None
        ),
        "data_as_of": data_as_of,
        "data_mode": "MULTI_ENGINE_EVIDENCE",
        "market_regime": "UNKNOWN",
        "directional_bias": "ABSTAIN",
        "confidence_class": "LOW",
        "support_zones": [],
        "resistance_zones": [],
        "acceptance_checks": [],
        "expected_path": None,
        "alternative_path": None,
        "macro_context": None,
        "event_risk": None,
        "cross_market_state": None,
        "invalidation": None,
        "flip_conditions": None,
        "model_evidence": {
            "engine_records": copied,
            "engine_biases": biases,
            "disagreement_preserved": conflicts,
            "evidence_dimensions": _dimension_index(copied),
        },
        "evidence_quality": {
            "fusion_method": "LOSSLESS_NO_MAJORITY_VOTE",
            "local_validation_components": local_components,
        },
        "unknown_fields": ["fused_direction_requires_governed_decision_policy"],
        "validation_claims": deepcopy(VALIDATION_FALSE),
        "local_validation_status": local_summary,
    }
    payload["analysis_id"] = stable_analysis_id(
        {k: v for k, v in payload.items() if k not in {"generated_at", "analysis_id"}}
    )
    return payload
