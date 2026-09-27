"""Accuracy v2 P2 preregistration contract.

This module intentionally contains protocol loading/validation only.  Candidate
model execution is added only after the tracked protocol commit is pushed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from market_ai_hub.config.settings import project_root
from market_ai_hub.research.accuracy_v2_p1 import TARGET_NEXT_PUBLISHED_SETTLEMENT

P2_SCHEMA_VERSION = "AV2P2.1"
P2_DEFAULT_PROTOCOL_ID = "jnu_next_published_settlement_return_1obs_v1"
P2_DEFAULT_PROTOCOL_PATH = project_root() / "config" / "accuracy_v2_p2_protocol.yaml"


class P2ProtocolError(ValueError):
    """Fail-closed P2 preregistration validation error."""


@dataclass(frozen=True)
class P2Protocol:
    protocol_id: str
    raw: dict[str, Any]

    @property
    def development_origin_end(self) -> date:
        return date.fromisoformat(str(self.raw["development"]["origin_end"]))

    @property
    def quarantine_start(self) -> date:
        return date.fromisoformat(str(self.raw["exposed_quarantine"]["origin_start"]))

    @property
    def quarantine_end(self) -> date:
        return date.fromisoformat(str(self.raw["exposed_quarantine"]["origin_end"]))

    @property
    def final_holdout_start(self) -> date:
        return date.fromisoformat(str(self.raw["final_holdout"]["origin_start"]))

    @property
    def minimum_meaningful_delta(self) -> float:
        return float(self.raw["primary_evaluation"]["minimum_meaningful_delta"])

    @property
    def hash(self) -> str:
        payload = {
            "schema_version": P2_SCHEMA_VERSION,
            "protocol_id": self.protocol_id,
            "protocol": self.raw,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _validate(raw: dict[str, Any]) -> None:
    if raw.get("target_task") != "RETURN_REGRESSION":
        raise P2ProtocolError("P2 primary task must remain RETURN_REGRESSION")
    if raw.get("target_measure") != TARGET_NEXT_PUBLISHED_SETTLEMENT:
        raise P2ProtocolError("P2 target must remain NEXT_PUBLISHED_SETTLEMENT_OBSERVATION")
    if int(raw.get("history_len", 0)) < 32:
        raise P2ProtocolError("P2 history_len cannot be below preregistered minimum")

    dev_end = date.fromisoformat(str(raw["development"]["origin_end"]))
    quarantine = raw["exposed_quarantine"]
    q_start = date.fromisoformat(str(quarantine["origin_start"]))
    q_end = date.fromisoformat(str(quarantine["origin_end"]))
    final_start = date.fromisoformat(str(raw["final_holdout"]["origin_start"]))
    if not (dev_end < q_start <= q_end < final_start):
        raise P2ProtocolError("development/quarantine/final boundaries must be strictly chronological")
    if any(bool(quarantine.get(key)) for key in ("use_for_fit", "use_for_selection", "use_for_claim")):
        raise P2ProtocolError("exposed quarantine cannot be reused")
    if int(raw["final_holdout"]["minimum_origins"]) < 20:
        raise P2ProtocolError("P2 final minimum cannot be weakened below 20 origins")
    final = raw["final_holdout"]
    if final.get("training_policy") != "FIT_SELECTED_MODEL_ON_DEVELOPMENT_ORIGINS_ONLY_STATIC_PARAMETERS":
        raise P2ProtocolError("P2 final training policy changed")
    if final.get("inference_context_policy") != "ORIGIN_CAUSAL_PUBLIC_HISTORY_ALLOWED_INCLUDING_POST_DEVELOPMENT_PUBLICATIONS":
        raise P2ProtocolError("P2 final inference-context policy changed")

    primary = raw["primary_evaluation"]
    if primary.get("loss") != "MAE_RETURN" or primary.get("baseline") != "ZERO_RETURN":
        raise P2ProtocolError("P2 primary loss/baseline changed")
    delta = float(primary["minimum_meaningful_delta"])
    if not (delta >= 0.0005):
        raise P2ProtocolError("P2 meaningful improvement delta cannot be weakened")

    feature_set = raw["feature_set"]
    names = list(feature_set.get("names") or [])
    if not names or len(names) > int(feature_set["maximum_feature_count"]) or len(names) > 20:
        raise P2ProtocolError("P2 feature count outside preregistered budget")
    forbidden = set(feature_set.get("forbidden") or [])
    required_forbidden = {
        "CROSS_MARKET_FACTOR_UNTIL_P1_DATA_READY",
        "FUTURE_FILL",
        "LABEL_COLUMNS",
        "FULL_SAMPLE_SCALER",
    }
    if not required_forbidden.issubset(forbidden):
        raise P2ProtocolError("P2 leakage guards were weakened")

    validation = raw["chronological_validation"]
    outer = validation["outer"]
    inner = validation["inner"]
    purge = validation["purge"]
    if not outer.get("expanding") or not inner.get("expanding"):
        raise P2ProtocolError("P2 splits must remain expanding chronological")
    if int(outer["minimum_train_origins"]) < 32 or int(inner["minimum_train_origins"]) < 20:
        raise P2ProtocolError("P2 train minima cannot be weakened")
    if purge.get("rule") != "TRAIN_LABEL_AVAILABLE_AT_MUST_NOT_EXCEED_EVALUATION_DECISION_TIME":
        raise P2ProtocolError("P2 label-availability purge changed")
    if int(purge.get("embargo_origins", 0)) < 1 or purge.get("future_rows_in_train") is not False:
        raise P2ProtocolError("P2 purge/embargo guard weakened")

    families = raw["model_families"]
    if set(families) != {
        "zero_return_naive", "ridge_return", "logistic_direction", "lightgbm_return"
    }:
        raise P2ProtocolError("P2 model-family set changed")
    if len(families["ridge_return"].get("alphas") or []) > 8:
        raise P2ProtocolError("Ridge setting cap exceeded")
    if len(families["lightgbm_return"].get("settings") or []) > 8:
        raise P2ProtocolError("LightGBM setting cap exceeded")
    if families["logistic_direction"].get("promotion_task") is not False:
        raise P2ProtocolError("classification score cannot select the return champion")

    budget = raw["search_budget"]
    if int(budget["maximum_candidate_model_families"]) > 3:
        raise P2ProtocolError("candidate family cap exceeded")
    if int(budget["maximum_settings_per_family"]) > 8:
        raise P2ProtocolError("setting cap exceeded")
    if len(budget.get("seeds") or []) > int(budget["maximum_seeds_per_setting"]):
        raise P2ProtocolError("seed cap exceeded")
    if budget.get("rerun_failed_trial_with_new_seed") is not False:
        raise P2ProtocolError("failed trials cannot be silently retried with new seeds")

    selection = raw["selection"]
    if selection.get("outer_results_are_development_information") is not True:
        raise P2ProtocolError("outer folds must remain development information")
    if selection.get("candidate_must_beat_naive_mean") is not True:
        raise P2ProtocolError("candidate cannot advance without beating naive mean")
    if selection.get("inner_setting_rule") != "LOWEST_INNER_OOF_MAE_RETURN_THEN_CONFIG_ORDER":
        raise P2ProtocolError("P2 inner setting rule changed")
    if float(selection.get("required_inner_same_origin_coverage", 0.0)) < 1.0:
        raise P2ProtocolError("P2 inner coverage requirement cannot be weakened")
    if float(selection.get("required_outer_same_origin_coverage", 0.0)) < 1.0:
        raise P2ProtocolError("P2 outer coverage requirement cannot be weakened")

    uncertainty = raw["uncertainty"]
    if int(uncertainty["block_length_publication_origins"]) < 5:
        raise P2ProtocolError("bootstrap dependence block cannot be shortened")
    if int(uncertainty["replicates"]) < 2000:
        raise P2ProtocolError("bootstrap replicate count cannot be weakened")

    promotion = raw["promotion"]
    if float(promotion["required_same_origin_coverage"]) < 1.0:
        raise P2ProtocolError("P2 final coverage requirement cannot be weakened")
    if float(promotion["required_delta_ci_upper_below"]) > -delta:
        raise P2ProtocolError("P2 CI promotion threshold cannot be weakened")
    if promotion.get("missing_prediction_counts_as_failure") is not True:
        raise P2ProtocolError("missing predictions must remain visible")


def load_p2_protocol(
    protocol_id: str = P2_DEFAULT_PROTOCOL_ID,
    path: str | Path | None = None,
) -> P2Protocol:
    p = Path(path) if path is not None else P2_DEFAULT_PROTOCOL_PATH
    payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if str(payload.get("schema_version")) != P2_SCHEMA_VERSION:
        raise P2ProtocolError("P2 protocol schema mismatch")
    raw = (payload.get("protocols") or {}).get(protocol_id)
    if not isinstance(raw, dict):
        raise KeyError(protocol_id)
    _validate(raw)
    return P2Protocol(protocol_id=protocol_id, raw=raw)
