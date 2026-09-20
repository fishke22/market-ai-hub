"""Phase 2E — Analysis Archive（不可變分析）+ Outcome（append-only 結算）。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel, Field

from market_ai_hub.automation.data_lake import default_data_root


class AnalysisRecord(BaseModel):
    analysis_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    information_cutoff: datetime

    market: str = ""
    target: str = ""
    instrument: str = ""
    horizon: str = ""
    forecast_target_dates: list[str] = Field(default_factory=list)

    reference_price: float | None = None
    model_center: float | None = None
    research_center: float | None = None
    model_range: list[float] = Field(default_factory=list)
    research_core_range: list[float] = Field(default_factory=list)

    direction: str = ""
    research_confidence: float | None = None

    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    confirmation_levels: list[float] = Field(default_factory=list)
    invalidation_levels: list[float] = Field(default_factory=list)

    regime: str = ""
    event_state: str = ""

    top_positive_drivers: list[str] = Field(default_factory=list)
    top_negative_drivers: list[str] = Field(default_factory=list)

    forecast_ids: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    dataset_version: str = ""
    feature_version: str = ""

    analysis_packet_hash: str = ""
    human_readable_report_ref: str = ""

    def packet_hash(self) -> str:
        payload = json.dumps(self.model_dump(), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]


class AnalysisOutcome(BaseModel):
    analysis_id: str
    actual_close: float
    actual_high: float
    actual_low: float
    center_absolute_error: float
    direction_hit: bool
    core_range_hit: bool
    core_range_coverage: float | None = None
    support_broken: bool = False
    resistance_broken: bool = False
    invalidation_triggered: bool = False
    max_favorable_move: float | None = None
    max_adverse_move: float | None = None
    settled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalysisArchive:
    """不可變分析 + append-only 結算（DuckDB）。"""

    def __init__(self, data_root: Path | None = None) -> None:
        self.dir = (data_root or default_data_root()) / "analysis_archive"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "archive.duckdb"

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    analysis_id VARCHAR PRIMARY KEY, created_at TIMESTAMP, information_cutoff TIMESTAMP,
                    market VARCHAR, target VARCHAR, instrument VARCHAR, horizon VARCHAR,
                    forecast_target_dates VARCHAR, reference_price DOUBLE, model_center DOUBLE,
                    research_center DOUBLE, model_range VARCHAR, research_core_range VARCHAR,
                    direction VARCHAR, research_confidence DOUBLE, support_levels VARCHAR,
                    resistance_levels VARCHAR, confirmation_levels VARCHAR, invalidation_levels VARCHAR,
                    regime VARCHAR, event_state VARCHAR, top_positive_drivers VARCHAR,
                    top_negative_drivers VARCHAR, forecast_ids VARCHAR, model_versions VARCHAR,
                    dataset_version VARCHAR, feature_version VARCHAR, analysis_packet_hash VARCHAR,
                    human_readable_report_ref VARCHAR
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS outcomes (
                    analysis_id VARCHAR PRIMARY KEY, actual_close DOUBLE, actual_high DOUBLE,
                    actual_low DOUBLE, center_absolute_error DOUBLE, direction_hit BOOLEAN,
                    core_range_hit BOOLEAN, core_range_coverage DOUBLE, support_broken BOOLEAN,
                    resistance_broken BOOLEAN, invalidation_triggered BOOLEAN,
                    max_favorable_move DOUBLE, max_adverse_move DOUBLE, settled_at TIMESTAMP
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_links (
                    analysis_id VARCHAR, strategy_candidate_id VARCHAR,
                    strategy_status VARCHAR, historical_edge_summary VARCHAR, linked_at TIMESTAMP
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS reanalysis (
                    analysis_id VARCHAR, supersedes_analysis_id VARCHAR,
                    reason VARCHAR, linked_at TIMESTAMP
                )
                """
            )

    def save(self, rec: AnalysisRecord) -> None:
        """寫入分析（不可變）。重複 analysis_id → 拒絕。"""
        self.init()
        d = rec.model_dump()
        vals = []
        for k in (
            "analysis_id", "created_at", "information_cutoff", "market", "target", "instrument",
            "horizon", "forecast_target_dates", "reference_price", "model_center", "research_center",
            "model_range", "research_core_range", "direction", "research_confidence",
            "support_levels", "resistance_levels", "confirmation_levels", "invalidation_levels",
            "regime", "event_state", "top_positive_drivers", "top_negative_drivers", "forecast_ids",
            "model_versions", "dataset_version", "feature_version", "analysis_packet_hash",
            "human_readable_report_ref",
        ):
            v = d.get(k)
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False, default=str)
            vals.append(v)
        with self._conn() as con:
            if con.execute("SELECT 1 FROM analyses WHERE analysis_id=?", [rec.analysis_id]).fetchone():
                raise ValueError(f"analysis_id {rec.analysis_id} already archived (immutable)")
            con.execute(
                f"INSERT INTO analyses VALUES ({','.join(['?']*len(vals))})", vals
            )

    def settle(self, outcome: AnalysisOutcome) -> None:
        """append outcome（append-only）。"""
        self.init()
        with self._conn() as con:
            if not con.execute("SELECT 1 FROM analyses WHERE analysis_id=?", [outcome.analysis_id]).fetchone():
                raise ValueError(f"analysis_id {outcome.analysis_id} not found")
            if con.execute("SELECT 1 FROM outcomes WHERE analysis_id=?", [outcome.analysis_id]).fetchone():
                raise ValueError(f"analysis_id {outcome.analysis_id} already settled")
            d = outcome.model_dump()
            cols = list(d.keys())
            con.execute(
                f"INSERT INTO outcomes ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                [d[c] for c in cols],
            )

    def unsettled_ids(self) -> list[str]:
        self.init()
        with self._conn() as con:
            return [r[0] for r in con.execute(
                "SELECT a.analysis_id FROM analyses a LEFT JOIN outcomes o ON a.analysis_id=o.analysis_id "
                "WHERE o.analysis_id IS NULL ORDER BY a.created_at"
            ).fetchall()]

    def link_strategy(self, analysis_id: str, strategy_candidate_id: str,
                      strategy_status: str, historical_edge_summary: str = "") -> None:
        """以附加 relationship 儲存（不改動不可變 analysis）。"""
        self.init()
        with self._conn() as con:
            if not con.execute("SELECT 1 FROM analyses WHERE analysis_id=?", [analysis_id]).fetchone():
                raise ValueError(f"analysis_id {analysis_id} not found")
            con.execute(
                "INSERT INTO strategy_links VALUES (?,?,?,?,?)",
                [analysis_id, strategy_candidate_id, strategy_status,
                 historical_edge_summary, datetime.now(timezone.utc)],
            )

    def get_strategy_links(self, analysis_id: str | None = None) -> list[dict]:
        self.init()
        q = "SELECT * FROM strategy_links"
        params: list = []
        if analysis_id:
            q += " WHERE analysis_id=?"
            params.append(analysis_id)
        q += " ORDER BY linked_at"
        with self._conn() as con:
            return con.execute(q, params).df().to_dict("records")

    def record_reanalysis(self, analysis_id: str, supersedes_analysis_id: str,
                          reason: str = "FORECAST_STALE_AFTER_EVENT") -> None:
        """append reanalysis relationship（不覆蓋舊分析；supersedes 指向舊 analysis_id）。"""
        self.init()
        with self._conn() as con:
            con.execute(
                "INSERT INTO reanalysis VALUES (?,?,?,?)",
                [analysis_id, supersedes_analysis_id, reason, datetime.now(timezone.utc)],
            )

    def reanalysis_of(self, analysis_id: str) -> list[dict]:
        self.init()
        with self._conn() as con:
            return con.execute(
                "SELECT * FROM reanalysis WHERE supersedes_analysis_id=? ORDER BY linked_at",
                [analysis_id],
            ).df().to_dict("records")
