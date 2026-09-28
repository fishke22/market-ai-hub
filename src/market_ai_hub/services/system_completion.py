"""Machine-readable engineering completion audit for Accuracy v2.

The audit answers a narrower question than system readiness:
are all *currently actionable* engineering packages present without weakening
the explicit future-data, authorization, sealed-evidence, or claim boundaries?
It does not turn time-dependent forward evidence into an engineering blocker.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from market_ai_hub.config.settings import project_root
from market_ai_hub.services.build_info import build_fingerprint


SYSTEM_COMPLETION_SCHEMA_VERSION = "AV2.SYSTEM_COMPLETION.1"
SYSTEM_COMPLETION_PROTOCOL_ID = "accuracy_v2_engineering_closeout_v1"
DEFAULT_SYSTEM_COMPLETION_PATH = (
    project_root() / "config" / "accuracy_v2_system_completion.yaml"
)


class SystemCompletionProtocolError(ValueError):
    """Tracked completion policy was changed incompatibly."""


_EXPECTED_REQUIRED_ENGINEERING = {
    "p1_data_contract": ("src/market_ai_hub/research/accuracy_v2_p1.py", None, None),
    "p2_selection_protocol": ("config/accuracy_v2_p2_protocol.yaml", "AV2P2.1", None),
    "p3a_past_only_covariates": (
        "src/market_ai_hub/research/accuracy_v2_p3a.py",
        None,
        None,
    ),
    "p3b_receipt_time_cross_market": (
        "src/market_ai_hub/research/accuracy_v2_p3b_taifex.py",
        None,
        None,
    ),
    "p4_no_future_analysis": ("config/accuracy_v2_p4_protocol.yaml", "AV2P4.1", None),
    "p5_forward_monitor": ("config/accuracy_v2_p5_protocol.yaml", "AV2P5.1", None),
    "p7_independent_engine": ("config/accuracy_v2_p7_protocol.yaml", "AV2P7.1", None),
    "data_continuity": ("src/market_ai_hub/services/data_continuity.py", None, None),
    "capability_registry": (
        "src/market_ai_hub/services/capability_registry.py",
        None,
        None,
    ),
    "analysis_packet_audit": ("src/market_ai_hub/packet/builder.py", None, None),
    "taiex_official_daily": (
        "src/market_ai_hub/providers/twse.py",
        None,
        "def fetch_taiex_daily(",
    ),
    "jpx_investor_flow": (
        "src/market_ai_hub/targets/jpx_investor_flow.py",
        None,
        "AVAILABLE_OFFICIAL_WEEKLY_RECEIPT_TIME",
    ),
    "taiwan_forward_receipts": (
        "config/taiwan_context_forward_protocol.yaml",
        "TWCTXFORWARD.1",
        None,
    ),
    "timesfm_personal_research": (
        "src/market_ai_hub/services/model_governance.py",
        None,
        None,
    ),
    "system_readiness": ("scripts/validate_accuracy_v2_system.py", None, None),
    "system_manifest_consistency": (
        "config/system_manifest.yaml",
        None,
        "tool_count: 27",
    ),
    "static_capability_consistency": (
        "config/capabilities.yaml",
        None,
        "jpx_micro_investor_flow:",
    ),
}


def _load_completion_policy(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path is not None else DEFAULT_SYSTEM_COMPLETION_PATH
    payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if payload.get("schema_version") != SYSTEM_COMPLETION_SCHEMA_VERSION:
        raise SystemCompletionProtocolError("system completion schema mismatch")
    completion = payload.get("completion")
    if not isinstance(completion, dict):
        raise SystemCompletionProtocolError("system completion block missing")
    if completion.get("protocol_id") != SYSTEM_COMPLETION_PROTOCOL_ID:
        raise SystemCompletionProtocolError("system completion protocol id changed")
    if completion.get("scope") != "CURRENTLY_ACTIONABLE_ENGINEERING_ONLY":
        raise SystemCompletionProtocolError("system completion scope changed")
    return completion


def _validate_policy(completion: dict[str, Any]) -> None:
    required = completion.get("required_engineering")
    if not isinstance(required, dict) or set(required) != set(
        _EXPECTED_REQUIRED_ENGINEERING
    ):
        raise SystemCompletionProtocolError("required engineering set changed")
    for component, (path, schema, marker) in _EXPECTED_REQUIRED_ENGINEERING.items():
        item = dict(required.get(component) or {})
        if item.get("path") != path:
            raise SystemCompletionProtocolError(
                f"required engineering path changed: {component}"
            )
        if schema is None:
            if item.get("expected_schema") not in (None, ""):
                raise SystemCompletionProtocolError(
                    f"unexpected schema contract: {component}"
                )
        elif item.get("expected_schema") != schema:
            raise SystemCompletionProtocolError(
                f"required schema changed: {component}"
            )
        if marker is None:
            if item.get("expected_marker") not in (None, ""):
                raise SystemCompletionProtocolError(
                    f"unexpected marker contract: {component}"
                )
        elif item.get("expected_marker") != marker:
            raise SystemCompletionProtocolError(
                f"required marker changed: {component}"
            )

    p6 = dict((completion.get("conditional_packages") or {}).get("P6") or {})
    if p6 != {
        "status": "CONDITIONAL_NOT_REQUIRED",
        "trigger": "DATA_RUNTIME_AND_INDEPENDENT_GAIN_PREREQUISITES",
        "engineering_completion_blocker": False,
        "automatic_activation": False,
        "automatic_model_promotion": False,
    }:
        raise SystemCompletionProtocolError("P6 conditional boundary changed")

    deferred = dict(completion.get("deferred_non_blocking") or {})
    if set(deferred) != {
        "p6_research_extensions",
        "broker_order_execution",
        "optional_external_macro_sources",
    }:
        raise SystemCompletionProtocolError("deferred non-blocking set changed")
    for deferred_id, item in deferred.items():
        if dict(item or {}).get("engineering_completion_blocker") is not False:
            raise SystemCompletionProtocolError(
                f"deferred component became blocker: {deferred_id}"
            )
    if deferred["broker_order_execution"].get("quote_only") is not True:
        raise SystemCompletionProtocolError("deferred broker quote-only boundary changed")

    external = dict(completion.get("external_dependencies") or {})
    expected_external = {
        "p5_forward_outcomes",
        "taiwan_forward_observation_periods",
        "taiwan_eps_publication_semantics",
        "taiwan_target_news_source",
    }
    if set(external) != expected_external:
        raise SystemCompletionProtocolError("external dependency set changed")
    for dependency_id, item in external.items():
        if dict(item or {}).get("engineering_completion_blocker") is not False:
            raise SystemCompletionProtocolError(
                f"external dependency became blocker: {dependency_id}"
            )
    if (
        external["p5_forward_outcomes"].get("historical_backfill_allowed")
        is not False
    ):
        raise SystemCompletionProtocolError("P5 historical backfill boundary changed")
    if (
        external["taiwan_forward_observation_periods"].get(
            "repeated_retrieval_counts_as_new_observation"
        )
        is not False
    ):
        raise SystemCompletionProtocolError(
            "Taiwan repeated-retrieval counting boundary changed"
        )

    auth = dict(completion.get("authorization_boundaries") or {})
    if set(auth) != {
        "p5_scheduler_install",
        "recorder_runtime_handover",
        "live_trading",
    }:
        raise SystemCompletionProtocolError("authorization boundary set changed")
    for boundary_id, item in auth.items():
        item = dict(item or {})
        if item.get("authorized") is not False:
            raise SystemCompletionProtocolError(
                f"authorization boundary weakened: {boundary_id}"
            )
        if item.get("engineering_completion_blocker") is not False:
            raise SystemCompletionProtocolError(
                f"authorization boundary became blocker: {boundary_id}"
            )
    if auth["live_trading"].get("quote_only") is not True:
        raise SystemCompletionProtocolError("quote-only boundary changed")

    sealed = dict(completion.get("sealed_evidence") or {})
    if set(sealed) != {"hpq1_old_final", "p2_final"}:
        raise SystemCompletionProtocolError("sealed evidence set changed")
    hpq1 = dict(sealed["hpq1_old_final"] or {})
    if hpq1.get("status") != "BLOCKED_HORIZON_MISMATCH":
        raise SystemCompletionProtocolError("HPQ1 sealed status changed")
    if hpq1.get("rerun_allowed") is not False:
        raise SystemCompletionProtocolError("HPQ1 rerun boundary changed")
    if hpq1.get("overwrite_allowed") is not False:
        raise SystemCompletionProtocolError("HPQ1 overwrite boundary changed")
    p2_final = dict(sealed["p2_final"] or {})
    if p2_final.get("status") != "NOT_OPENED_WAITING_NEW_FORWARD_ONLY":
        raise SystemCompletionProtocolError("P2 final status changed")
    if int(p2_final.get("minimum_new_forward_origins") or 0) != 20:
        raise SystemCompletionProtocolError("P2 final minimum origin count changed")
    if any(
        dict(item or {}).get("engineering_completion_blocker") is not False
        for item in sealed.values()
    ):
        raise SystemCompletionProtocolError("sealed evidence became engineering blocker")

    claims = dict(completion.get("claims") or {})
    for key in (
        "PREDICTIVE_GAIN",
        "CALIBRATED",
        "TRADING_EDGE",
        "live_execution_enabled",
    ):
        if claims.get(key) is not False:
            raise SystemCompletionProtocolError(f"claim boundary weakened: {key}")


def _check_required_component(
    root: Path,
    component_id: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    relative = str(policy["path"])
    path = root / relative
    expected_schema = policy.get("expected_schema")
    expected_marker = policy.get("expected_marker")
    status = "IMPLEMENTED"
    reason = ""
    observed_schema = None
    if not path.is_file():
        status = "MISSING"
        reason = "REQUIRED_PATH_MISSING"
    elif expected_schema:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            observed_schema = payload.get("schema_version")
        except Exception as exc:
            status = "INVALID"
            reason = type(exc).__name__
        else:
            if observed_schema != expected_schema:
                status = "INVALID"
                reason = "SCHEMA_MISMATCH"
    if status == "IMPLEMENTED" and expected_marker:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            status = "INVALID"
            reason = type(exc).__name__
        else:
            if str(expected_marker) not in text:
                status = "INVALID"
                reason = "REQUIRED_MARKER_MISSING"
    return {
        "component_id": component_id,
        "status": status,
        "complete": status == "IMPLEMENTED",
        "path": relative,
        "expected_schema": expected_schema,
        "observed_schema": observed_schema,
        "expected_marker": expected_marker,
        "reason": reason,
    }


def system_completion_snapshot(
    *,
    policy_path: str | Path | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    completion = _load_completion_policy(policy_path)
    _validate_policy(completion)
    repo_root = Path(root) if root is not None else project_root()
    required_policy = dict(completion["required_engineering"])
    components = [
        _check_required_component(repo_root, component_id, dict(policy))
        for component_id, policy in required_policy.items()
    ]
    actionable_gaps = [
        component for component in components if component["complete"] is not True
    ]
    conditional = dict(completion["conditional_packages"])
    deferred = dict(completion["deferred_non_blocking"])
    external = dict(completion["external_dependencies"])
    authorization = dict(completion["authorization_boundaries"])
    sealed = dict(completion["sealed_evidence"])
    claims = dict(completion["claims"])
    engineering_complete = not actionable_gaps
    status = (
        "ENGINEERING_COMPLETE_WAITING_FOR_EXTERNAL_EVIDENCE"
        if engineering_complete
        else "ENGINEERING_INCOMPLETE_ACTION_REQUIRED"
    )
    return {
        "schema_version": SYSTEM_COMPLETION_SCHEMA_VERSION,
        "protocol_id": SYSTEM_COMPLETION_PROTOCOL_ID,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "build": build_fingerprint(),
        "scope": completion["scope"],
        "all_currently_actionable_engineering_complete": engineering_complete,
        "actionable_engineering_gap_count": len(actionable_gaps),
        "actionable_engineering_gaps": actionable_gaps,
        "required_engineering": components,
        "conditional_packages": conditional,
        "deferred_non_blocking": deferred,
        "external_dependencies": external,
        "authorization_boundaries": authorization,
        "sealed_evidence": sealed,
        "claims": claims,
        "completion_semantics": {
            "future_data_is_engineering_blocker": False,
            "missing_external_authorization_is_engineering_blocker": False,
            "sealed_final_must_be_rerun_for_engineering_completion": False,
            "predictive_gain_required_for_engineering_completion": False,
            "calibration_required_for_engineering_completion": False,
            "trading_edge_required_for_engineering_completion": False,
        },
    }
