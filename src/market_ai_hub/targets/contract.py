"""Phase 2G.1 — Target Instrument Contract（true execution target）。"""
from __future__ import annotations

import re

from pydantic import BaseModel

# 角色標記（不得混稱）
TARGET = "TARGET"
REFERENCE = "REFERENCE"
PROXY = "PROXY"

# 正式 execution target
EXECUTION_TARGET = "OSE_NIKKEI225_MICRO_FUTURES"

# 研究參考（分開）
REFERENCE_INSTRUMENTS = {
    "OSE_NIKKEI225_MICRO_FUTURES": TARGET,
    "OSE_NIKKEI225_MINI_FUTURES": REFERENCE,
    "OSE_NIKKEI225_LARGE_FUTURES": REFERENCE,
    "NIKKEI_SPOT": REFERENCE,      # underlying spot
    "SGX_NIKKEI": REFERENCE,
    "CME_NIKKEI": REFERENCE,
    "^N225": PROXY,                # yfinance research proxy，不是最終交易標的
}


_INSTRUMENT_ALIASES = {
    "JNU": EXECUTION_TARGET,
    "OSE_NIKKEI225_MICRO_FUTURES": EXECUTION_TARGET,
    "大阪微日經": EXECUTION_TARGET,
    "大阪微型日經": EXECUTION_TARGET,
    "大阪日經微型": EXECUTION_TARGET,
    "大阪日經225微型期貨": EXECUTION_TARGET,
    "日經225微型期貨": EXECUTION_TARGET,
    "NIKKEI225 MICRO": EXECUTION_TARGET,
    "NIKKEI 225 MICRO": EXECUTION_TARGET,
    "NIKKEI 225 MICRO FUTURES": EXECUTION_TARGET,
}


def normalize_instrument_alias(value: str) -> str:
    """Map common user-facing aliases/quote codes to the canonical execution target."""
    raw = str(value or "").strip()
    if not raw:
        return raw
    upper = raw.upper()
    if re.fullmatch(r"JNU(?:PM)?\d{4}", upper):
        return EXECUTION_TARGET
    if upper in _INSTRUMENT_ALIASES:
        return _INSTRUMENT_ALIASES[upper]
    if raw in _INSTRUMENT_ALIASES:
        return _INSTRUMENT_ALIASES[raw]
    compact = re.sub(r"\s+", " ", upper)
    return _INSTRUMENT_ALIASES.get(compact, raw)


def instrument_display_name(value: str) -> str:
    canonical = normalize_instrument_alias(value)
    if canonical == EXECUTION_TARGET:
        return "大阪日經225微型期貨（JNU）"
    return canonical


def role_of(instrument: str) -> str:
    """回傳 TARGET / REFERENCE / PROXY；未知 → PROXY（保守）。"""
    return REFERENCE_INSTRUMENTS.get(instrument, PROXY)


class TargetInstrumentContract(BaseModel):
    execution_target: str = EXECUTION_TARGET
    exchange: str = "OSE"
    contract_month: str = ""          # 動態（front month）
    quote_code: str = ""              # 動態（交易所 code）
    underlying: str = "NIKKEI225"
    tick_size: float = 5.0            # JPY（參考值）
    contract_multiplier: float = 10.0  # JPY/點（Micro=10x；Mini=100x；Large=1000x）
    session: str = "OSE daytime + night"
    currency: str = "JPY"


def is_execution_target(instrument: str) -> bool:
    return role_of(instrument) == TARGET
