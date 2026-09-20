"""Phase 2Y-B — Yuanta SPARK quote_probe CLI（read-only，NO ORDER）。

用法：
  python -m market_ai_hub.integrations.yuanta.quote_probe --profile futures --instrument OSE_NIKKEI225_MICRO_FUTURES

風險最低順序：GetWatchListAll → GetStkTickDetail(LastCount=20) → GetStkClassifyPrice(1 次)
→ 短暫 SubscribeWatchlist/FiveTick/StockTick（每項 ≤5s，之後立即 UnSubscribe）。
finally：unsubscribe + LogOut + Dispose。不建正式 Order Book、不做 Recorder。
"""
from __future__ import annotations

import argparse
import sys

from market_ai_hub.integrations.yuanta.spark_auth import AuthProbeConfig
from market_ai_hub.integrations.yuanta.sanitizer import mask_account, sanitize_login_result

MAX_TICK_DETAIL_COUNT = 20
MAX_STREAM_SECONDS = 5

PROBE_ORDER = ["GET_WATCHLIST", "GET_TICK_DETAIL", "CLASSIFY_PRICE",
               "SHORT_WATCHLIST_SUB", "SHORT_FIVETICK_SUB", "SHORT_STOCKTICK_SUB"]


def _instrument_resolved(instrument: str) -> bool:
    from market_ai_hub.integrations.yuanta.resolver import YuantaInstrumentResolver

    r = YuantaInstrumentResolver().resolve(instrument)
    return r.verified


def main() -> int:
    ap = argparse.ArgumentParser(prog="yuanta.quote_probe")
    ap.add_argument("--profile", choices=["futures"], default="futures")
    ap.add_argument("--instrument", default="OSE_NIKKEI225_MICRO_FUTURES")
    args = ap.parse_args()

    if not _instrument_resolved(args.instrument):
        print("OSE_MICRO_STKCODE_UNRESOLVED: run symbol discovery first "
              "(cannot guess StkCode).")
        return 1

    cfg = AuthProbeConfig()
    print("Profile:", cfg.profile, "| Mode:", cfg.mode, "| Orders:", cfg.orders)
    print("Instrument:", args.instrument)
    print("Probe order:", " -> ".join(PROBE_ORDER))
    print("TickDetail max count:", MAX_TICK_DETAIL_COUNT)
    print("Stream max seconds:", MAX_STREAM_SECONDS)
    print("NOTE: read-only capability probe; finally unsubscribe+LogOut+Dispose.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
