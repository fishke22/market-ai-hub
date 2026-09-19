"""Horizon 解析（V1 remediation：修復 horizon 參數失效）。

語義定案（以日線 bar 為基礎）：
  "Nd"  → N 根 trading bars（trading day）。1d=1, 2d=2, 5d=5, 10d=10。
  日內 horizon（5m/15m/30m/60m）在 data_frequency="1d" 下 → UNSUPPORTED_WITH_CURRENT_DATA。
  不把日線 interpolation 成假的日內 K。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_HORIZON_RE = re.compile(r"^(\d+)([a-z]+)$")

INTRADAY_HORIZONS = {"5m", "15m", "30m", "60m"}
SUPPORTED_HORIZONS = {"1d", "2d", "5d", "10d"}


class HorizonUnsupportedError(Exception):
    """資料頻率不支援該 horizon 時丟出；上層回 UNSUPPORTED_WITH_CURRENT_DATA。"""


@dataclass(frozen=True)
class HorizonSpec:
    requested_horizon: str
    unit: str
    effective_horizon_steps: int
    data_frequency: str
    supported: bool
    reason: str = ""

    @property
    def horizon_applied(self) -> bool:
        return self.supported


def parse_horizon(horizon: str, data_frequency: str = "1d") -> HorizonSpec:
    """把 "1d"/"2d"/"5d"/"10d" 解析成 trading bar 步數。

    data_frequency 目前只有 "1d"（日線）；未來接真分 K 資料時再擴充。
    """
    m = _HORIZON_RE.match((horizon or "").strip())
    if not m:
        return HorizonSpec(horizon, "", 0, data_frequency, False, f"malformed horizon '{horizon}'")
    n, unit = int(m.group(1)), m.group(2)

    if data_frequency == "1d":
        if unit == "d":
            if n <= 0:
                return HorizonSpec(horizon, unit, 0, data_frequency, False, "horizon must be positive")
            return HorizonSpec(horizon, unit, n, data_frequency, True)
        if unit in ("m", "h"):
            return HorizonSpec(
                horizon, unit, 0, data_frequency, False,
                f"UNSUPPORTED_WITH_CURRENT_DATA: intraday horizon '{horizon}' with daily data; "
                "不能把日線假造成分 K",
            )
        return HorizonSpec(horizon, unit, 0, data_frequency, False, f"unsupported unit '{unit}'")
    return HorizonSpec(
        horizon, unit, 0, data_frequency, False,
        f"UNSUPPORTED_WITH_CURRENT_DATA: data_frequency='{data_frequency}' not supported",
    )


def forecast_dates_from_series(last_ts, steps: int) -> list[str]:
    """從最後一根 bar 的時間戳產生 trading-day 日期（skip 週末）。"""
    import pandas as pd

    dates = pd.bdate_range(start=pd.Timestamp(last_ts).normalize(), periods=steps + 1)
    return [d.strftime("%Y-%m-%d") for d in dates[1:]]
