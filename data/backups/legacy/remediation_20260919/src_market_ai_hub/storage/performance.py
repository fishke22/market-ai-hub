"""模型績效歷史儲存（spec §24 保存要求 + §23 performance-weighted 權重來源）。"""
from __future__ import annotations

from pathlib import Path

import duckdb

from market_ai_hub.config.settings import project_root
from market_ai_hub.schemas.backtest import BacktestRecord


class PerformanceStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or project_root()
        self.db_path = self.root / "data" / "performance.duckdb"

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS backtests (
                    model VARCHAR, model_version VARCHAR, data_version VARCHAR,
                    symbol VARCHAR, period VARCHAR, horizon VARCHAR, feature_set VARCHAR,
                    timestamp TIMESTAMP,
                    directional_accuracy DOUBLE, mae DOUBLE, rmse DOUBLE, pinball_loss DOUBLE,
                    brier_score DOUBLE,
                    hit_rate DOUBLE, average_return DOUBLE, expectancy DOUBLE,
                    profit_factor DOUBLE, max_drawdown DOUBLE, sharpe DOUBLE, sortino DOUBLE,
                    n_samples BIGINT
                )
                """
            )

    def save(self, rec: BacktestRecord) -> None:
        self.init()
        with self._conn() as con:
            con.execute(
                """INSERT INTO backtests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    rec.model, rec.model_version, rec.data_version, rec.symbol,
                    rec.period, rec.horizon, rec.feature_set, rec.timestamp,
                    rec.directional_accuracy, rec.mae, rec.rmse, rec.pinball_loss,
                    rec.brier_score, rec.hit_rate, rec.average_return, rec.expectancy,
                    rec.profit_factor, rec.max_drawdown, rec.sharpe, rec.sortino, rec.n_samples,
                ],
            )

    def latest_by_model(self) -> dict[str, dict]:
        """各 model 最近一次績效（ensemble weighting 用 directional_accuracy）。"""
        with self._conn() as con:
            df = con.execute(
                """
                SELECT model, directional_accuracy, timestamp FROM (
                    SELECT *, row_number() OVER (PARTITION BY model ORDER BY timestamp DESC) rn
                    FROM backtests
                ) WHERE rn = 1
                """
            ).df()
        return {r["model"]: {"directional_accuracy": r["directional_accuracy"], "timestamp": r["timestamp"]} for r in df.to_dict("records")}

    def list(self, model: str | None = None, limit: int = 20) -> list[dict]:
        with self._conn() as con:
            if model:
                df = con.execute(
                    "SELECT * FROM backtests WHERE model = ? ORDER BY timestamp DESC LIMIT ?", [model, limit]
                ).df()
            else:
                df = con.execute("SELECT * FROM backtests ORDER BY timestamp DESC LIMIT ?", [limit]).df()
        return df.to_dict("records")
