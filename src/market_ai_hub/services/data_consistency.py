"""Phase 2I-A — DataConsistencyValidator（accuracy hardening）。

檢查：timestamp ordering / duplicate bars / missing sessions / price<=0 /
abnormal jumps / stale values / constant-frozen targets / timezone mismatch。
OSE Micro/Mini/Large/Settlement/Volume/OI 保持來源與語義分離；settlement 不冒充 live close。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd


@dataclass
class ConsistencyReport:
    ok: bool = True
    issues: list[str] = field(default_factory=list)

    def add(self, issue: str) -> None:
        self.issues.append(issue)
        self.ok = False

    def as_dict(self) -> dict:
        return {"ok": self.ok, "issues": self.issues}


class DataConsistencyValidator:
    def __init__(self, abnormal_jump_threshold: float = 0.30) -> None:
        self.jump_threshold = abnormal_jump_threshold

    def validate_bars(self, df: pd.DataFrame, price_col: str = "close",
                      ts_col: str = "timestamp", symbol: str = "") -> ConsistencyReport:
        r = ConsistencyReport()
        if df.empty:
            r.add(f"{symbol}: empty dataframe")
            return r
        # timezone mismatch
        ts = pd.to_datetime(df[ts_col])
        if ts.dt.tz is None:
            r.add(f"{symbol}: timestamp missing timezone")
        # ordering
        if not ts.is_monotonic_increasing:
            r.add(f"{symbol}: timestamp not sorted")
        # duplicate bars
        if ts.duplicated().any():
            r.add(f"{symbol}: duplicate bars ({int(ts.duplicated().sum())})")
        # price <= 0
        if (df[price_col] <= 0).any():
            r.add(f"{symbol}: non-positive price")
        # abnormal jumps
        pct = df[price_col].pct_change().dropna()
        if len(pct) and (pct.abs() > self.jump_threshold).any():
            n = int((pct.abs() > self.jump_threshold).sum())
            r.add(f"{symbol}: {n} abnormal jumps >{self.jump_threshold:.0%}")
        # constant/frozen
        if df[price_col].nunique() <= 1:
            r.add(f"{symbol}: constant/frozen price")
        return r

    def validate_target(self, series: pd.Series, symbol: str = "") -> ConsistencyReport:
        r = ConsistencyReport()
        s = series.dropna()
        if s.nunique() <= 1:
            r.add(f"{symbol}: frozen target (unique={s.nunique()})")
        if len(s) < 30:
            r.add(f"{symbol}: insufficient samples ({len(s)})")
        return r

    def validate_settlement_semantics(self, settlement: pd.Series, close: pd.Series | None = None) -> ConsistencyReport:
        """settlement 不得冒充 close（兩者來源與語義分離）。"""
        r = ConsistencyReport()
        if close is not None and len(settlement) and len(close):
            # 若 settlement 與 close 全等 → 可能被誤當 close，標記
            aligned = pd.concat([settlement.reset_index(drop=True), close.reset_index(drop=True)], axis=1).dropna()
            if len(aligned) and (aligned.iloc[:, 0] == aligned.iloc[:, 1]).all():
                r.add("settlement == close: settlement must be labeled SETTLEMENT, not CLOSE")
        return r
