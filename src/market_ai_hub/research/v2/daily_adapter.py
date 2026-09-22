"""V2-C — daily dataset adapters (read-only). 

Map actual local daily datasets to `DailyOutcomeBar` with HONEST roll_status / asof_status.

Dataset truth (from V2 AUDIT, verified on-disk):
- OSAKA_MICRO: data/normalized/ose_micro/ose_micro_daily_bar_v1.parquet → full OHLC, NO contract id / roll.
- TAIWAN_STOCK: data/cache/twse/*.json → Opening/Highest/Lowest/ClosingPrice (full OHLC), no roll.
- ^N225: feature store → close-only (NO OHLC) → Touch NOT possible.
- TAIWAN_INDEX / TAIEX: no local managed OHLC → NOT_AVAILABLE_LOCAL_DATASET.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dfield, asdict
from typing import Any

from market_ai_hub.research.v2.labels import DailyOutcomeBar

# local dataset field readiness (target/provider capability vs actual field readiness — separated)
FIELD_READINESS = {
    "OSAKA_MICRO": {"open": True, "high": True, "low": True, "close": True, "roll_provenance": False},
    "TAIWAN_STOCK": {"open": True, "high": True, "low": True, "close": True, "roll_provenance": "NOT_APPLICABLE"},
    "^N225": {"open": False, "high": False, "low": False, "close": True, "roll_provenance": "NOT_APPLICABLE"},
    "TAIWAN_INDEX": {"open": False, "high": False, "low": False, "close": False, "roll_provenance": "NOT_APPLICABLE"},
}


@dataclass
class DatasetReadiness:
    target_family: str = ""
    dataset_path: str = ""
    rows_inspected: int = 0
    date_range_start: str = ""
    date_range_end: str = ""
    fields: list[str] = dfield(default_factory=list)
    ohlc_ready: bool = False
    touch_ready: bool = False
    break_ready: bool = False
    acceptance_ready: bool = False
    roll_provenance: str = "UNKNOWN"
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    blocker: str = ""

    def model_dump(self) -> dict:
        return asdict(self)


def local_field_readiness(target_family: str) -> dict:
    """Return actual local dataset field readiness (NOT target theoretical capability)."""
    key = target_family.strip().upper()
    return FIELD_READINESS.get(key, {"open": False, "high": False, "low": False, "close": False,
                                     "roll_provenance": "UNKNOWN"})


def _is_futures(target_family: str, instrument_role: str) -> bool:
    return target_family.strip().upper() == "OSAKA_MICRO" and instrument_role == "DIRECT"


def osaka_micro_bars(path: str | None = None) -> tuple[list[DailyOutcomeBar], DatasetReadiness]:
    """Read-only: load OSE micro daily bars as DailyOutcomeBar.

    roll_status is set to UNKNOWN (the parquet has no contract id / roll column) → the V2-C engine
    will fail closed with BLOCKED_ROLL_PROVENANCE on multi-session futures labels. Honest.
    """
    import pandas as pd
    from market_ai_hub.config.runtime_paths import data_root
    p = path or str(data_root() / "normalized" / "ose_micro" / "ose_micro_daily_bar_v1.parquet")
    import os
    if not os.path.exists(p):
        return [], DatasetReadiness(target_family="OSAKA_MICRO", dataset_path=p,
                                    blocker="DATASET_NOT_FOUND")
    df = pd.read_parquet(p)
    bars: list[DailyOutcomeBar] = []
    for _, row in df.iterrows():
        bars.append(DailyOutcomeBar(
            instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT",
            calendar_id="OSE_DERIVATIVES", trading_date=str(row["trading_date"].date()),
            open=float(row["open"]) if pd.notna(row["open"]) else None,
            high=float(row["high"]) if pd.notna(row["high"]) else None,
            low=float(row["low"]) if pd.notna(row["low"]) else None,
            close=float(row["close"]) if pd.notna(row["close"]) else None,
            asof_status="LEGACY_TEMPORAL_UNVERIFIED",
            roll_status="UNKNOWN",  # no contract id / roll provenance
            series_semantics="CONTINUOUS",
        ))
    rd = DatasetReadiness(
        target_family="OSAKA_MICRO", dataset_path=p, rows_inspected=len(bars),
        date_range_start=bars[0].trading_date if bars else "",
        date_range_end=bars[-1].trading_date if bars else "",
        fields=list(df.columns), ohlc_ready=True, touch_ready=True, break_ready=True,
        acceptance_ready=True, roll_provenance="UNKNOWN",
        asof_status="LEGACY_TEMPORAL_UNVERIFIED",
        blocker="NO_ROLL_PROVENANCE (multi-session futures labels will block)",
    )
    return bars, rd
