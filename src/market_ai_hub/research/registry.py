"""Phase 2A 儲存層：DuckDB（metadata/registry）+ Parquet（bulk records）。

- schema versioned（meta 表記錄 schema_version）
- non-destructive migration：只 CREATE IF NOT EXISTS；不 DROP 既有資料
- predictions 不可變（同 forecast_id 重複 insert → 拒絕）
- outcomes append-only（同 forecast_id 重複 settle → 拒絕）
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from market_ai_hub.config.settings import project_root
from market_ai_hub.research.schemas import OutcomeRecord, PredictionRecord

SCHEMA_VERSION = 1

PREDICTION_COLUMNS = [
    "forecast_id", "created_at", "information_cutoff",
    "market", "target", "instrument", "contract",
    "horizon", "forecast_origin", "forecast_target_dates", "exchange_calendar",
    "model_name", "model_task", "model_revision", "model_build_id", "training_cutoff",
    "input_data_hash", "dataset_version", "feature_version", "forecast_config_hash",
    "inference_seed", "sampling_config", "deterministic_mode",
    "point_forecast", "p10", "p50", "p90", "origin_price",
    "direction", "raw_class_scores", "probability_calibrated",
    "engineering_status", "predictive_validation_status",
    "regime_as_known_at_prediction_time", "data_quality_state", "raw_output_reference",
]

OUTCOME_COLUMNS = [
    "forecast_id", "actual", "actual_timestamp", "absolute_error", "squared_error",
    "scaled_error", "direction_result", "interval_hit", "pinball_loss", "settled_at",
]


class PredictionRegistry:
    """不可變預測 registry。DuckDB 為 metadata；Parquet 為 bulk export。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or project_root()
        self.registry_dir = self.root / "data" / "registry"
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.registry_dir / "registry.duckdb"

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key VARCHAR PRIMARY KEY, value VARCHAR
                )
                """
            )
            con.execute(
                "INSERT INTO schema_meta VALUES ('schema_version', ?) ON CONFLICT (key) DO NOTHING",
                [str(SCHEMA_VERSION)],
            )
            con.execute(
                f"""
                CREATE TABLE IF NOT EXISTS predictions (
                    forecast_id VARCHAR PRIMARY KEY,
                    created_at TIMESTAMP, information_cutoff TIMESTAMP,
                    market VARCHAR, target VARCHAR, instrument VARCHAR, contract VARCHAR,
                    horizon VARCHAR, forecast_origin TIMESTAMP, forecast_target_dates VARCHAR, exchange_calendar VARCHAR,
                    model_name VARCHAR, model_task VARCHAR, model_revision VARCHAR, model_build_id VARCHAR, training_cutoff TIMESTAMP,
                    input_data_hash VARCHAR, dataset_version VARCHAR, feature_version VARCHAR, forecast_config_hash VARCHAR,
                    inference_seed BIGINT, sampling_config VARCHAR, deterministic_mode BOOLEAN,
                    point_forecast DOUBLE, p10 DOUBLE, p50 DOUBLE, p90 DOUBLE, origin_price DOUBLE,
                    direction VARCHAR, raw_class_scores VARCHAR, probability_calibrated BOOLEAN,
                    engineering_status VARCHAR, predictive_validation_status VARCHAR,
                    regime_as_known_at_prediction_time VARCHAR, data_quality_state VARCHAR, raw_output_reference VARCHAR
                )
                """
            )
            con.execute(
                f"""
                CREATE TABLE IF NOT EXISTS outcomes (
                    forecast_id VARCHAR PRIMARY KEY,
                    actual DOUBLE, actual_timestamp TIMESTAMP, absolute_error DOUBLE, squared_error DOUBLE,
                    scaled_error DOUBLE, direction_result VARCHAR, interval_hit BOOLEAN, pinball_loss DOUBLE, settled_at TIMESTAMP
                )
                """
            )

    def schema_version(self) -> int:
        self.init()
        with self._conn() as con:
            r = con.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
            return int(r[0]) if r else SCHEMA_VERSION

    def register(self, rec: PredictionRecord) -> None:
        """寫入 forecast（不可變）。重複 forecast_id → 拒絕，不 overwrite。"""
        self.init()
        d = rec.model_dump()
        values = []
        for c in PREDICTION_COLUMNS:
            v = d.get(c)
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False, default=str)
            values.append(v)
        with self._conn() as con:
            existing = con.execute("SELECT 1 FROM predictions WHERE forecast_id=?", [rec.forecast_id]).fetchone()
            if existing:
                raise ValueError(f"forecast_id {rec.forecast_id} already registered (immutable)")
            con.execute(
                f"INSERT INTO predictions ({','.join(PREDICTION_COLUMNS)}) VALUES ({','.join(['?']*len(PREDICTION_COLUMNS))})",
                values,
            )

    def settle(self, outcome: OutcomeRecord) -> None:
        """append outcome（append-only）。重複 settle → 拒絕；forecast 不存在 → 拒絕。"""
        self.init()
        with self._conn() as con:
            f = con.execute("SELECT 1 FROM predictions WHERE forecast_id=?", [outcome.forecast_id]).fetchone()
            if not f:
                raise ValueError(f"forecast_id {outcome.forecast_id} not found")
            o = con.execute("SELECT 1 FROM outcomes WHERE forecast_id=?", [outcome.forecast_id]).fetchone()
            if o:
                raise ValueError(f"forecast_id {outcome.forecast_id} already settled (append-only)")
            d = outcome.model_dump()
            con.execute(
                f"INSERT INTO outcomes ({','.join(OUTCOME_COLUMNS)}) VALUES ({','.join(['?']*len(OUTCOME_COLUMNS))})",
                [d.get(c) for c in OUTCOME_COLUMNS],
            )

    def get(self, forecast_id: str) -> dict:
        self.init()
        with self._conn() as con:
            r = con.execute("SELECT * FROM predictions WHERE forecast_id=?", [forecast_id]).fetchone()
            if not r:
                raise KeyError(forecast_id)
            cols = [c[0] for c in con.description]
            return _decode(dict(zip(cols, r)))

    def is_settled(self, forecast_id: str) -> bool:
        self.init()
        with self._conn() as con:
            return con.execute("SELECT 1 FROM outcomes WHERE forecast_id=?", [forecast_id]).fetchone() is not None

    def list_predictions(self, model_name: str | None = None, settled: bool | None = None, limit: int = 100) -> list[dict]:
        self.init()
        q = "SELECT p.*, (o.forecast_id IS NOT NULL) AS settled FROM predictions p LEFT JOIN outcomes o ON p.forecast_id=o.forecast_id"
        conds, params = [], []
        if model_name:
            conds.append("p.model_name = ?")
            params.append(model_name)
        if settled is True:
            conds.append("o.forecast_id IS NOT NULL")
        elif settled is False:
            conds.append("o.forecast_id IS NULL")
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY p.created_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as con:
            df = con.execute(q, params).df()
        return [_decode(r) for r in df.to_dict("records")]

    def leaderboard(self, metric: str = "direction_result") -> list[dict]:
        """依 model 聚合已結算預測的簡易指標。"""
        self.init()
        with self._conn() as con:
            df = con.execute(
                """
                SELECT p.model_name,
                       COUNT(*) AS n,
                       AVG(o.absolute_error) AS mae,
                       SQRT(AVG(o.squared_error)) AS rmse,
                       AVG(CASE WHEN o.direction_result='correct' THEN 1.0 ELSE 0.0 END) AS direction_accuracy,
                       AVG(CASE WHEN o.interval_hit THEN 1.0 ELSE 0.0 END) AS interval_coverage,
                       AVG(o.pinball_loss) AS pinball
                FROM outcomes o JOIN predictions p ON p.forecast_id = o.forecast_id
                GROUP BY p.model_name
                ORDER BY n DESC
                """
            ).df()
        return df.to_dict("records")

    def forward_summary(self) -> dict:
        """Phase 2Q-A §14：統一 forward count 語義（單一來源，所有 packet 引用此函式）。"""
        preds = self.list_predictions(settled=None, limit=100000)
        model_tasks = {"PRICE_FORECAST", "DIRECTION_CLASSIFICATION"}

        def _is_model(p: dict) -> bool:
            return p.get("model_task") in model_tasks

        def _is_baseline(p: dict) -> bool:
            name = (p.get("model_name") or "").lower()
            return "baseline" in name or "naive" in name or "drift" in name

        settled = [p for p in preds if p.get("settled")]
        pending = [p for p in preds if not p.get("settled")]

        task_breakdown: dict = {}
        for p in preds:
            t = p.get("model_task") or "unknown"
            b = task_breakdown.setdefault(t, {"registered": 0, "settled": 0})
            b["registered"] += 1
            if p.get("settled"):
                b["settled"] += 1

        return {
            "registry_records_total": len(preds),
            "model_forecast_records": sum(1 for p in preds if _is_model(p)),
            "baseline_records": sum(1 for p in preds if _is_baseline(p)),
            "pending_records": len(pending),
            "settled_model_forecasts": sum(1 for p in settled if _is_model(p)),
            "settled_baselines": sum(1 for p in settled if _is_baseline(p)),
            "forward_evidence_n": sum(1 for p in settled if _is_model(p)),
            "task_breakdown": task_breakdown,
        }

    def export_parquet(self) -> tuple[Path, Path]:
        """把 predictions / outcomes 落成 bulk Parquet（schema versioned 檔名）。"""
        self.init()
        with self._conn() as con:
            pred = con.execute("SELECT * FROM predictions ORDER BY created_at").df()
            out = con.execute("SELECT * FROM outcomes ORDER BY settled_at").df()
        p_pred = self.registry_dir / f"predictions_v{SCHEMA_VERSION}.parquet"
        p_out = self.registry_dir / f"outcomes_v{SCHEMA_VERSION}.parquet"
        pred.to_parquet(p_pred, index=False)
        out.to_parquet(p_out, index=False)
        return p_pred, p_out


def _decode(rec: dict) -> dict:
    for k in ("forecast_target_dates", "sampling_config", "raw_class_scores"):
        if k in rec and isinstance(rec[k], str) and rec[k]:
            try:
                rec[k] = json.loads(rec[k])
            except json.JSONDecodeError:
                pass
    return rec
