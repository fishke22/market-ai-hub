from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


def test_parquet_roundtrip_tz_aware(tmp_path: Path):
    ts = pd.date_range("2026-01-01", periods=5, freq="D", tz="UTC")
    df = pd.DataFrame({"ts": ts, "v": range(5)})
    p = tmp_path / "x.parquet"
    df.to_parquet(p)
    df2 = pq.read_table(p).to_pandas()
    assert df2["ts"].dt.tz is not None
    assert list(df2["v"]) == list(range(5))


def test_parquet_provenance_sidecar(tmp_path: Path):
    # storage 層的 provenance json 側車檔
    import json

    from market_ai_hub.schemas.market_data import Provenance

    now = datetime.now(timezone.utc)
    prov = Provenance(
        provider="test", symbol="A", requested_at=now, received_at=now,
        first_timestamp=now, last_timestamp=now, row_count=1,
        checksum="abc", frequency="daily",
    )
    side = tmp_path / "a.provenance.json"
    side.write_text(prov.model_dump_json(), encoding="utf-8")
    got = json.loads(side.read_text())
    assert got["provider"] == "test"
    assert got["frequency"] == "daily"
