"""Phase 2Y-A — Yuanta Capability Matrix skeleton（不因 API method 存在就標 SUPPORTED_BY_ACCOUNT）。"""
from __future__ import annotations

from market_ai_hub.integrations.yuanta.contracts import YuantaCapability

# 能力盤點（quote-only 關注的項目）。本棒只標 SUPPORTED_BY_API / UNKNOWN。
CAPABILITIES = [
    YuantaCapability(name="LOGIN", status="SUPPORTED_BY_API", note="Login Function ID 100000；未登入"),
    YuantaCapability(name="WATCHLIST", status="SUPPORTED_BY_API", note="SubscribeWatchlist*"),
    YuantaCapability(name="WATCHLIST_FIELDS", status="UNKNOWN", note="回傳欄位需 login 後確認"),
    YuantaCapability(name="FIVE_TICK", status="SUPPORTED_BY_API", note="SubscribeFiveTickA"),
    YuantaCapability(name="STOCK_TICK", status="SUPPORTED_BY_API", note="SubscribeStocktick"),
    YuantaCapability(name="GET_TICK_DETAIL", status="SUPPORTED_BY_API", note="GetStkTickDetail（當日 tick）"),
    YuantaCapability(name="CLASSIFY_PRICE", status="SUPPORTED_BY_API", note="GetStkClassifyPrice（當日分價量）"),
    YuantaCapability(name="QUOTE_LIST", status="SUPPORTED_BY_API", note="GetQuoteList Function ID 100001"),
    YuantaCapability(name="MARKET_INFO", status="SUPPORTED_BY_API", note="SubscribeMarketInformation"),
    # 2Y-B entitlement（未 login，故不標 SUPPORTED_BY_ACCOUNT）
    YuantaCapability(name="GET_WATCHLIST", status="SUPPORTED_BY_API_ONLY", note="未 login，entitlement 未知"),
    YuantaCapability(name="GET_KLINE", status="SUPPORTED_BY_API_ONLY", note="僅台股上市櫃（OSE_KLINE=NOT_SUPPORTED_BY_API_DOC）"),
]

# 只有真的收到有效 callback/result 才可標 SUPPORTED_BY_ACCOUNT
# 2Y-G.3: measured provider status (machine-readable). Login success != quote success.
# SPARK API supports securities + futures markets by official contract.
# 2026-09-24 PROD probe: securities profile MsgCode=0001 and matching live callbacks were measured
# on TAIFEX/OSE/CME/CBOT/CBOE/NYBOT. API_SUPPORT != FUTURES_ACCOUNT_ENTITLEMENT:
# the separate futures-account SPARK login still returns 0112. Names keep account_profile + market
# explicit; never reinterpret securities-profile quote success as futures-account login success.
PROVIDER_STATUS = {
    "legacy_futures_auth": "VERIFIED",                     # ReqType=1/2 measured Status=2 LogonOK code=0
    "legacy_domestic_quote": "LIVE_CALLBACK_VERIFIED",    # TX/MX/TMF/UNF T+1 measured OnGetMktData
    "spark_securities_taifex_quote": "LIVE_CALLBACK_VERIFIED",
    "spark_securities_ose_quote": "LIVE_CALLBACK_VERIFIED",
    "spark_securities_cme_quote": "LIVE_CALLBACK_VERIFIED",
    "spark_securities_cbot_quote": "LIVE_CALLBACK_VERIFIED",
    "spark_securities_cboe_quote": "LIVE_CALLBACK_VERIFIED",
    "spark_securities_nybot_quote": "LIVE_CALLBACK_VERIFIED",
    "spark_futures": "SPARK_FUTURES_ACCOUNT_ENTITLEMENT_BLOCKED",          # measured 0112 API_PERMISSION_UNAVAILABLE
    "ose_micro_live": "LIVE_CALLBACK_VERIFIED_SPARK_SECURITIES",
    "taifex_live": "LIVE_CALLBACK_VERIFIED_SPARK_AND_LEGACY",
}


ACCOUNT_VERIFIED_STATUS = {"SUPPORTED_BY_ACCOUNT", "NOT_ENTITLED", "NOT_RETURNED", "ERROR"}


def capability_matrix() -> list[dict]:
    return [c.model_dump() for c in CAPABILITIES]


def capability(name: str) -> YuantaCapability | None:
    for c in CAPABILITIES:
        if c.name == name:
            return c
    return None
