"""Build identity / version fingerprint（V1.1）。

讓外部 Agent 能確認自己正在使用哪一份 code、哪個 process：
- market_ai_version：人讀版本
- build_id：關鍵 source 檔內容的 sha256（code 一變 id 就變）
- git_commit：N/A（本專案非 git repo）
- source_root / python_executable / server_started_at / schema_version

build_id 在 server 啟動時計算一次（import 時），供所有 response 引用。
"""
from __future__ import annotations

import hashlib
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

MARKET_AI_VERSION = "1.1.0"
SCHEMA_VERSION = "1.1"

SOURCE_ROOT = Path(__file__).resolve().parents[3]

FINGERPRINTED_FILES = [
    "mcp/server.py",
    "services/analysis.py",
    "services/horizon.py",
    "services/model_catalog.py",
    "services/validation.py",
    "models/chronos_model.py",
    "models/timesfm_model.py",
    "models/baseline_ml.py",
    "ensemble/ensemble.py",
    "features/features.py",
    "backtest/walk_forward.py",
    "schemas/market_data.py",
    "schemas/backtest.py",
]


def _compute_build_id() -> str:
    h = hashlib.sha256()
    for rel in FINGERPRINTED_FILES:
        p = SOURCE_ROOT / "src" / "market_ai_hub" / rel
        if p.exists():
            h.update(rel.encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


BUILD_ID = _compute_build_id()
SERVER_STARTED_AT = datetime.now(timezone.utc).isoformat()

try:
    import subprocess

    GIT_COMMIT = subprocess.run(
        ["git", "-C", str(SOURCE_ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip() or "N/A (not a git repo)"
except Exception:
    GIT_COMMIT = "N/A (not a git repo)"


def build_fingerprint() -> dict:
    return {
        "market_ai_version": MARKET_AI_VERSION,
        "build_id": BUILD_ID,
        "git_commit": GIT_COMMIT,
        "source_root": str(SOURCE_ROOT),
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "server_started_at": SERVER_STARTED_AT,
        "schema_version": SCHEMA_VERSION,
    }
