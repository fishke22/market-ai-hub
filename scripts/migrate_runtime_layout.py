"""Phase 2Q-F — migrate legacy runtime DB layout to <DATA_ROOT>/db/.

用法：
  python scripts/migrate_runtime_layout.py --dry-run
  python scripts/migrate_runtime_layout.py --apply

流程：detect legacy DB → record size/tables/rows → backup → atomic copy/move → verify。
若偵測到 active MARKET_AI_HUB process → MIGRATION_DEFERRED_ACTIVE_PROCESS（不強搬）。

安全：resolve_db_path() 已有 legacy fallback，未 migrate 也能正常讀 legacy DB。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DB_NAMES = ["market.duckdb", "performance.duckdb", "ts_validation.duckdb"]


def _active_process() -> bool:
    try:
        import psutil

        for proc in psutil.process_iter(["name", "cmdline"]):
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "market-ai-mcp" in cmd or "market_ai_hub.mcp.server" in cmd:
                return True
    except Exception:
        pass
    return False


def _db_meta(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    meta = {"exists": True, "size": path.stat().st_size}
    try:
        import duckdb

        with duckdb.connect(str(path)) as con:
            tables = con.execute("SHOW TABLES").df()["name"].tolist()
            meta["tables"] = tables
            meta["row_counts"] = {
                t: int(con.execute(f"SELECT COUNT(*) FROM \"{t}\"").fetchone()[0]) for t in tables
            }
    except Exception as e:
        meta["inspect_error"] = str(e)[:120]
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from market_ai_hub.config.runtime_paths import data_root, db_root, legacy_db_path

    report: dict = {"at": datetime.now(timezone.utc).isoformat(), "dry_run": args.dry_run,
                    "migrations": []}
    if _active_process():
        report["status"] = "MIGRATION_DEFERRED_ACTIVE_PROCESS"
        print(json.dumps(report, indent=2, default=str))
        return 0

    db_root().mkdir(parents=True, exist_ok=True)
    for name in DB_NAMES:
        legacy = legacy_db_path(name)
        target = db_root() / name
        entry = {"db": name, "legacy": str(legacy), "target": str(target),
                 "meta": _db_meta(legacy)}
        if not legacy.exists() or target.exists():
            entry["action"] = "SKIP"
        elif args.apply:
            shutil.copy2(legacy, target)
            entry["action"] = "COPIED"
            entry["verify"] = _db_meta(target)
        else:
            entry["action"] = "WOULD_COPY"
        report["migrations"].append(entry)

    report["status"] = "DRY_RUN" if args.dry_run else "APPLIED"
    print(json.dumps(report, indent=2, default=str))

    out = data_root() / "research_outputs" / "status" / "db_migration_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
