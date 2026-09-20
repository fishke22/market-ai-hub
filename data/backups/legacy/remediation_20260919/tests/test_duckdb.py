import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from market_ai_hub.storage.duckdb_store import MarketStore


def _sample_df(symbol="^N225", n=10):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ts = [base + timedelta(days=i) for i in range(n)]
    return pd.DataFrame(
        {
            "timestamp_utc": ts,
            "timestamp_local": ts,
            "symbol": symbol,
            "open": [100 + i for i in range(n)],
            "high": [101 + i for i in range(n)],
            "low": [99 + i for i in range(n)],
            "close": [100.5 + i for i in range(n)],
            "volume": [1000.0] * n,
            "provider": "test",
            "data_grade": "RESEARCH_PROXY",
            "retrieved_at": ts,
        }
    )


def test_append_and_rebuild(tmp_path: Path):
    store = MarketStore(root=tmp_path)
    store.init_schema()
    prov = store.append_raw("test", "^N225", _sample_df())
    assert prov.row_count == 10
    assert prov.checksum
    store.rebuild_bars()
    df = store.query_bars("^N225")
    assert len(df) == 10
    assert list(df.columns) == [
        "timestamp_utc", "timestamp_local", "symbol", "open", "high", "low",
        "close", "volume", "provider", "data_grade", "retrieved_at",
    ]


def test_append_is_append_only(tmp_path: Path):
    store = MarketStore(root=tmp_path)
    store.init_schema()
    store.append_raw("test", "A", _sample_df("A", 5))
    store.append_raw("test", "A", _sample_df("A", 5))
    parquets = list((tmp_path / "data" / "raw").glob("*.parquet"))
    assert len(parquets) == 2  # 不覆寫


def test_query_range(tmp_path: Path):
    store = MarketStore(root=tmp_path)
    store.init_schema()
    store.append_raw("test", "B", _sample_df("B", 20))
    store.rebuild_bars()
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    df = store.query_bars("B", start=start)
    assert len(df) == 16
