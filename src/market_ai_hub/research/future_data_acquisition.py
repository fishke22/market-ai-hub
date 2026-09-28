"""Accuracy v2 future-data acquisition manifest and fail-closed readiness checks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from market_ai_hub.config.settings import project_root


SCHEMA_VERSION = "AV2DATA.1"
DEFAULT_PATH = project_root() / "config" / "future_data_acquisition.yaml"


class FutureDataPlanError(ValueError):
    pass


@dataclass(frozen=True)
class FutureDataSource:
    source_id: str
    raw: dict[str, Any]

    @property
    def status(self) -> str:
        return str(self.raw.get("status") or "")

    @property
    def collector(self) -> str:
        return str(self.raw.get("collector") or "")

    @property
    def active_public_collector(self) -> bool:
        return self.raw.get("acquisition") == "PUBLIC_HTTP" and self.status == "ACTIVE_PUBLIC_COLLECTOR"


def load_future_data_plan(path: str | Path | None = None) -> tuple[dict[str, Any], dict[str, FutureDataSource]]:
    p = Path(path) if path is not None else DEFAULT_PATH
    payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if str(payload.get("schema_version")) != SCHEMA_VERSION:
        raise FutureDataPlanError("future-data plan schema mismatch")
    policy = payload.get("policy") or {}
    required_true = {
        "public_only_or_already_authorized_quote_sources",
        "no_paid_data_required",
        "no_order_or_account_access",
        "no_broker_login_or_recorder_restart",
        "available_at_is_observed_receipt_unless_official_publication_time_is_explicit",
        "no_future_fill",
        "no_continuous_proxy_for_exact_contract_task",
    }
    if any(policy.get(key) is not True for key in required_true):
        raise FutureDataPlanError("future-data safety/PIT policy weakened")
    if policy.get("raw_private_market_data_committed_to_git") is not False:
        raise FutureDataPlanError("private market data may not be committed")

    sources = payload.get("sources") or {}
    if not isinstance(sources, dict) or not sources:
        raise FutureDataPlanError("future-data sources missing")
    out: dict[str, FutureDataSource] = {}
    for source_id, raw in sources.items():
        if not isinstance(raw, dict):
            raise FutureDataPlanError(f"invalid source definition: {source_id}")
        if raw.get("exact_contract") is not True:
            raise FutureDataPlanError(f"exact contract requirement missing: {source_id}")
        acquisition = str(raw.get("acquisition") or "")
        status = str(raw.get("status") or "")
        if "BLOCKED" in status and acquisition != "DISABLED":
            raise FutureDataPlanError(f"blocked source must be disabled: {source_id}")
        if acquisition == "EXISTING_RECORDER_ONLY" and raw.get("collector") != "EXISTING_SINGLE_OWNER_RECORDER":
            raise FutureDataPlanError(f"recorder source must preserve existing owner: {source_id}")
        out[str(source_id)] = FutureDataSource(str(source_id), dict(raw))
    return dict(policy), out


def collect_public_sources(
    *,
    taifex_start: str = "",
    taifex_end: str = "",
) -> dict[str, Any]:
    """Refresh official/public sources only; never touches broker/session ownership."""
    from datetime import datetime, timedelta, timezone

    from market_ai_hub.providers.taifex import TaifexProvider
    from market_ai_hub.research.accuracy_v2_p3b_taifex import materialize_tmf_settlement_snapshot
    from market_ai_hub.services.jnu_direct import refresh_jnu_direct_data

    now = datetime.now(timezone.utc)
    start = taifex_start or (now - timedelta(days=28)).strftime("%Y/%m/%d")
    end = taifex_end or now.strftime("%Y/%m/%d")
    result: dict[str, Any] = {
        "schema_version": "AV2PUBLICCOLLECT.2",
        "started_at": now.isoformat(),
        "broker_used": False,
        "credentials_used": False,
        "recorder_touched": False,
        "order_action": False,
        "jpx": refresh_jnu_direct_data(force=True),
    }
    try:
        snap = TaifexProvider().fetch_daily_snapshot("TMF", start=start, end=end)
        summary = materialize_tmf_settlement_snapshot(snap)
        result["taifex_tmf"] = {
            key: value for key, value in summary.items() if key != "results"
        }
        result["taifex_tmf"]["blocked_reasons"] = sorted({
            str(row.get("reason"))
            for row in summary.get("results", [])
            if row.get("status") == "BLOCKED" and row.get("reason")
        })
    except Exception as exc:
        result["taifex_tmf"] = {
            "status": "REFRESH_FAILED",
            "error": type(exc).__name__,
        }
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    return result


def future_data_readiness(path: str | Path | None = None) -> dict[str, Any]:
    policy, sources = load_future_data_plan(path)
    active_public = sorted(k for k, v in sources.items() if v.active_public_collector)
    blocked = sorted(k for k, v in sources.items() if "BLOCKED" in v.status)
    prebuilt = sorted(k for k, v in sources.items() if "PREBUILD" in v.status or "PREEXISTING" in v.status)
    return {
        "schema_version": SCHEMA_VERSION,
        "policy": policy,
        "active_public_collectors": active_public,
        "blocked_sources": blocked,
        "prebuilt_or_existing_quote_paths": prebuilt,
        "orders_allowed": False,
        "account_access_allowed": False,
        "recorder_restart_allowed": False,
    }
