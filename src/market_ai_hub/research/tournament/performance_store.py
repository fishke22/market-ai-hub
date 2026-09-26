"""Phase 2D — Model Performance Store（DuckDB）。

保存 model / revision / target / horizon / regime / evaluation_window / sample_size /
effective_sample_size + 價格/方向 metrics + runtime / peak_vram / failure_rate。
不得只保存 overall_accuracy。
"""
from __future__ import annotations

import math

import json
from pathlib import Path

import duckdb

from market_ai_hub.config.settings import project_root

ACCOUNTING_SCHEMA_VERSION = "C1.1"

COLUMNS = [
    "exam_hash", "model", "revision", "target", "horizon", "regime",
    "evaluation_window_start", "evaluation_window_end", "accounting_schema_version",
    "sample_size", "effective_sample_size", "failure_count", "abstention_count",
    "nonfinite_count", "invalid_target_count", "failure_rate", "coverage_rate",
    "mae", "rmse", "mase", "pinball_loss", "coverage", "interval_width", "calibration_error",
    "direction_accuracy", "balanced_accuracy", "macro_f1", "mcc",
    "runtime_seconds", "peak_vram_mb", "task",
]

PAIRWISE_COLUMNS = [
    "exam_hash", "target", "horizon", "regime", "evaluation_window_start",
    "evaluation_window_end", "model_a", "revision_a", "model_b", "revision_b", "task",
    "common_origin_count", "common_origin_coverage_rate", "model_a_coverage_rate",
    "model_b_coverage_rate", "metric", "model_a_metric_common", "model_b_metric_common",
    "delta_a_minus_b", "common_origin_indices_json",
]

# 單一 canonical boundary：這些欄位不得存放 NaN/±Inf
NUMERIC_METRIC_FIELDS = (
    "failure_rate", "coverage_rate", "mae", "rmse", "mase", "pinball_loss", "coverage",
    "interval_width", "calibration_error", "direction_accuracy", "balanced_accuracy",
    "macro_f1", "mcc", "runtime_seconds", "peak_vram_mb",
)
PAIRWISE_NUMERIC_FIELDS = (
    "common_origin_coverage_rate", "model_a_coverage_rate", "model_b_coverage_rate",
    "model_a_metric_common", "model_b_metric_common", "delta_a_minus_b",
)
ACCOUNTING_FIELDS = ("sample_size", "effective_sample_size", "failure_count",
                     "abstention_count", "nonfinite_count", "invalid_target_count")


class NonFiniteMetricError(ValueError):
    """NaN/±Inf 不得進 aggregate 或排名（typed reject，非 silent success）。"""


class AccountingMismatchError(ValueError):
    """attempted != valid + failed + abstained + nonfinite + invalid_target。"""


def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _reject_nonfinite(row: dict, fields, label: str) -> None:
    bad = sorted(f for f in fields if row.get(f) is not None and not _finite(row[f]))
    if bad:
        raise NonFiniteMetricError(f"BLOCKED_NONFINITE_METRIC({label}): {', '.join(bad)}")


def _reject_accounting_mismatch(summary: dict) -> None:
    missing = [f for f in ACCOUNTING_FIELDS if summary.get(f) is None]
    if missing:
        raise AccountingMismatchError(
            f"BLOCKED_ACCOUNTING_MISSING: {', '.join(missing)}")
    total = int(summary["sample_size"])
    parts = sum(int(summary[f]) for f in ACCOUNTING_FIELDS[1:])
    if parts != total:
        raise AccountingMismatchError(
            f"BLOCKED_ACCOUNTING_MISMATCH: sample_size={total} != effective+failed+"
            f"abstained+nonfinite+invalid_target={parts}")
    effective = int(summary["effective_sample_size"])
    rate = summary.get("coverage_rate")
    if rate is not None and total > 0 and abs(float(rate) - effective / total) > 1e-6:
        raise AccountingMismatchError(
            f"BLOCKED_ACCOUNTING_MISMATCH: coverage_rate={rate} != effective/sample="
            f"{effective / total:.6f}")


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
                    accounting_schema_version VARCHAR,
                    sample_size BIGINT, effective_sample_size BIGINT, failure_count BIGINT,
                    abstention_count BIGINT, nonfinite_count BIGINT, invalid_target_count BIGINT,
                    failure_rate DOUBLE, coverage_rate DOUBLE,
                    mae DOUBLE, rmse DOUBLE, mase DOUBLE, pinball_loss DOUBLE,
                    coverage DOUBLE, interval_width DOUBLE, calibration_error DOUBLE,
                    direction_accuracy DOUBLE, balanced_accuracy DOUBLE, macro_f1 DOUBLE, mcc DOUBLE,
                    runtime_seconds DOUBLE, peak_vram_mb DOUBLE, task VARCHAR
                )
                """
            )
            for name, dtype in (
                ("accounting_schema_version", "VARCHAR"), ("failure_count", "BIGINT"),
                ("abstention_count", "BIGINT"), ("nonfinite_count", "BIGINT"),
                ("invalid_target_count", "BIGINT"), ("coverage_rate", "DOUBLE"),
            ):
                con.execute(f"ALTER TABLE results ADD COLUMN IF NOT EXISTS {name} {dtype}")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS pairwise_results (
                    exam_hash VARCHAR, target VARCHAR, horizon VARCHAR, regime VARCHAR,
                    evaluation_window_start VARCHAR, evaluation_window_end VARCHAR,
                    model_a VARCHAR, revision_a VARCHAR, model_b VARCHAR, revision_b VARCHAR, task VARCHAR,
                    common_origin_count BIGINT, common_origin_coverage_rate DOUBLE,
                    model_a_coverage_rate DOUBLE, model_b_coverage_rate DOUBLE, metric VARCHAR,
                    model_a_metric_common DOUBLE, model_b_metric_common DOUBLE, delta_a_minus_b DOUBLE,
                    common_origin_indices_json VARCHAR
                )
                """
            )

    def save(self, exam_hash: str, target: str, horizon: str, regime: str,
             window: tuple[str, str], revision: str, summary: dict) -> None:
        self.init()
        row = {
            "exam_hash": exam_hash, "target": target, "horizon": horizon, "regime": regime,
            "evaluation_window_start": window[0], "evaluation_window_end": window[1],
            "revision": revision, "accounting_schema_version": ACCOUNTING_SCHEMA_VERSION,
            "model": summary.get("model"), "task": summary.get("task"),
            "sample_size": summary.get("sample_size"),
            "effective_sample_size": summary.get("effective_sample_size"),
            "failure_count": summary.get("failure_count"),
            "abstention_count": summary.get("abstention_count"),
            "nonfinite_count": summary.get("nonfinite_count"),
            "invalid_target_count": summary.get("invalid_target_count"),
            "failure_rate": summary.get("failure_rate"),
            "coverage_rate": summary.get("coverage_rate"),
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
        _reject_accounting_mismatch(row)
        _reject_nonfinite(row, NUMERIC_METRIC_FIELDS, "result")
        with self._conn() as con:
            con.execute(
                f"INSERT INTO results ({','.join(COLUMNS)}) VALUES ({','.join(['?']*len(COLUMNS))})",
                [row.get(c) for c in COLUMNS],
            )

    def leaderboard(self, target: str | None = None, horizon: str | None = None,
                    accounting_schema_version: str | None = ACCOUNTING_SCHEMA_VERSION) -> list[dict]:
        self.init()
        q = "SELECT * FROM results"
        conds, params = [], []
        if target:
            conds.append("target = ?"); params.append(target)
        if horizon:
            conds.append("horizon = ?"); params.append(horizon)
        if accounting_schema_version:
            conds.append("accounting_schema_version = ?"); params.append(accounting_schema_version)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY target, horizon, mae"
        with self._conn() as con:
            return con.execute(q, params).df().to_dict("records")

    def inspect(self, model: str) -> list[dict]:
        self.init()
        with self._conn() as con:
            return con.execute("SELECT * FROM results WHERE model=? ORDER BY target, horizon", [model]).df().to_dict("records")

    def save_pairwise(self, exam_hash: str, target: str, horizon: str, regime: str,
                      window: tuple[str, str], revisions: dict[str, str], comparison: dict) -> None:
        self.init()
        row = {
            **{k: comparison.get(k) for k in PAIRWISE_COLUMNS},
            "exam_hash": exam_hash, "target": target, "horizon": horizon, "regime": regime,
            "evaluation_window_start": window[0], "evaluation_window_end": window[1],
            "revision_a": revisions.get(comparison["model_a"], ""),
            "revision_b": revisions.get(comparison["model_b"], ""),
            "common_origin_indices_json": json.dumps(comparison.get("common_origin_indices", [])),
        }
        _reject_nonfinite(row, PAIRWISE_NUMERIC_FIELDS, "pairwise")
        with self._conn() as con:
            con.execute(
                f"INSERT INTO pairwise_results ({','.join(PAIRWISE_COLUMNS)}) "
                f"VALUES ({','.join(['?'] * len(PAIRWISE_COLUMNS))})",
                [row.get(c) for c in PAIRWISE_COLUMNS],
            )

    def pairwise(self, model_a: str | None = None, model_b: str | None = None,
                 target: str | None = None, horizon: str | None = None) -> list[dict]:
        self.init()
        q = "SELECT * FROM pairwise_results"
        conds, params = [], []
        if model_a and model_b:
            conds.append("((model_a=? AND model_b=?) OR (model_a=? AND model_b=?))")
            params.extend([model_a, model_b, model_b, model_a])
        if target:
            conds.append("target = ?"); params.append(target)
        if horizon:
            conds.append("horizon = ?"); params.append(horizon)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY target, horizon, model_a, model_b"
        with self._conn() as con:
            rows = con.execute(q, params).df().to_dict("records")
        for row in rows:
            row["common_origin_indices"] = json.loads(row.pop("common_origin_indices_json") or "[]")
        return rows
