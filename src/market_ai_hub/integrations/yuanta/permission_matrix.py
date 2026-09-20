"""Phase 2Y-G — YuantaPermissionMatrix（API 權限精確分類，USER vs SERVER 分開）。

USER_CONFIRMED_ENABLED ≠ SERVER_CONFIRMED。使用者說全開 + server 回無權限 → CONTRADICTION，
不得直接覆寫成「使用者沒申請」。
"""
from __future__ import annotations

from dataclasses import dataclass

USER_CONFIRMED_ENABLED = "USER_CONFIRMED_ENABLED"
SERVER_CONFIRMED = "SERVER_CONFIRMED"
SERVER_DENIED = "SERVER_DENIED"
NOT_TESTED = "NOT_TESTED"
UNKNOWN = "UNKNOWN"
CONTRADICTION = "CONTRADICTION"


@dataclass
class YuantaPermissionMatrix:
    def __init__(self) -> None:
        self.entries: dict[str, dict] = {
            "SPARK_SECURITIES": {"user": USER_CONFIRMED_ENABLED, "server": None, "state": SERVER_CONFIRMED,
                                 "note": "MsgCode=0001"},
            "SPARK_FUTURES": {"user": USER_CONFIRMED_ENABLED, "server": "0112", "state": CONTRADICTION,
                              "note": "user says enabled; server 0112"},
            "LEGACY_FUTURES_QUOTE_T": {"user": USER_CONFIRMED_ENABLED, "server": "Status=-2/Msg3",
                                       "state": "REQUIRES_SESSION_AWARE_RETEST",
                                       "note": "status=-2=LinkFail（非權限）；Msg[0]=3=無權限；需正常 T session 重測"},
            "LEGACY_FUTURES_QUOTE_TPLUS1": {"user": USER_CONFIRMED_ENABLED, "server": "Status=2", "state": SERVER_CONFIRMED,
                                            "note": "LogonOK"},
            "LEGACY_FUTURES_TRADING_T": {"user": UNKNOWN, "server": None, "state": NOT_TESTED,
                                         "note": "FUTURE_RESEARCH_ONLY"},
            "LEGACY_FUTURES_TRADING_TPLUS1": {"user": UNKNOWN, "server": None, "state": NOT_TESTED,
                                              "note": "FUTURE_RESEARCH_ONLY"},
            "OVERSEAS_FUTURES_MARKET_DATA": {"user": UNKNOWN, "server": None, "state": UNKNOWN,
                                             "note": "國外期貨行情可能另有訂閱"},
            "OSE_MARKET_DATA": {"user": UNKNOWN, "server": None, "state": UNKNOWN,
                                "note": "JNU public code verified; quote path 待定"},
        }

    def state(self, key: str) -> str:
        return self.entries.get(key, {}).get("state", UNKNOWN)

    def contradictions(self) -> list[str]:
        return [k for k, v in self.entries.items() if v["state"] == CONTRADICTION]

    def as_dict(self) -> dict:
        return dict(self.entries)
