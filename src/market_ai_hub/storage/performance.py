"""模型績效歷史儲存（spec §24 + V1 remediation：additive v2 table）。

backtests v1 表格保留不動（非破壞性）；新記錄寫入 backtests_v2（擴充欄位）。
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from market_ai_hub.config.settings import project_root
from market_ai_hub.schemas.backtest import BacktestRecord

V2_COLUMNS = [
    "model", "model_version", "data_version", "symbol", "period", "horizon", "feature_set", "timestamp",
    "directional_accuracy", "mae", "rmse", "pinball_loss", "brier_score",
    "hit_rate", "average_return", "expectancy", "profit_factor", "max_drawdown", "sharpe", "sortino",
    "n_samples",
    "task_type", "classes", "flat_threshold", "accuracy", "balanced_accuracy", "macro_f1", "mcc", "mase",
    "class_distribution", "uniform_random_baseline_accuracy", "majority_class_baseline_accuracy",
    "baseline_threshold", "beats_majority_baseline",
    "engineering_status", "predictive_validation_status", "eligible_for_direction_vote",
    "baseline_results", "sample_size", "date_range",
]


class PerformanceStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or project_root()
        if root is not None:
            self.db_path = root / "db" / "performance.duckdb"
        else:
            from market_ai_hub.config.runtime_paths import resolve_db_path

            self.db_path = resolve_db_path("performance.duckdb")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS backtests_v2 (
                    model VARCHAR, model_version VARCHAR, data_version VARCHAR,
                    symbol VARCHAR, period VARCHAR, horizon VARCHAR, feature_set VARCHAR,
                    timestamp TIMESTAMP,
                    directional_accuracy DOUBLE, mae DOUBLE, rmse DOUBLE, pinball_loss DOUBLE,
                    brier_score DOUBLE,
                    hit_rate DOUBLE, average_return DOUBLE, expectancy DOUBLE,
                    profit_factor DOUBLE, max_drawdown DOUBLE, sharpe DOUBLE, sortino DOUBLE,
                    n_samples BIGINT,
                    task_type VARCHAR, classes VARCHAR, flat_threshold DOUBLE,
                    accuracy DOUBLE, balanced_accuracy DOUBLE, macro_f1 DOUBLE, mcc DOUBLE, mase DOUBLE,
                    class_distribution VARCHAR,
                    uniform_random_baseline_accuracy DOUBLE, majority_class_baseline_accuracy DOUBLE,
                    baseline_threshold DOUBLE, beats_majority_baseline BOOLEAN,
                    engineering_status VARCHAR, predictive_validation_status VARCHAR,
                    eligible_for_direction_vote BOOLEAN,
                    baseline_results VARCHAR, sample_size BIGINT, date_range VARCHAR
                )
                """
            )

    def save(self, rec: BacktestRecord) -> None:
        self.init()
        data = rec.model_dump()
        placeholders = ",".join(["?"] * len(V2_COLUMNS))
        values = []
        for c in V2_COLUMNS:
            v = data.get(c)
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False, default=str)
            values.append(v)
        with self._conn() as con:
            con.execute(f"INSERT INTO backtests_v2 VALUES ({placeholders})", values)

    def latest_by_model(self) -> dict[str, dict]:
        """各 model 最近一次 v2 績效（ensemble weighting / eligibility 用）。"""
        self.init()
        with self._conn() as con:
            df = con.execute(
                """
                SELECT * FROM (
                    SELECT *, row_number() OVER (PARTITION BY model ORDER BY timestamp DESC) rn
                    FROM backtests_v2
                ) WHERE rn = 1
                """
            ).df()
        out = {}
        for r in df.to_dict("records"):
            rec = dict(r)
            for k in ("class_distribution", "baseline_results", "date_range", "classes"):
                if rec.get(k) and isinstance(rec[k], str):
                    try:
                        rec[k] = json.loads(rec[k])
                    except json.JSONDecodeError:
                        pass
            out[rec["model"]] = rec
        return out

    def list(self, model: str | None = None, limit: int = 20) -> list[dict]:
        """v2 優先；v2 無資料時 fallback v1（欄位較少，缺欄以 None 呈現）。"""
        self.init()
        with self._conn() as con:
            df = con.execute(
                "SELECT * FROM backtests_v2 ORDER BY timestamp DESC LIMIT ?", [limit * 2]
            ).df() if model is None else con.execute(
                "SELECT * FROM backtests_v2 WHERE model = ? ORDER BY timestamp DESC LIMIT ?", [model, limit]
            ).df()
        rows = []
        for r in df.to_dict("records"):
            rec = dict(r)
            for k in ("class_distribution", "baseline_results", "date_range", "classes"):
                if rec.get(k) and isinstance(rec[k], str):
                    try:
                        rec[k] = json.loads(rec[k])
                    except json.JSONDecodeError:
                        pass
            rows.append(rec)
        if rows:
            return rows[:limit]
        # fallback：v1 舊表（僅 legacy 欄位）
        try:
            with self._conn() as con:
                if model is None:
                    df1 = con.execute("SELECT * FROM backtests ORDER BY timestamp DESC LIMIT ?", [limit]).df()
                else:
                    df1 = con.execute("SELECT * FROM backtests WHERE model = ? ORDER BY timestamp DESC LIMIT ?", [model, limit]).df()
            out = []
            for r in df1.to_dict("records"):
                rec = {c: (r.get(c) if c in r else None) for c in V2_COLUMNS}
                rec["schema_version"] = "v1_legacy"
                out.append(rec)
            return out
        except Exception:
            return []
