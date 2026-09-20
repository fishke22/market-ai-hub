"""Phase 2Q-C.1 — runtime/data path resolver（single source of path truth）。

MARKET_AI_DATA_ROOT 為 optional env override；預設 <ProjectRoot>\\data。
所有 runtime / data / private inbox / raw archive / normalized 路徑由此 resolver 產生。
禁止 code 硬編 D:\\ 或 project sibling 資料夾。
"""
from __future__ import annotations

import os
from pathlib import Path

from market_ai_hub.config.settings import project_root

_ENV_OVERRIDE = "MARKET_AI_DATA_ROOT"

# legacy 本機 hardcoded private inbox（Phase 2Q-C.1 前）——僅用於 migration detection。
LEGACY_PRIVATE_INBOX = Path("D:/MARKET_AI_HUB_PRIVATE_INBOX/225labo")


def data_root() -> Path:
    """<DATA_ROOT>：env MARKET_AI_DATA_ROOT 優先，否則 <ProjectRoot>/data。"""
    override = os.environ.get(_ENV_OVERRIDE, "").strip()
    if override:
        return Path(override).expanduser()
    return project_root() / "data"


def private_inbox_dir() -> Path:
    """225LABO private inbox：<DATA_ROOT>/private/inbox/225labo。"""
    return data_root() / "private" / "inbox" / "225labo"


def raw_archive_dir() -> Path:
    """225LABO raw archive（immutable source copy）：<DATA_ROOT>/raw/ylab225/archive。"""
    return data_root() / "raw" / "ylab225" / "archive"


def normalized_ose_micro_dir() -> Path:
    """normalized OSE micro bars：<DATA_ROOT>/normalized/ose_micro。"""
    return data_root() / "normalized" / "ose_micro"


def ose_micro_bars_path() -> Path:
    return normalized_ose_micro_dir() / "ose_micro_daily_bar_v1.parquet"


# ── 2Q-F：完整 canonical resolver ──
def db_root() -> Path:
    return data_root() / "db"


def logs_root() -> Path:
    return data_root() / "logs"


def app_logs_root() -> Path:
    return logs_root() / "app"


def lightning_logs_root() -> Path:
    return logs_root() / "lightning"


def research_outputs_root() -> Path:
    return data_root() / "research_outputs"


def forward_outputs_root() -> Path:
    return research_outputs_root() / "forward"


def performance_outputs_root() -> Path:
    return research_outputs_root() / "performance"


def validation_outputs_root() -> Path:
    return research_outputs_root() / "validation"


def coverage_outputs_root() -> Path:
    return research_outputs_root() / "coverage"


def status_outputs_root() -> Path:
    return research_outputs_root() / "status"


def diagnostics_root() -> Path:
    return data_root() / "diagnostics"


def integration_outputs_root(name: str) -> Path:
    return diagnostics_root() / name


def backups_root() -> Path:
    return data_root() / "backups"


def private_root() -> Path:
    return data_root() / "private"


# ── DB paths（legacy fallback：新 layout 缺檔時可讀 legacy <DATA_ROOT>/<name>.duckdb）──
def db_path(name: str) -> Path:
    return db_root() / name


def legacy_db_path(name: str) -> Path:
    return data_root() / name


def resolve_db_path(name: str) -> Path:
    """prefer new <DATA_ROOT>/db/<name>；若不存在且 legacy <DATA_ROOT>/<name> 存在 → legacy（LEGACY_LAYOUT_DETECTED）。"""
    new = db_path(name)
    if new.exists():
        return new
    legacy = legacy_db_path(name)
    if legacy.exists():
        return legacy
    return new


def legacy_inbox_status() -> str:
    """detect legacy D:\\MARKET_AI_HUB_PRIVATE_INBOX\\225labo（migration only，不刪除/不移動）。"""
    if not LEGACY_PRIVATE_INBOX.exists():
        return "NONE"
    entries = list(LEGACY_PRIVATE_INBOX.iterdir()) if LEGACY_PRIVATE_INBOX.is_dir() else [LEGACY_PRIVATE_INBOX]
    if not entries:
        return "LEGACY_EMPTY_INBOX"
    return "LEGACY_PRIVATE_DATA_FOUND"


def ensure_runtime_dirs() -> list[Path]:
    """explicit init operation：建立 runtime 需要的目錄。import / health / status 不得呼叫此函式。"""
    dirs = [
        private_inbox_dir(), raw_archive_dir(), normalized_ose_micro_dir(),
        db_root(), logs_root(), lightning_logs_root(),
        forward_outputs_root(), performance_outputs_root(), validation_outputs_root(),
        coverage_outputs_root(), status_outputs_root(), diagnostics_root(), backups_root(),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    return dirs
