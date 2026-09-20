"""Phase 2Y-E — COM smoke（connect + cleanup，不登入）。供 check 腳本呼叫。"""
from __future__ import annotations

from market_ai_hub.integrations.yuanta.futures_com import require_32bit, YuantaFuturesQuoteClient


def main() -> int:
    if not require_32bit():
        print("NOT_32BIT")
        return 1
    c = YuantaFuturesQuoteClient()
    try:
        c.connect()
        print("SMOKE_OK")
    finally:
        c.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
