"""Phase 2G — Unknown/known future covariate leakage guard（C）。

Unknown future（NQ/USDJPY/VIX/US10Y/SOX tomorrow 等）禁止使用「實際未來值」；
只能來自 joint model / scenario / persistence baseline / independent forecast。
Known future（calendar/weekday/holiday/FOMC/BOJ/CPI/NFP schedule/expiry）可直接用。
"""
from __future__ import annotations

# Known future：可直接使用（calendar 類）
KNOWN_FUTURE_FIELDS = {
    "calendar", "weekday", "holiday", "fomc_schedule", "boj_schedule",
    "cpi_scheduled_time", "nfp_scheduled_time", "expiry", "exchange_calendar",
}

# Unknown future：cross-asset「明日值」等，禁止實際未來值
UNKNOWN_FUTURE_FIELDS = {
    "NQ_tomorrow", "USDJPY_tomorrow", "VIX_tomorrow", "US10Y_tomorrow", "SOX_tomorrow",
}

# Unknown future 的合法來源
ALLOWED_UNKNOWN_SOURCES = {
    "JOINT_MODEL", "SCENARIO", "PERSISTENCE_BASELINE", "INDEPENDENT_FORECAST",
}

FORBIDDEN_SOURCE = "ACTUAL_FUTURE"


class FutureLeakageError(Exception):
    """unknown future covariate 使用了實際未來值。"""


def validate_covariate_source(field: str, source: str) -> None:
    """field 若為 unknown future，source 不得是 ACTUAL_FUTURE（也不得假裝真實值）。"""
    if field in UNKNOWN_FUTURE_FIELDS and source == FORBIDDEN_SOURCE:
        raise FutureLeakageError(
            f"unknown future covariate '{field}' cannot use {FORBIDDEN_SOURCE}"
        )


def assert_no_future_leak(covariates: dict[str, str]) -> None:
    """covariates: {field: source}。任一 unknown future 用 ACTUAL_FUTURE → raise。"""
    for field, source in covariates.items():
        validate_covariate_source(field, source)


def is_known_future(field: str) -> bool:
    return field in KNOWN_FUTURE_FIELDS
