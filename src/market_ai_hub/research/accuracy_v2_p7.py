"""Accuracy v2 P7 preregistration and immutable acceptance contract."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from market_ai_hub.config.settings import project_root


P7_SCHEMA_VERSION = "AV2P7.1"
P7_DEFAULT_PROTOCOL_ID = "independent_engine_acceptance_v1"
P7_DEFAULT_PROTOCOL_PATH = project_root() / "config" / "accuracy_v2_p7_protocol.yaml"


class P7ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class P7Protocol:
    protocol_id: str
    raw: dict[str, Any]

    @property
    def hash(self) -> str:
        payload = {
            "schema_version": P7_SCHEMA_VERSION,
            "protocol_id": self.protocol_id,
            "protocol": self.raw,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def _validate(raw: dict[str, Any]) -> None:
    engine = raw["engine"]
    if engine.get("adapter") != "nautilus_trader":
        raise P7ProtocolError("P7 independent engine changed")
    if engine.get("release") != "1.231.0" or engine.get("commit") != "27a8e54":
        raise P7ProtocolError("P7 pinned engine revision changed")
    if engine.get("integration_mode") != "ISOLATED_SUBPROCESS_FILE_CONTRACT":
        raise P7ProtocolError("P7 engine must remain isolated")
    if engine.get("core_venv_install_allowed") is not False:
        raise P7ProtocolError("P7 core venv install is forbidden")
    if engine.get("live_execution_allowed") is not False:
        raise P7ProtocolError("P7 live execution is forbidden")
    if engine.get("serving_dependency_allowed") is not False:
        raise P7ProtocolError("P7 serving dependency is forbidden")
    if engine.get("prerelease_allowed") is not False:
        raise P7ProtocolError("P7 prerelease engine is forbidden")

    parity = raw["parity"]
    if parity.get("mode") != "DETERMINISTIC_OFFLINE_BACKTEST_SMOKE":
        raise P7ProtocolError("P7 parity mode changed")
    if int(parity.get("bar_count", 0)) < 32:
        raise P7ProtocolError("P7 parity bar count too small")
    if int(parity.get("deterministic_repeats", 0)) < 2:
        raise P7ProtocolError("P7 deterministic repeat gate weakened")
    required = parity.get("required") or {}
    for key in (
        "exact_engine_version",
        "monotonic_event_time",
        "processed_bar_count_equals_input",
        "ending_position_flat",
        "repeated_result_digest_equal",
        "finite_account_values",
        "no_network_market_data",
        "no_live_adapter",
        "no_external_order_action",
    ):
        if required.get(key) is not True:
            raise P7ProtocolError(f"P7 parity invariant weakened: {key}")
    if int(required.get("minimum_fill_count", 0)) < 2:
        raise P7ProtocolError("P7 fill-count gate weakened")
    if parity.get("predictive_performance_claim_allowed") is not False:
        raise P7ProtocolError("P7 parity cannot claim predictive performance")
    if parity.get("trading_edge_claim_allowed") is not False:
        raise P7ProtocolError("P7 parity cannot claim trading edge")

    cost = raw["cost_diagnostic"]
    if list(cost.get("presets") or []) != ["ZERO_COST", "BASE_COST", "STRESS_COST"]:
        raise P7ProtocolError("P7 cost presets changed")
    if cost.get("actual_execution_cost_claim_allowed") is not False:
        raise P7ProtocolError("P7 cost proxy cannot become actual execution cost")
    if cost.get("edge_claim_allowed") is not False:
        raise P7ProtocolError("P7 cost diagnostic cannot claim edge")

    paper = raw["paper_acceptance"]
    if paper.get("live_paper_broker_session_allowed") is not False:
        raise P7ProtocolError("P7 live paper broker session is forbidden")
    for key, value in (paper.get("required") or {}).items():
        if value is not True:
            raise P7ProtocolError(f"P7 paper acceptance weakened: {key}")

    migration = raw["migration_acceptance"]
    if migration.get("require_data_root_outside_git") is not True:
        raise P7ProtocolError("P7 data-root isolation gate weakened")
    if migration.get("require_isolated_engine_outside_core_venv") is not True:
        raise P7ProtocolError("P7 engine isolation gate weakened")
    if migration.get("require_runtime_rebuild_recipe") is not True:
        raise P7ProtocolError("P7 runtime rebuild recipe required")
    if migration.get("copy_secrets_allowed") is not False:
        raise P7ProtocolError("P7 secret copy is forbidden")
    if migration.get("runtime_handover_allowed") is not False:
        raise P7ProtocolError("P7 runtime handover is forbidden")
    if migration.get("active_recorder_restart_allowed") is not False:
        raise P7ProtocolError("P7 recorder restart is forbidden")

    completion = set(raw["completion"].get("does_not_require") or [])
    required_not = {
        "NEW_FORWARD_OUTCOMES",
        "PREDICTIVE_GAIN",
        "CALIBRATION",
        "TRADING_EDGE",
        "P6_CONDITIONAL_FEATURE",
    }
    if not required_not <= completion:
        raise P7ProtocolError("P7 completion boundary weakened")


def load_p7_protocol(
    protocol_id: str = P7_DEFAULT_PROTOCOL_ID,
    path: str | Path | None = None,
) -> P7Protocol:
    p = Path(path) if path is not None else P7_DEFAULT_PROTOCOL_PATH
    payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if str(payload.get("schema_version")) != P7_SCHEMA_VERSION:
        raise P7ProtocolError("P7 protocol schema mismatch")
    raw = (payload.get("protocols") or {}).get(protocol_id)
    if not isinstance(raw, dict):
        raise KeyError(protocol_id)
    _validate(raw)
    return P7Protocol(protocol_id=protocol_id, raw=raw)
