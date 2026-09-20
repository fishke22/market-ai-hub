"""Phase 2Y-A — YuantaQuoteOnlyGateway（quote-only，架構上不存在 order method）。

此模組不得 import/wrap/expose/register 任何 SendOrder / SendFutureOrder /
Cancel / Modify / FutureOrder / StockOrder / conditional order / account trading。
不是「prompt 說不要下單」，而是程式架構上不存在 order method。
"""
from __future__ import annotations

from market_ai_hub.integrations.yuanta.contracts import YuantaRecorderContract


class YuantaQuoteOnlyGateway:
    """quote-only gateway skeleton。本棒不登入、不訂閱、不查帳、不下單。"""

    quote_only = True
    realtime_recorder_enabled = False
    recorder = YuantaRecorderContract()

    def __init__(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def capabilities(self) -> list[dict]:
        from market_ai_hub.integrations.yuanta.capabilities import capability_matrix

        return capability_matrix()

    def resolve(self, logical_instrument: str) -> dict:
        from market_ai_hub.integrations.yuanta.resolver import YuantaInstrumentResolver

        return YuantaInstrumentResolver().resolve(logical_instrument).model_dump()

    # 明確不存在的方法（架構層級）：
    #   login / subscribe / get_tick_detail / classify_price / get_quote_list
    #   → 本棒只做 skeleton，不實作連線（NO LOGIN）
    #   send_order / send_future_order / cancel / modify / account_query
    #   → 永不實作，不在 class 內
