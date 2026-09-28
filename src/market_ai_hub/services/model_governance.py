"""Accuracy v2 model identity, capability, and usage-purpose governance."""
from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any

import yaml

from market_ai_hub.config.settings import project_root


class ModelUsageBlocked(RuntimeError):
    """Fail-closed model usage gate."""


class ModelRevisionMismatch(RuntimeError):
    """Registry revision and observed runtime revision disagree."""


TIMESFM3_PERSONAL_RESEARCH_ACK = "PERSONAL_NONCOMMERCIAL_NONPRODUCTION_RESEARCH"
TIMESFM3_RESEARCH_USAGE_SCHEMA = "TIMESFM3_RESEARCH_USAGE_V1"


def load_model_registry() -> dict[str, Any]:
    path = project_root() / "config" / "model_registry.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def model_entry(name: str) -> dict[str, Any]:
    for entry in load_model_registry().get("models", []):
        if entry.get("name") == name:
            return entry
    raise KeyError(name)


def expected_model_revision(name: str) -> str:
    revision = str(model_entry(name).get("revision") or "").strip()
    if not revision or revision.lower() in {"unknown", "latest"}:
        raise ModelRevisionMismatch(f"{name}: registry revision is not pinned")
    return revision


def model_use_gate(name: str, purpose: str | None) -> dict[str, Any]:
    """Return a stable usage decision; unknown purpose is always blocked."""
    entry = model_entry(name)
    requested = str(purpose or "UNKNOWN").strip().upper()
    allowed = {str(x).upper() for x in entry.get("allowed_purposes", [])}
    if not allowed:
        allowed = {"RESEARCH", "SERVING"} if entry.get("commercial_use") is True else {"RESEARCH"}
    allowed_now = requested in allowed
    reason = "ALLOWED" if allowed_now else (
        "PURPOSE_REQUIRED" if requested == "UNKNOWN"
        else f"PURPOSE_{requested}_NOT_ALLOWED"
    )
    return {
        "model": name,
        "purpose": requested,
        "allowed": allowed_now,
        "reason": reason,
        "allowed_purposes": sorted(allowed),
        "code_license": entry.get("code_license"),
        "weight_license": entry.get("weight_license"),
        "commercial_use": entry.get("commercial_use"),
    }


def require_model_use(name: str, purpose: str | None) -> dict[str, Any]:
    decision = model_use_gate(name, purpose)
    if not decision["allowed"]:
        raise ModelUsageBlocked(
            f"{name}: {decision['reason']} (allowed={decision['allowed_purposes']})"
        )
    return decision


def observed_revision_from_loaded(model: Any) -> str | None:
    """Best-effort runtime commit evidence without treating cache presence as load evidence."""
    candidates = [
        model,
        getattr(model, "model", None),
        getattr(model, "_model", None),
        getattr(getattr(model, "model", None), "config", None),
        getattr(getattr(model, "_model", None), "config", None),
        getattr(model, "config", None),
    ]
    for obj in candidates:
        if obj is None:
            continue
        for attr in ("_commit_hash", "commit_hash", "revision", "_revision"):
            value = getattr(obj, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def verify_loaded_revision(name: str, loaded: Any) -> dict[str, Any]:
    expected = expected_model_revision(name)
    observed = observed_revision_from_loaded(loaded)
    if observed and observed != expected:
        raise ModelRevisionMismatch(
            f"{name}: observed revision {observed} != registry {expected}"
        )
    return {
        "expected_revision": expected,
        "observed_revision": observed,
        "local_verified": observed == expected,
        "verification_reason": "RUNTIME_COMMIT_MATCH" if observed == expected else "RUNTIME_COMMIT_NOT_EXPOSED",
    }


def package_version(dist_name: str) -> str:
    try:
        return metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def exact_snapshot_present(model_id: str, cache_dir: Path, revision: str) -> bool:
    slug = "models--" + model_id.replace("/", "--")
    candidates = [
        cache_dir / slug / "snapshots" / revision,
        cache_dir / "snapshots" / revision,
    ]
    return any(p.is_dir() for p in candidates)


def model_capability_inventory(name: str, *, cache_dir: Path | None = None) -> dict[str, Any]:
    entry = model_entry(name)
    model_id = str(entry.get("model_id") or "")
    revision = expected_model_revision(name)
    dist = {"chronos-2": "chronos-forecasting", "timesfm-3.0": "timesfm"}.get(name, "")
    upstream = dict(entry.get("upstream_support") or {})
    implemented = dict(entry.get("adapter_implemented") or {})
    verified = dict(entry.get("local_verified") or {})
    if cache_dir is not None and model_id:
        verified["expected_snapshot_present"] = exact_snapshot_present(
            model_id, cache_dir, revision
        )
    return {
        "name": name,
        "model_id": model_id,
        "registry_revision": revision,
        "package": dist,
        "package_version": package_version(dist) if dist else "n/a",
        "code_license": entry.get("code_license"),
        "weight_license": entry.get("weight_license"),
        "commercial_use": entry.get("commercial_use"),
        "registry_hash": entry.get("file_hash") or f"hf_commit:{revision}",
        "upstream_support": upstream,
        "adapter_implemented": implemented,
        "local_verified": verified,
        "usage": model_use_gate(name, "RESEARCH"),
        "serving": model_use_gate(name, "SERVING"),
    }


def timesfm3_research_access_gate(
    acknowledgement: str | None,
    *,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Fail-closed local research gate for TimesFM-3 pretrained weights.

    This is deliberately stricter than the generic RESEARCH purpose gate:
    personal/non-commercial/non-production use must be acknowledged explicitly,
    the exact installed package and pinned local snapshot must exist, and no
    automatic download is allowed.
    """
    registry = load_model_registry()
    entry = model_entry("timesfm-3.0")
    revision = expected_model_revision("timesfm-3.0")
    model_id = str(entry.get("model_id") or "")
    expected_package = str(entry.get("package_version") or "").strip()
    actual_package = package_version("timesfm")
    cache = cache_dir or (project_root() / "models" / "cache" / "timesfm-3.0")
    fp = __import__(
        "market_ai_hub.services.build_info",
        fromlist=["build_fingerprint"],
    ).build_fingerprint()

    failures: list[str] = []
    if registry.get("schema_version") != 2:
        failures.append("MODEL_REGISTRY_SCHEMA_MISMATCH")
    if str(acknowledgement or "").strip() != TIMESFM3_PERSONAL_RESEARCH_ACK:
        failures.append("PERSONAL_RESEARCH_ACK_REQUIRED")
    if model_use_gate("timesfm-3.0", "RESEARCH")["allowed"] is not True:
        failures.append("RESEARCH_PURPOSE_NOT_ALLOWED")
    if entry.get("commercial_use") is not False or entry.get("production_use") is not False:
        failures.append("NONCOMMERCIAL_NONPRODUCTION_CONTRACT_MISMATCH")
    if entry.get("personal_noncommercial_research") is not True:
        failures.append("PERSONAL_RESEARCH_CONTRACT_MISMATCH")
    if entry.get("weight_license") != "timesfm-non-commercial-license-v1.0":
        failures.append("WEIGHT_LICENSE_MISMATCH")
    if not expected_package or actual_package != expected_package:
        failures.append("PACKAGE_VERSION_MISMATCH")
    if not model_id or not exact_snapshot_present(model_id, cache, revision):
        failures.append("PINNED_SNAPSHOT_MISSING")
    if not str(fp.get("build_id") or "").strip():
        failures.append("BUILD_FINGERPRINT_MISSING")

    return {
        "schema_version": TIMESFM3_RESEARCH_USAGE_SCHEMA,
        "model": "timesfm-3.0",
        "model_id": model_id,
        "revision": revision,
        "package_version_expected": expected_package,
        "package_version_observed": actual_package,
        "weight_license": entry.get("weight_license"),
        "code_license": entry.get("code_license"),
        "usage_mode": "PERSONAL_NONCOMMERCIAL_NONPRODUCTION_RESEARCH",
        "allowed": not failures,
        "reason": "ALLOWED" if not failures else failures[0],
        "failures": failures,
        "local_files_only": True,
        "automatic_download_allowed": False,
        "commercial_use_allowed": False,
        "production_use_allowed": False,
        "future_covariates_allowed": False,
        "past_only_covariates_allowed": True,
        "build_id": fp.get("build_id"),
    }


def require_timesfm3_research_access(
    acknowledgement: str | None,
    *,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    decision = timesfm3_research_access_gate(acknowledgement, cache_dir=cache_dir)
    if not decision["allowed"]:
        raise ModelUsageBlocked(
            f"timesfm-3.0 research access blocked: {decision['reason']}"
        )
    return decision
