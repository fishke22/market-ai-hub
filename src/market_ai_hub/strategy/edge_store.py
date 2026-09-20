"""Phase 2F — HistoricalEdgeStore（D）：條件 Edge 統計。樣本不足 → INSUFFICIENT_EVIDENCE。"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from pydantic import BaseModel

from market_ai_hub.config.settings import project_root

MIN_SAMPLE_SIZE = 30


class HistoricalEdge(BaseModel):
    market: str
    instrument: str
    horizon: str
    conditions: dict[str, str]
    sample_size: int
    mean_forward_return: float | None = None
    median_forward_return: float | None = None
    positive_rate: float | None = None
    downside_quantile: float | None = None
    upside_quantile: float | None = None
    max_adverse_excursion: float | None = None
    max_favorable_excursion: float | None = None
    expected_value: float | None = None
    confidence_interval: list[float] | None = None
    status: str = "INSUFFICIENT_EVIDENCE"  # EDGE_FOUND / NO_EDGE / INSUFFICIENT_EVIDENCE


def _stats(r: pd.Series, min_sample: int = MIN_SAMPLE_SIZE) -> HistoricalEdge:
    r = r.dropna()
    n = int(len(r))
    if n < min_sample:
        return HistoricalEdge(market="", instrument="", horizon="", conditions={}, sample_size=n)
    arr = r.to_numpy(dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1))
    se = std / np.sqrt(n)
    lo = mean - 1.96 * se
    hi = mean + 1.96 * se
    edge_status = "EDGE_FOUND" if lo > 0 else ("NO_EDGE" if hi < 0 else "INSUFFICIENT_EVIDENCE")
    return HistoricalEdge(
        market="", instrument="", horizon="", conditions={}, sample_size=n,
        mean_forward_return=mean, median_forward_return=float(np.median(arr)),
        positive_rate=float((arr > 0).mean()),
        downside_quantile=float(np.quantile(arr, 0.05)),
        upside_quantile=float(np.quantile(arr, 0.95)),
        max_adverse_excursion=float(arr.min()),
        max_favorable_excursion=float(arr.max()),
        expected_value=mean,
        confidence_interval=[round(lo, 6), round(hi, 6)],
        status=edge_status,
    )


class HistoricalEdgeStore:
    """DuckDB edge store：record_edge / query。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or project_root()
        self.dir = self.root / "data" / "strategy"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "edges.duckdb"

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    market VARCHAR, instrument VARCHAR, horizon VARCHAR,
                    conditions VARCHAR, sample_size BIGINT, mean_forward_return DOUBLE,
                    median_forward_return DOUBLE, positive_rate DOUBLE, downside_quantile DOUBLE,
                    upside_quantile DOUBLE, max_adverse_excursion DOUBLE, max_favorable_excursion DOUBLE,
                    expected_value DOUBLE, confidence_interval VARCHAR, status VARCHAR
                )
                """
            )

    def record(self, e: HistoricalEdge) -> None:
        self.init()
        vals = [e.market, e.instrument, e.horizon, json.dumps(e.conditions, ensure_ascii=False),
                e.sample_size, e.mean_forward_return, e.median_forward_return, e.positive_rate,
                e.downside_quantile, e.upside_quantile, e.max_adverse_excursion,
                e.max_favorable_excursion, e.expected_value,
                json.dumps(e.confidence_interval) if e.confidence_interval else None, e.status]
        with self._conn() as con:
            con.execute(
                "INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals
            )

    def query(self, market: str | None = None, status: str | None = None) -> list[dict]:
        self.init()
        q = "SELECT * FROM edges"
        conds, params = [], []
        if market:
            conds.append("market=?"); params.append(market)
        if status:
            conds.append("status=?"); params.append(status)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY sample_size DESC"
        with self._conn() as con:
            df = con.execute(q, params).df()
        for r in df.to_dict("records"):
            r["conditions"] = json.loads(r["conditions"]) if r.get("conditions") else {}
            if r.get("confidence_interval"):
                r["confidence_interval"] = json.loads(r["confidence_interval"])
        return df.to_dict("records")


def compute_edge(returns: pd.Series, market: str = "", instrument: str = "",
                 horizon: str = "", conditions: dict | None = None,
                 min_sample: int = MIN_SAMPLE_SIZE) -> HistoricalEdge:
    e = _stats(returns, min_sample)
    e.market = market
    e.instrument = instrument
    e.horizon = horizon
    e.conditions = conditions or {}
    return e
