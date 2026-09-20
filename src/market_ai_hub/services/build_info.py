"""Build identity / version fingerprint（V1.1 + 2Q-D）。

讓外部 Agent 能確認自己正在使用哪一份 code、哪個 process：
- market_ai_version：人讀版本
- release_version：release 版本
- build_id：全部 runtime source + runtime config 內容的 sha256（code/config 一變 id 就變）
- git_commit / source_root / python_executable / server_started_at / schema_version

2Q-D 修正：build_id 涵蓋所有會影響 runtime semantics 的 src/**/*.py 與 runtime config，
純 docs/tests 不改變 build_id。
"""
from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MARKET_AI_VERSION = "1.1.0"
RELEASE_VERSION = "v2.0.0-rc1"
SCHEMA_VERSION = "1.1"

SOURCE_ROOT = Path(__file__).resolve().parents[3]

# runtime config（內容變 → build_id 變）
RUNTIME_CONFIG_FILES = [
    "config/model_registry.yaml",
    "config/model_manifest.yaml",
    "config/primary_targets.yaml",
    "config/resource_profiles.yaml",
    "config/model_resource_requirements.yaml",
    "config/symbols.yaml",
]


def _fingerprint_paths() -> list[Path]:
    """全部 runtime source + runtime config（sorted，deterministic）。"""
    src_dir = SOURCE_ROOT / "src" / "market_ai_hub"
    paths: list[Path] = []
    if src_dir.exists():
        paths.extend(p for p in src_dir.rglob("*.py") if "__pycache__" not in p.parts)
    for cfg in RUNTIME_CONFIG_FILES:
        p = SOURCE_ROOT / cfg
        if p.exists():
            paths.append(p)
    return sorted(paths)


def _compute_build_id() -> str:
    h = hashlib.sha256()
    for p in _fingerprint_paths():
        rel = p.relative_to(SOURCE_ROOT).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


BUILD_ID = _compute_build_id()
SERVER_STARTED_AT = datetime.now(timezone.utc).isoformat()

try:
    GIT_COMMIT = subprocess.run(
        ["git", "-C", str(SOURCE_ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip() or "N/A (not a git repo)"
except Exception:
    GIT_COMMIT = "N/A (not a git repo)"


def build_fingerprint() -> dict:
    return {
        "market_ai_version": MARKET_AI_VERSION,
        "release_version": RELEASE_VERSION,
        "build_id": BUILD_ID,
        "runtime_build_id": BUILD_ID,  # 內容 hash（非 git commit prefix）；build_id 為 backward-compat alias
        "git_commit": GIT_COMMIT,
        "source_root": str(SOURCE_ROOT),
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "server_started_at": SERVER_STARTED_AT,
        "schema_version": SCHEMA_VERSION,
    }
