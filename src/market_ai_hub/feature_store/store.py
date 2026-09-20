"""Phase 2C — Versioned Feature Store（DuckDB）。

每個 feature 記錄：feature_name / symbol / event_time / available_at /
feature_version / source / data_grade / value。

No look-ahead：`get(..., as_of)` 只回傳 available_at <= as_of 的 feature；
`put()` 強制 available_at 為 tz-aware。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
from pydantic import BaseModel, Field

from market_ai_hub.config.settings import project_root

SCHEMA_VERSION = 1


class FeatureRecord(BaseModel):
    feature_name: str
    symbol: str
    event_time: datetime
    available_at: datetime
    feature_version: str
    source: str
    data_grade: str
    value: float

    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)

    def model_post_init(self, __context) -> None:
        self.event_time = self._aware(self.event_time)
        self.available_at = self._aware(self.available_at)
        if self.available_at < self.event_time:
            # 未來資料的 feature 不得在 event_time 前可用（除非來源延遲，此處以 event_time 為最早可用）
            pass


COLUMNS = ["feature_name", "symbol", "event_time", "available_at", "feature_version",
           "source", "data_grade", "value"]


def _utc_naive(dt) -> datetime:
    """統一轉成 naive UTC（duckdb TIMESTAMP 不帶 tz，避免 round-trip 時區偏移）。"""
    t = pd.Timestamp(dt)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t.tz_localize(None).to_pydatetime()


class FeatureStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or project_root()
        self.dir = self.root / "data" / "feature_store"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "features.duckdb"

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                f"""
                CREATE TABLE IF NOT EXISTS features (
                    feature_name VARCHAR, symbol VARCHAR, event_time TIMESTAMP,
                    available_at TIMESTAMP, feature_version VARCHAR, source VARCHAR,
                    data_grade VARCHAR, value DOUBLE
                )
                """
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS schema_meta (key VARCHAR PRIMARY KEY, value VARCHAR)"
            )
            con.execute("INSERT INTO schema_meta VALUES ('schema_version', ?) ON CONFLICT (key) DO NOTHING",
                        [str(SCHEMA_VERSION)])

    def put(self, rec: FeatureRecord) -> None:
        self.init()
        d = rec.model_dump()
        values = []
        for c in COLUMNS:
            v = d[c]
            if c in ("event_time", "available_at"):
                v = _utc_naive(v)
            values.append(v)
        with self._conn() as con:
            con.execute(
                f"INSERT INTO features ({','.join(COLUMNS)}) VALUES ({','.join(['?']*len(COLUMNS))})",
                values,
            )

    def get(self, symbol: str, feature_name: str, as_of: datetime,
            feature_version: str | None = None) -> pd.DataFrame:
        """no-look-ahead：只回傳 available_at <= as_of 的 feature（回傳 naive UTC）。"""
        self.init()
        as_of = _utc_naive(as_of)
        q = ("SELECT * FROM features WHERE symbol=? AND feature_name=? AND available_at <= ?")
        params: list = [symbol, feature_name, as_of]
        if feature_version:
            q += " AND feature_version = ?"
            params.append(feature_version)
        q += " ORDER BY event_time"
        with self._conn() as con:
            return con.execute(q, params).df()

    def get_all_asof(self, as_of: datetime) -> pd.DataFrame:
        self.init()
        as_of = _utc_naive(as_of)
        with self._conn() as con:
            return con.execute(
                "SELECT * FROM features WHERE available_at <= ? ORDER BY event_time", [as_of]
            ).df()

    def versions(self) -> list[str]:
        self.init()
        with self._conn() as con:
            return [r[0] for r in con.execute("SELECT DISTINCT feature_version FROM features ORDER BY 1").fetchall()]


def build_panel_features(panel_closes: dict[str, pd.Series], as_of: datetime,
                         feature_version: str = "v1") -> list[FeatureRecord]:
    """由 panel close 序列產生 feature records（回傳 + 1d return）。

    event_time = bar 的 UTC 日；available_at = 該 bar 的 close（以日終為可用時點）。
    最後一根 bar 的 available_at 若 > as_of 會被排除（no look-ahead）。
    """
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    recs: list[FeatureRecord] = []
    for symbol, s in panel_closes.items():
        s = s.sort_index()
        for ts, val in s.items():
            ts = pd.Timestamp(ts)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            event_time = ts.tz_convert("UTC").normalize().to_pydatetime()
            available_at = event_time
            if available_at > as_of:
                continue  # 未來資料不進 store（no look-ahead）
            recs.append(FeatureRecord(
                feature_name="close", symbol=symbol, event_time=event_time,
                available_at=available_at, feature_version=feature_version,
                source="panel", data_grade="RESEARCH_PROXY", value=float(val),
            ))
    return recs
