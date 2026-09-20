"""Phase 2Q-F.3 — audit ts_validation store for synthetic test records.

辨識 confirmed synthetic signature（test_oos_validation._good_result）：
chronos-2 / ^N225 / n_origins=3 / n_oos=10 / mase=0.9 / interval_coverage=0.75 / beats_naive=true。

dry-run 只輸出 QUARANTINE_CANDIDATE；--apply 才把 100% match 的 rows 標 run_kind=TEST_FIXTURE。
不刪 legitimate historical validation runs。

用法：python scripts/audit_validation_store.py [--apply]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _synthetic_signature(r: dict) -> bool:
    return (
        r.get("model") == "chronos-2"
        and r.get("symbol") == "^N225"
        and int(r.get("n_origins") or 0) == 3
        and int(r.get("n_oos") or 0) == 10
        and (r.get("mase") is not None and abs(r["mase"] - 0.9) < 1e-6)
        and (r.get("interval_coverage") is not None and abs(r["interval_coverage"] - 0.75) < 1e-6)
        and r.get("beats_naive") is True
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    import duckdb

    from market_ai_hub.config.runtime_paths import data_root, resolve_db_path

    db = resolve_db_path("ts_validation.duckdb")
    if not db.exists():
        print("no ts_validation.duckdb")
        return 0

    if args.apply:
        backup = data_root() / "backups" / f"ts_validation.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.duckdb"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db, backup)
        print(f"backup -> {backup}")

    con = duckdb.connect(str(db))
    try:
        con.execute("ALTER TABLE runs ADD COLUMN run_kind VARCHAR DEFAULT 'RUNTIME_VALIDATION'")
    except Exception:
        pass
    rows = con.execute("SELECT rowid, * FROM runs").df().to_dict("records")
    candidates = [r for r in rows if _synthetic_signature(r)]

    print(f"total runs: {len(rows)}, QUARANTINE_CANDIDATE: {len(candidates)}")
    for r in candidates:
        print(f"  rowid={r['rowid']} model={r['model']} symbol={r['symbol']} n_origins={r['n_origins']} mase={r['mase']}")

    if args.apply:
        for r in candidates:
            con.execute("UPDATE runs SET run_kind='TEST_FIXTURE' WHERE rowid=?", [r["rowid"]])
        print(f"quarantined {len(candidates)} rows (run_kind=TEST_FIXTURE)")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
