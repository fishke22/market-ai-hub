"""Restore/merge the latest GitHub Actions P5 cloud-state artifact."""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import zipfile

import requests

from market_ai_hub.config.runtime_paths import data_root
from market_ai_hub.research.accuracy_v2_p5_engine import (
    HORIZON, INSTRUMENT, MODEL_NAME, MODEL_VERSION, SAMPLE_ORIGIN, TARGET_FAMILY,
)
from market_ai_hub.research.v2 import prediction_audit as PA

DEFAULT_REPO = "fishke22/market-ai-hub"
DEFAULT_ARTIFACT = "p5-cloud-state"
ALLOWED_STATE_PATHS = {
    "audit/prediction_audit.duckdb",
    "automation/p5_forward_state.json",
    "cloud/p5_cloud_run_summary.json",
    "cloud/p5_cloud_state_manifest.json",
}


def _token() -> str:
    value = os.environ.get("GITHUB_TOKEN", "").strip()
    if value:
        return value
    proc = subprocess.run(
        ["gh", "auth", "token"], check=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True,
    )
    value = proc.stdout.strip()
    if not value:
        raise RuntimeError("GITHUB_TOKEN_UNAVAILABLE")
    return value


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "MARKET_AI_HUB-P5-cloud-sync",
    }


def latest_artifact(repo: str, artifact_name: str, *, token: str) -> dict[str, Any] | None:
    response = requests.get(
        f"https://api.github.com/repos/{repo}/actions/artifacts",
        params={"name": artifact_name, "per_page": 100},
        headers=_headers(token), timeout=30,
    )
    response.raise_for_status()
    rows = [
        row for row in response.json().get("artifacts", [])
        if row.get("name") == artifact_name and not row.get("expired", False)
    ]
    if not rows:
        return None
    return sorted(rows, key=lambda x: (x.get("created_at") or "", int(x.get("id") or 0)))[-1]


def download_artifact_zip(artifact: dict[str, Any], *, token: str) -> bytes:
    url = str(artifact.get("archive_download_url") or "")
    if not url:
        raise RuntimeError("ARTIFACT_DOWNLOAD_URL_MISSING")
    response = requests.get(url, headers=_headers(token), timeout=60, allow_redirects=True)
    response.raise_for_status()
    return bytes(response.content)


def safe_extract_state(archive: bytes, destination: Path) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/").lstrip("./")
            if name.endswith("/") or name not in ALLOWED_STATE_PATHS:
                continue
            target = destination / Path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(name)
    return sorted(extracted)


def restore_latest_cloud_state(
    *, repo: str = DEFAULT_REPO, artifact_name: str = DEFAULT_ARTIFACT,
    destination: Path | None = None,
) -> dict[str, Any]:
    token = _token()
    artifact = latest_artifact(repo, artifact_name, token=token)
    if artifact is None:
        return {"status": "NO_PRIOR_ARTIFACT", "artifact_name": artifact_name}
    dest = destination or data_root()
    files = safe_extract_state(download_artifact_zip(artifact, token=token), dest)
    manifest = dest / "cloud" / "p5_cloud_state_manifest.json"
    if manifest.is_file():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("state_valid") is not True or payload.get("public_sources_only") is not True:
            raise RuntimeError("CLOUD_STATE_MANIFEST_INVALID")
    return {
        "status": "RESTORED",
        "artifact_id": int(artifact["id"]),
        "created_at": artifact.get("created_at"),
        "files": files,
    }


def _p5_scope(pred: PA.PredictionRecord) -> bool:
    return (
        pred.target_family == TARGET_FAMILY
        and pred.instrument == INSTRUMENT
        and pred.horizon == HORIZON
        and pred.model == MODEL_NAME
        and pred.model_version == MODEL_VERSION
        and pred.sample_origin == SAMPLE_ORIGIN
    )


def merge_cloud_p5_audit(cloud_db_path: Path, local_db_path: Path) -> dict[str, int]:
    counts = {
        "cloud_predictions": 0, "p5_predictions": 0,
        "prediction_inserts_or_idempotent": 0,
        "outcome_inserts_or_idempotent": 0, "skipped_non_p5": 0,
    }
    if not cloud_db_path.is_file():
        return counts
    cloud = PA.PredictionAuditDB(cloud_db_path, read_only=True)
    local = PA.PredictionAuditDB(local_db_path)
    for pid in cloud.list_prediction_ids():
        counts["cloud_predictions"] += 1
        pred = cloud.get_prediction(pid)
        if pred is None or not _p5_scope(pred):
            counts["skipped_non_p5"] += 1
            continue
        counts["p5_predictions"] += 1
        local.append_prediction_bundle(
            pred, cloud.get_lineage(pid), cloud.get_forecast_artifacts(pid)
        )
        counts["prediction_inserts_or_idempotent"] += 1
        for outcome in cloud.get_outcomes(pid):
            local.append_outcome(outcome)
            counts["outcome_inserts_or_idempotent"] += 1
    return counts


def merge_latest_into_local(
    *, repo: str = DEFAULT_REPO, artifact_name: str = DEFAULT_ARTIFACT,
) -> dict[str, Any]:
    root = data_root()
    with tempfile.TemporaryDirectory(prefix="p5_cloud_sync_") as td:
        temp_root = Path(td)
        restored = restore_latest_cloud_state(
            repo=repo, artifact_name=artifact_name, destination=temp_root
        )
        if restored["status"] == "NO_PRIOR_ARTIFACT":
            return restored
        merge = merge_cloud_p5_audit(
            temp_root / "audit" / "prediction_audit.duckdb",
            PA.default_audit_db_path(),
        )
        cloud_dir = root / "cloud" / "p5"
        cloud_dir.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for source_rel, dest_name in (
            ("automation/p5_forward_state.json", "cloud_p5_forward_state.json"),
            ("cloud/p5_cloud_run_summary.json", "latest_run_summary.json"),
            ("cloud/p5_cloud_state_manifest.json", "latest_state_manifest.json"),
        ):
            src = temp_root / Path(source_rel)
            if src.is_file():
                shutil.copy2(src, cloud_dir / dest_name)
                copied.append(dest_name)
        return {**restored, "merge": merge, "local_cloud_files": copied}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("restore", "merge-local"), default="merge-local")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--artifact-name", default=DEFAULT_ARTIFACT)
    args = ap.parse_args()
    result = (
        restore_latest_cloud_state(repo=args.repo, artifact_name=args.artifact_name)
        if args.mode == "restore"
        else merge_latest_into_local(repo=args.repo, artifact_name=args.artifact_name)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
