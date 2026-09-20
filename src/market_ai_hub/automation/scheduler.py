"""Phase 2E — Scheduler 狀態（DuckDB）+ 自主循環 orchestrator。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from market_ai_hub.automation.data_lake import default_data_root

log = logging.getLogger(__name__)

JOBS = [
    "sync_market_data", "validate_data", "update_normalized", "update_features",
    "settle_predictions", "settle_analysis", "recompute_metrics", "update_leaderboard",
    "river_shadow", "training_due_check",
]


class SchedulerState:
    def __init__(self, data_root: Path | None = None) -> None:
        self.dir = (data_root or default_data_root()) / "manifests"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "scheduler.duckdb"

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_name VARCHAR PRIMARY KEY, last_success TIMESTAMP,
                    last_attempt TIMESTAMP, next_due TIMESTAMP, status VARCHAR,
                    error VARCHAR, retry_count BIGINT
                )
                """
            )

    def record_attempt(self, job: str) -> None:
        self.init()
        with self._conn() as con:
            con.execute(
                "INSERT INTO jobs (job_name, last_attempt, status, retry_count) VALUES (?,?, 'running', 0) "
                "ON CONFLICT (job_name) DO UPDATE SET last_attempt=excluded.last_attempt, status='running'",
                [job, datetime.now(timezone.utc)],
            )

    def record_success(self, job: str, next_due: datetime | None = None) -> None:
        self.init()
        now = datetime.now(timezone.utc)
        with self._conn() as con:
            con.execute(
                "UPDATE jobs SET last_success=?, status='ok', error=NULL, next_due=? WHERE job_name=?",
                [now, next_due or now, job],
            )

    def record_failure(self, job: str, error: str) -> None:
        self.init()
        with self._conn() as con:
            con.execute(
                "UPDATE jobs SET status='error', error=?, retry_count=retry_count+1 WHERE job_name=?",
                [error, job],
            )

    def status(self) -> dict[str, dict]:
        self.init()
        with self._conn() as con:
            rows = con.execute("SELECT * FROM jobs").df()
        return {r["job_name"]: r for r in rows.to_dict("records")}

    def last_success(self, job: str) -> datetime | None:
        s = self.status().get(job, {})
        return s.get("last_success")
