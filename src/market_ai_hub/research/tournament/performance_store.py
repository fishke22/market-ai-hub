"""Phase 2D — Model Performance Store（DuckDB）。

保存 model / revision / target / horizon / regime / evaluation_window / sample_size /
effective_sample_size + 價格/方向 metrics + runtime / peak_vram / failure_rate。
不得只保存 overall_accuracy。
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from market_ai_hub.config.settings import project_root

COLUMNS = [
    "exam_hash", "model", "revision", "target", "horizon", "regime",
    "evaluation_window_start", "evaluation_window_end",
    "sample_size", "effective_sample_size", "failure_rate",
    "mae", "rmse", "mase", "pinball_loss", "coverage", "interval_width", "calibration_error",
    "direction_accuracy", "balanced_accuracy", "macro_f1", "mcc",
    "runtime_seconds", "peak_vram_mb", "task",
]


class PerformanceStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or project_root()
        self.dir = self.root / "data" / "tournament"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "performance.duckdb"

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                f"""
                CREATE TABLE IF NOT EXISTS results (
                    exam_hash VARCHAR, model VARCHAR, revision VARCHAR, target VARCHAR, horizon VARCHAR,
                    regime VARCHAR, evaluation_window_start VARCHAR, evaluation_window_end VARCHAR,
                    sample_size BIGINT, effective_sample_size BIGINT, failure_rate DOUBLE,
                    mae DOUBLE, rmse DOUBLE, mase DOUBLE, pinball_loss DOUBLE,
                    coverage DOUBLE, interval_width DOUBLE, calibration_error DOUBLE,
                    direction_accuracy DOUBLE, balanced_accuracy DOUBLE, macro_f1 DOUBLE, mcc DOUBLE,
                    runtime_seconds DOUBLE, peak_vram_mb DOUBLE, task VARCHAR
                )
                """
            )

    def save(self, exam_hash: str, target: str, horizon: str, regime: str,
             window: tuple[str, str], revision: str, summary: dict) -> None:
        self.init()
        row = {
            "exam_hash": exam_hash, "target": target, "horizon": horizon, "regime": regime,
            "evaluation_window_start": window[0], "evaluation_window_end": window[1],
            "revision": revision,
            "model": summary.get("model"), "task": summary.get("task"),
            "sample_size": summary.get("sample_size"),
            "effective_sample_size": summary.get("effective_sample_size"),
            "failure_rate": summary.get("failure_rate"),
            "mae": summary.get("mae"), "rmse": summary.get("rmse"), "mase": summary.get("mase"),
            "pinball_loss": summary.get("pinball_loss"),
            "coverage": summary.get("coverage"), "interval_width": summary.get("interval_width"),
            "calibration_error": summary.get("calibration_error"),
            "direction_accuracy": summary.get("direction_accuracy"),
            "balanced_accuracy": summary.get("balanced_accuracy"),
            "macro_f1": summary.get("macro_f1"), "mcc": summary.get("mcc"),
            "runtime_seconds": summary.get("runtime_seconds"),
            "peak_vram_mb": summary.get("peak_vram_mb"),
        }
        with self._conn() as con:
            con.execute(
                f"INSERT INTO results ({','.join(COLUMNS)}) VALUES ({','.join(['?']*len(COLUMNS))})",
                [row.get(c) for c in COLUMNS],
            )

    def leaderboard(self, target: str | None = None, horizon: str | None = None) -> list[dict]:
        self.init()
        q = "SELECT * FROM results"
        conds, params = [], []
        if target:
            conds.append("target = ?"); params.append(target)
        if horizon:
            conds.append("horizon = ?"); params.append(horizon)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY target, horizon, mae"
        with self._conn() as con:
            return con.execute(q, params).df().to_dict("records")

    def inspect(self, model: str) -> list[dict]:
        self.init()
        with self._conn() as con:
            return con.execute("SELECT * FROM results WHERE model=? ORDER BY target, horizon", [model]).df().to_dict("records")
