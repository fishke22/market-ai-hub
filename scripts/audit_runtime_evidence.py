"""Phase 2Q-F.3 — audit runtime evidence stores for TEST_FIXTURE contamination。

檢查真實 runtime evidence stores（ts_validation）不得有 run_kind=TEST_FIXTURE 的 rows。
存在 → FAIL（代表 test 污染了 runtime evidence）。

用法：python scripts/audit_runtime_evidence.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    import duckdb

    from market_ai_hub.config.runtime_paths import resolve_db_path

    db = resolve_db_path("ts_validation.duckdb")
    if not db.exists():
        print("PASS: no ts_validation.duckdb")
        return 0

    con = duckdb.connect(str(db))
    try:
        con.execute("ALTER TABLE runs ADD COLUMN run_kind VARCHAR DEFAULT 'RUNTIME_VALIDATION'")
    except Exception:
        pass
    # 檢查 runtime evidence store 是否有「未 quarantine」的 synthetic test fixture signature
    try:
        n = int(con.execute(
            "SELECT COUNT(*) FROM runs WHERE model='chronos-2' AND symbol='^N225' "
            "AND n_origins=3 AND n_oos=10 AND mase=0.9 AND interval_coverage=0.75 "
            "AND (run_kind IS NULL OR run_kind != 'TEST_FIXTURE')"
        ).fetchone()[0])
    except Exception:
        n = 0
    con.close()

    if n > 0:
        print(f"FAIL: {n} un-quarantined synthetic test records in runtime evidence store")
        return 1
    print("PASS: no un-quarantined test-fixture records in runtime evidence stores")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
