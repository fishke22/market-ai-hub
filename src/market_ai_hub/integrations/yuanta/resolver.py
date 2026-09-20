"""Phase 2Y-A — YuantaInstrumentResolver（只從 FunctionList/vendor docs 解析，不猜 ticker）。

禁止假設 TradingView ticker / JPX product code / SPARK StkCode 三者相同。
本棒只能從 FunctionList.xlsx 解析；不呼叫 SPARK。
"""
from __future__ import annotations

from market_ai_hub.integrations.yuanta.contracts import MARKET_TYPE, OSE_MARKET_TYPE, YuantaInstrument

# 本棒從 FunctionList.xlsx 股票代碼總表 實測確認的海外期貨 code（非猜測）
VERIFIED_FROM_FUNCTIONLIST = {
    # SGX (202) 日經相關
    "SGX_NIKKEI_225": YuantaInstrument(logical_instrument="SGX_NIKKEI_225", market_type=202,
                                       spark_code="NKN", display_name="日經225期貨(SGX)",
                                       source="FunctionList.xlsx", verified=True, verified_at="2026-09-19"),
    "SGX_NIKKEI_MINI": YuantaInstrument(logical_instrument="SGX_NIKKEI_MINI", market_type=202,
                                        spark_code="SNS", display_name="微型日經(SGX)",
                                        source="FunctionList.xlsx", verified=True, verified_at="2026-09-19"),
    # CME (203) 日經相關
    "CME_NIKKEI_MICRO": YuantaInstrument(logical_instrument="CME_NIKKEI_MICRO", market_type=203,
                                         spark_code="MNIK", display_name="微型日經(CME)",
                                         source="FunctionList.xlsx", verified=True, verified_at="2026-09-19"),
    "CME_NIKKEI_USD": YuantaInstrument(logical_instrument="CME_NIKKEI_USD", market_type=203,
                                       spark_code="NIY", display_name="日經225(CME USD)",
                                       source="FunctionList.xlsx", verified=True, verified_at="2026-09-19"),
    "CME_NIKKEI_JPY": YuantaInstrument(logical_instrument="CME_NIKKEI_JPY", market_type=203,
                                       spark_code="NK", display_name="日經225(CME JPY)",
                                       source="FunctionList.xlsx", verified=True, verified_at="2026-09-19"),
}

# OSE 日經期貨：FunctionList 股票代碼總表**未含** OSE (207) 期貨 code → 不得猜
OSE_UNVERIFIED_NOTE = ("OSE StkCode not present in FunctionList.xlsx stock table; "
                       "do NOT guess. Requires login + SubscribeWatchlist/market info "
                       "or a dedicated futures contract list.")


class YuantaInstrumentResolver:
    def resolve(self, logical_instrument: str) -> YuantaInstrument:
        if logical_instrument in VERIFIED_FROM_FUNCTIONLIST:
            return VERIFIED_FROM_FUNCTIONLIST[logical_instrument]
        if logical_instrument.startswith("OSE_"):
            # OSE 日經 Micro/Mini/Large 未在 FunctionList → UNVERIFIED，不猜
            return YuantaInstrument(
                logical_instrument=logical_instrument, market_type=OSE_MARKET_TYPE,
                spark_code="", display_name="", source="FunctionList.xlsx (NOT FOUND)",
                verified=False, verified_at="2026-09-19",
            )
        return YuantaInstrument(logical_instrument=logical_instrument, verified=False)

    def ose_market_type(self) -> int:
        return OSE_MARKET_TYPE

    def market_enum(self) -> dict:
        return dict(MARKET_TYPE)
