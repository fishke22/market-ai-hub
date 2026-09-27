"""Accuracy v2 P5 preregistration: real forward publication monitoring."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from market_ai_hub.config.settings import project_root
from market_ai_hub.research.accuracy_v2_p1 import TARGET_NEXT_PUBLISHED_SETTLEMENT


P5_SCHEMA_VERSION = "AV2P5.1"
P5_DEFAULT_PROTOCOL_ID = "jnu_forward_publication_monitor_v1"
P5_DEFAULT_PROTOCOL_PATH = project_root() / "config" / "accuracy_v2_p5_protocol.yaml"


class P5ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class P5Protocol:
    protocol_id: str
    raw: dict[str, Any]

    @property
    def hash(self) -> str:
        payload = {
            "schema_version": P5_SCHEMA_VERSION,
            "protocol_id": self.protocol_id,
            "protocol": self.raw,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def _validate(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("measure") != TARGET_NEXT_PUBLISHED_SETTLEMENT:
        raise P5ProtocolError("P5 target measure changed")
    if target.get("exact_contract_required") is not True:
        raise P5ProtocolError("P5 exact-contract requirement cannot be disabled")
    if target.get("full_session_forecast_claim_allowed") is not False:
        raise P5ProtocolError("P5 publication monitor cannot masquerade as full-session forecast")

    origin = raw["origin"]
    if origin.get("first_eligible_publication_date") != "2026-09-28":
        raise P5ProtocolError("P5 forward start boundary changed")
    if origin.get("nominal_rule") != "REFERENCE_SESSION_PUBLICATION_PLUS_5_MINUTES":
        raise P5ProtocolError("P5 origin rule changed")
    lateness = int(origin.get("canonical_max_lateness_minutes", -1))
    if lateness < 0 or lateness > 30:
        raise P5ProtocolError("P5 canonical lateness must remain in [0,30] minutes")
    if origin.get("reference_receipt_must_precede_forecast_origin") is not True:
        raise P5ProtocolError("P5 reference receipt gate weakened")
    if origin.get("backdated_forecast_origin_allowed") is not False:
        raise P5ProtocolError("P5 backdated origins are forbidden")

    artifacts = raw["artifacts"]
    point = artifacts["point"]
    if point.get("method") != "ZERO_RETURN_NAIVE_LAST_AVAILABLE_SETTLEMENT":
        raise P5ProtocolError("P5 point champion changed")
    interval = artifacts["interval"]
    if float(interval.get("nominal_coverage")) != 0.90:
        raise P5ProtocolError("P5 interval nominal coverage changed")
    if interval.get("never_implies_probability") is not True:
        raise P5ProtocolError("P5 interval cannot become a probability")
    quantile = artifacts["quantile_challenger"]
    if [float(x) for x in quantile.get("levels") or []] != [0.10, 0.50, 0.90]:
        raise P5ProtocolError("P5 quantile levels changed")
    if quantile.get("may_replace_point_champion") is not False:
        raise P5ProtocolError("P5 quantile challenger cannot replace point champion")

    ledger = raw["immutable_ledger"]
    required_true = (
        "append_only",
        "one_prediction_per_target_contract_origin",
        "prediction_before_outcome_required",
        "outcome_binding_per_artifact_required",
    )
    if any(ledger.get(k) is not True for k in required_true):
        raise P5ProtocolError("P5 immutable-ledger invariant weakened")
    if ledger.get("overwrite_allowed") is not False or ledger.get("delete_allowed") is not False:
        raise P5ProtocolError("P5 ledger must remain append-only")
    if ledger.get("sample_origin") != "FORWARD_PRECOMMITTED":
        raise P5ProtocolError("P5 sample_origin changed")

    evaluation = raw["forward_evaluation"]
    if int(evaluation.get("minimum_settled_canonical_origins", 0)) < 20:
        raise P5ProtocolError("P5 minimum settled origin count cannot be weakened")
    if evaluation.get("automatic_model_promotion") is not False:
        raise P5ProtocolError("P5 cannot automatically promote models")
    if evaluation.get("requires_separate_preregistered_promotion_protocol") is not True:
        raise P5ProtocolError("P5 promotion must remain separately preregistered")
    if evaluation.get("quarantine_or_historical_replay_counts_as_forward") is not False:
        raise P5ProtocolError("historical/quarantine data cannot count as forward")

    downgrade = raw["downgrade"]
    if int(downgrade.get("current_reference_max_age_minutes", 0)) > 30:
        raise P5ProtocolError("P5 reference-age gate weakened")
    if float(downgrade["interval"]["minimum_acceptable_coverage"]) < 0.75:
        raise P5ProtocolError("P5 interval downgrade threshold weakened")
    if float(downgrade["origin_coverage"]["minimum_canonical_origin_coverage"]) < 0.80:
        raise P5ProtocolError("P5 origin coverage threshold weakened")
    if downgrade.get("strong_direction_allowed") is not False:
        raise P5ProtocolError("P5 strong direction remains blocked")
    if downgrade.get("calibrated_probability_allowed") is not False:
        raise P5ProtocolError("P5 calibration remains blocked")
    if downgrade.get("trading_edge_allowed") is not False:
        raise P5ProtocolError("P5 trading edge remains blocked")

    collector = raw["collector"]
    if collector.get("public_sources_only") is not True:
        raise P5ProtocolError("P5 collector must remain public-source only")
    for k in ("broker_used", "credentials_used", "recorder_restart_allowed", "order_action_allowed"):
        if collector.get(k) is not False:
            raise P5ProtocolError(f"P5 collector safety gate weakened: {k}")
    times = list(collector.get("planned_weekday_times") or [])
    if times != ["08:05", "08:15"]:
        raise P5ProtocolError("P5 collector cadence changed")

    never = set(raw["publication"].get("never_implies") or [])
    if not {"PREDICTIVE_GAIN", "CALIBRATED", "TRADING_EDGE", "FIXED_WIN_RATE"} <= never:
        raise P5ProtocolError("P5 evidence disclaimers weakened")


def load_p5_protocol(
    protocol_id: str = P5_DEFAULT_PROTOCOL_ID,
    path: str | Path | None = None,
) -> P5Protocol:
    p = Path(path) if path is not None else P5_DEFAULT_PROTOCOL_PATH
    payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if str(payload.get("schema_version")) != P5_SCHEMA_VERSION:
        raise P5ProtocolError("P5 protocol schema mismatch")
    raw = (payload.get("protocols") or {}).get(protocol_id)
    if not isinstance(raw, dict):
        raise KeyError(protocol_id)
    _validate(raw)
    return P5Protocol(protocol_id=protocol_id, raw=raw)
