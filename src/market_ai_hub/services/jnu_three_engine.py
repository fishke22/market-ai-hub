"""JNU Research three-engine contract adapter.

This module is intentionally dependency-light.  JNU Research owns the semantic
contract; MARKET_AI_HUB maps governed local evidence into it without redefining
research semantics.  Local-runtime validation remains pending until executed on
the user's MARKET_AI_HUB host.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
import hashlib
import json

CONTRACT_VERSION = "1.0"
TARGET = "OSE_NIKKEI225_MICRO_FUTURES"
ENGINE = "MARKET_AI_HUB"
VALIDATION_FALSE = {"PREDICTIVE_GAIN": False, "CALIBRATED": False, "TRADING_EDGE": False}

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def stable_analysis_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "jnu-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]

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
) -> dict[str, Any]:
    claims = deepcopy(VALIDATION_FALSE)
    evidence = deepcopy(model_evidence) if model_evidence else {}
    # A downstream caller may describe an already-governed validation state in
    # model_evidence, but this adapter never promotes it by inference.
    payload = {
        "contract_version": CONTRACT_VERSION,
        "engine": ENGINE,
        "generated_at": _iso_now(),
        "target": TARGET,
        "contract_month": contract_month,
        "data_as_of": data_as_of,
        "data_mode": data_mode,
        "market_regime": market_regime,
        "directional_bias": directional_bias,
        "confidence_class": confidence_class,
        "support_zones": list(support_zones or []),
        "resistance_zones": list(resistance_zones or []),
        "acceptance_checks": list(acceptance_checks or []),
        "expected_path": expected_path,
        "alternative_path": alternative_path,
        "macro_context": None,
        "event_risk": None,
        "cross_market_state": None,
        "invalidation": None,
        "flip_conditions": None,
        "model_evidence": evidence,
        "evidence_quality": deepcopy(evidence_quality or {}),
        "unknown_fields": list(unknown_fields or []),
        "validation_claims": claims,
        "source_analysis_id": source_analysis_id,
        "contract_authority": "fishke22/jerry-backtest-lab:config/jnu_three_engine_analysis_contract_v1.json",
        "local_validation_status": "LOCAL_VALIDATION_PENDING",
    }
    payload["analysis_id"] = stable_analysis_id({
        k: v for k, v in payload.items() if k not in {"generated_at", "analysis_id"}
    })
    return payload

def fuse_engine_records(records: list[dict[str, Any]], *, data_as_of: str) -> dict[str, Any]:
    """Lossless evidence-fusion envelope; deliberately not a voting engine."""
    copied = [deepcopy(r) for r in records]
    biases = [r.get("directional_bias") for r in copied if r.get("directional_bias")]
    conflicts = len(set(biases)) > 1
    payload = {
        "contract_version": CONTRACT_VERSION,
        "engine": "EVIDENCE_FUSION",
        "generated_at": _iso_now(),
        "target": TARGET,
        "contract_month": next((r.get("contract_month") for r in copied if r.get("contract_month")), None),
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
        "model_evidence": {"engine_records": copied, "engine_biases": biases, "disagreement_preserved": conflicts},
        "evidence_quality": {"fusion_method": "LOSSLESS_NO_MAJORITY_VOTE"},
        "unknown_fields": ["fused_direction_requires_governed_decision_policy"],
        "validation_claims": deepcopy(VALIDATION_FALSE),
        "local_validation_status": "LOCAL_VALIDATION_PENDING",
    }
    payload["analysis_id"] = stable_analysis_id({
        k: v for k, v in payload.items() if k not in {"generated_at", "analysis_id"}
    })
    return payload
