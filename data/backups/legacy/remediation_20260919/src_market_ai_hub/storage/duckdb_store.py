"""DuckDB + Parquet 儲存層。raw 不覆寫，processed 可重建。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from market_ai_hub.schemas.market_data import Provenance

BAR_COLUMNS = [
    "timestamp_utc",
    "timestamp_local",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "provider",
    "data_grade",
    "retrieved_at",
]


def _project_root() -> Path:
    # src/market_ai_hub/storage/duckdb_store.py -> D:\MARKET_AI_HUB
    return Path(__file__).resolve().parents[3]


class MarketStore:
    """Append-only raw 儲存 + query。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _project_root()
        self.raw_dir = self.root / "data" / "raw"
        self.processed_dir = self.root / "data" / "processed"
        self.db_path = self.root / "data" / "market.duckdb"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def append_raw(self, provider: str, symbol: str, df: pd.DataFrame) -> Provenance:
        """把 provider 回傳的 df 落成 raw parquet（帶 content hash 檔名，不覆寫）。"""
        now = datetime.now(timezone.utc)
        requested_at = now
        received_at = now
        if df.empty:
            raise ValueError("empty dataframe")
        df = df.copy()
        df["retrieved_at"] = now
        payload = df.to_csv(index=False).encode("utf-8")
        checksum = hashlib.sha256(payload).hexdigest()[:16]
        fname = f"{provider}_{symbol}_{now:%Y%m%dT%H%M%S}_{checksum}.parquet"
        path = self.raw_dir / fname
        df.to_parquet(path, index=False)

        prov = Provenance(
            provider=provider,
            symbol=symbol,
            requested_at=requested_at,
            received_at=received_at,
            first_timestamp=pd.Timestamp(df["timestamp_utc"].min()).to_pydatetime(),
            last_timestamp=pd.Timestamp(df["timestamp_utc"].max()).to_pydatetime(),
            row_count=len(df),
            checksum=checksum,
            frequency=_guess_frequency(df),
        )
        prov_path = path.with_suffix(".provenance.json")
        prov_path.write_text(prov.model_dump_json(indent=2), encoding="utf-8")

        with self._conn() as con:
            con.execute(
                """
                INSERT INTO raw_provenance
                (provider, symbol, file, requested_at, received_at, first_ts, last_ts, row_count, checksum, frequency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    prov.provider, prov.symbol, fname, prov.requested_at, prov.received_at,
                    prov.first_timestamp, prov.last_timestamp, prov.row_count,
                    prov.checksum, prov.frequency,
                ],
            )
        return prov

    def init_schema(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_provenance (
                    provider VARCHAR, symbol VARCHAR, file VARCHAR,
                    requested_at TIMESTAMP, received_at TIMESTAMP,
                    first_ts TIMESTAMP, last_ts TIMESTAMP,
                    row_count BIGINT, checksum VARCHAR, frequency VARCHAR
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS bars (
                    timestamp_utc TIMESTAMP, timestamp_local TIMESTAMP, symbol VARCHAR,
                    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
                    provider VARCHAR, data_grade VARCHAR, retrieved_at TIMESTAMP
                )
                """
            )

    def rebuild_bars(self) -> None:
        """把 raw parquet 全部重讀，重建 bars table（processed 可重建）。"""
        self.init_schema()
        with self._conn() as con:
            con.execute("DELETE FROM bars")
        for p in sorted(self.raw_dir.glob("*.parquet")):
            df = pd.read_parquet(p)
            missing = [c for c in BAR_COLUMNS if c not in df.columns]
            if missing:
                continue
            df = df[BAR_COLUMNS]
            with self._conn() as con:
                con.execute("INSERT INTO bars SELECT * FROM df")

    def query_bars(self, symbol: str, start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame:
        with self._conn() as con:
            q = "SELECT * FROM bars WHERE symbol = ?"
            params: list = [symbol]
            if start is not None:
                q += " AND timestamp_utc >= ?"
                params.append(start)
            if end is not None:
                q += " AND timestamp_utc <= ?"
                params.append(end)
            q += " ORDER BY timestamp_utc"
            return con.execute(q, params).df()


def _guess_frequency(df: pd.DataFrame) -> str:
    ts = pd.to_datetime(df["timestamp_utc"])
    if len(ts) < 2:
        return "unknown"
    delta = ts.diff().dropna().median()
    seconds = delta.total_seconds()
    if seconds <= 3600:
        return "intraday"
    if seconds <= 86400 * 2:
        return "daily"
    return "coarse"
