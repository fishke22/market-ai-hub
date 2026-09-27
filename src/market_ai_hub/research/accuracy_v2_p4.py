"""Accuracy v2 P4 preregistration for analysis when no new forward outcome exists."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from market_ai_hub.config.settings import project_root
from market_ai_hub.research.accuracy_v2_p1 import TARGET_NEXT_PUBLISHED_SETTLEMENT


P4_SCHEMA_VERSION = "AV2P4.1"
P4_DEFAULT_PROTOCOL_ID = "jnu_no_future_analysis_v1"
P4_DEFAULT_PROTOCOL_PATH = project_root() / "config" / "accuracy_v2_p4_protocol.yaml"


class P4ProtocolError(ValueError):
    """Fail-closed P4 preregistration validation error."""


@dataclass(frozen=True)
class P4Protocol:
    protocol_id: str
    raw: dict[str, Any]

    @property
    def hash(self) -> str:
        payload = {
            "schema_version": P4_SCHEMA_VERSION,
            "protocol_id": self.protocol_id,
            "protocol": self.raw,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _validate(raw: dict[str, Any]) -> None:
    if raw.get("target_measure") != TARGET_NEXT_PUBLISHED_SETTLEMENT:
        raise P4ProtocolError("P4 target measure changed")
    if raw.get("exact_contract_required") is not True:
        raise P4ProtocolError("P4 exact-contract requirement cannot be disabled")

    boundaries = raw["evidence_boundaries"]
    if boundaries.get("point_champion") != "ZERO_RETURN_NAIVE":
        raise P4ProtocolError("P4 must preserve the P2 retained baseline")
    for key in (
        "exposed_quarantine_use_for_fit",
        "exposed_quarantine_use_for_selection",
        "exposed_quarantine_use_for_claim",
    ):
        if boundaries.get(key) is not False:
            raise P4ProtocolError("P4 cannot reuse exposed quarantine for fit/selection/claim")
    for key in (
        "final_forward_required_for_predictive_gain",
        "historical_interval_never_implies_calibrated_probability",
        "no_future_outcome_never_implies_predictive_gain",
        "no_future_outcome_never_implies_trading_edge",
    ):
        if boundaries.get(key) is not True:
            raise P4ProtocolError(f"P4 evidence guard weakened: {key}")

    context = raw["inference_context"]
    if context.get("future_fill_allowed") is not False:
        raise P4ProtocolError("future fill must remain forbidden")
    if context.get("cross_contract_stitching_allowed") is not False:
        raise P4ProtocolError("cross-contract stitching must remain forbidden")
    if context.get("label_columns_allowed_in_features") is not False:
        raise P4ProtocolError("label columns cannot enter P4 features")
    if context.get("post_development_labels_allowed_for_reselection") is not False:
        raise P4ProtocolError("post-development labels cannot reselect models")

    vol = raw["volatility"]
    if vol.get("method") != "EWMA_RETURN_VOLATILITY":
        raise P4ProtocolError("P4 volatility method changed")
    decay = float(vol["decay_lambda"])
    if not 0.0 < decay < 1.0:
        raise P4ProtocolError("EWMA decay must be in (0,1)")
    if int(vol["minimum_return_count"]) < 20:
        raise P4ProtocolError("P4 volatility history minimum cannot be weakened")

    quantile = raw["quantile_challenger"]
    if quantile.get("objective") != "quantile" or quantile.get("tuning") != "NONE":
        raise P4ProtocolError("P4 quantile challenger must remain fixed/no-tuning")
    alphas = [float(x) for x in quantile.get("alphas") or []]
    if alphas != [0.10, 0.50, 0.90]:
        raise P4ProtocolError("P4 quantile levels changed")
    if quantile.get("fit_partition") != "DEVELOPMENT_ONLY":
        raise P4ProtocolError("P4 quantile fit must remain development-only")
    if quantile.get("may_replace_point_champion") is not False:
        raise P4ProtocolError("quantile challenger cannot replace point champion")
    if quantile.get("may_publish_as_calibrated_interval") is not False:
        raise P4ProtocolError("quantile challenger cannot masquerade as calibrated")

    conformal = raw["conformal"]
    if conformal.get("initial_fit_partition") != "DEVELOPMENT_ONLY":
        raise P4ProtocolError("P4 conformal initial fit must remain development-only")
    if int(conformal["minimum_residual_count"]) < 20:
        raise P4ProtocolError("P4 conformal minimum cannot be weakened")
    coverages = [float(x) for x in conformal.get("nominal_coverages") or []]
    if coverages != [0.50, 0.75, 0.90]:
        raise P4ProtocolError("P4 conformal coverage grid changed")
    adaptive = conformal["adaptive_challenger"]
    if adaptive.get("update_only_after_outcome_available") is not True:
        raise P4ProtocolError("adaptive conformal cannot update before outcome availability")
    if adaptive.get("evaluation_partition") != "DEVELOPMENT_ONLY":
        raise P4ProtocolError("adaptive conformal evaluation must remain development-only")
    if conformal.get("may_publish_as_conditional_probability") is not False:
        raise P4ProtocolError("interval coverage is not a probability")
    if conformal.get("may_replace_w4_probability_calibration") is not False:
        raise P4ProtocolError("P4 conformal cannot replace W4 calibration")

    regime = raw["regime"]
    if regime.get("model_switching_allowed") is not False:
        raise P4ProtocolError("P4 regime cannot switch models")
    if regime.get("threshold_fit_partition") != "DEVELOPMENT_ONLY":
        raise P4ProtocolError("regime threshold must remain development-only")

    abstain = raw["abstention"]
    if abstain.get("strong_direction_requires_predictive_gain") is not True:
        raise P4ProtocolError("strong direction cannot bypass predictive-gain gate")
    if float(abstain.get("max_reference_age_hours", 0)) <= 0:
        raise P4ProtocolError("reference age gate must be positive")

    perf = raw["performance_budget"]
    if perf.get("gpu_required") is not False:
        raise P4ProtocolError("P4 no-future path must not require GPU")
    if int(perf.get("maximum_model_fits_per_analysis", 999)) > 3:
        raise P4ProtocolError("P4 model-fit budget exceeded")

    promotion = raw["promotion"]
    if promotion.get("point_default_without_gain") != "ZERO_RETURN_NAIVE":
        raise P4ProtocolError("P4 no-gain default changed")
    if promotion.get("requires_separate_preregistered_forward_protocol_for_upgrade") is not True:
        raise P4ProtocolError("P4 upgrade must remain separately preregistered")
    never = set(promotion.get("never_implies") or [])
    if not {"PREDICTIVE_GAIN", "CALIBRATED", "TRADING_EDGE", "FIXED_WIN_RATE"} <= never:
        raise P4ProtocolError("P4 promotion disclaimers weakened")


def load_p4_protocol(
    protocol_id: str = P4_DEFAULT_PROTOCOL_ID,
    path: str | Path | None = None,
) -> P4Protocol:
    p = Path(path) if path is not None else P4_DEFAULT_PROTOCOL_PATH
    payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if str(payload.get("schema_version")) != P4_SCHEMA_VERSION:
        raise P4ProtocolError("P4 protocol schema mismatch")
    raw = (payload.get("protocols") or {}).get(protocol_id)
    if not isinstance(raw, dict):
        raise KeyError(protocol_id)
    _validate(raw)
    return P4Protocol(protocol_id=protocol_id, raw=raw)
