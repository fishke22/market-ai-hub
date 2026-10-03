"""Refresh public JPX/OSE Nikkei 225 Micro direct research data."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market_ai_hub.targets.jpx_daily import JPXOSEDailyReportProvider, public_daily_report_months
from market_ai_hub.targets.jpx_settlement import JPXSettlementProvider


def _recent_dates(days: int) -> list[str]:
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    return [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(max(days, 1))]


def refresh_current_settlement(lookback_days: int = 10) -> dict:
    provider = JPXSettlementProvider()
    errors = []
    for d in _recent_dates(lookback_days):
        try:
            rows = provider.fetch_parse(d)
        except Exception as exc:
            errors.append(f"{d}:{type(exc).__name__}")
            continue
        micro = [r for r in rows if r.product == "Nikkei 225 Micro Futures"]
        if not micro:
            continue
        path = provider.save(d, rows)
        return {
            "status": "OK",
            "trade_date": d,
            "micro_contracts": len(micro),
            "micro_months": sorted({r.contract for r in micro}),
            "saved": str(path),
            "errors_before_success": errors,
        }
    return {"status": "NO_RECENT_SETTLEMENT", "errors": errors}


def refresh_open_interest(lookback_days: int = 45) -> dict:
    """採集（或回填）JPX open_interest.xlsx 的 per-contract 成交量／建玉。

    W3.4 新高+放量假說的成交量來源；檔案已存在即略過，逐日容錯。
    """
    from market_ai_hub.targets.jpx_market_data import JPXMarketDataProvider
    provider = JPXMarketDataProvider()
    saved: list[str] = []
    errors: dict[str, str] = {}
    for d in _recent_dates(lookback_days):
        try:
            if provider.open_interest_path(d).exists():
                continue
            rows = provider.fetch_open_interest(d, product="Nikkei 225 Micro Futures")
            if not rows:
                continue
            provider.save_open_interest(d, rows)
            saved.append(d)
        except Exception as exc:
            errors[d] = type(exc).__name__
    return {"status": "OK" if not errors else "PARTIAL",
            "saved_dates": saved, "errors": errors}


def run_w34_breakout(months: list[str]) -> dict:
    """W3.4 前向假說循環（settle → trigger → precommit）。絕不寫 broker、絕不吃命令列值。"""
    from market_ai_hub.integrations.yuanta.resolver import select_target_contract_month
    from market_ai_hub.research.v2 import breakout_forward as BF
    from datetime import datetime as _dt
    if not months:
        return {"schema": BF.W34_SCHEMA_VERSION, "status": "SKIPPED",
                "reason": "NO_MICRO_MONTHS", "values_exposed": False}
    try:
        asof = _dt.now(ZoneInfo("Asia/Tokyo")).date()
        month, source = select_target_contract_month(sorted(set(months)), asof=asof)
        code = f"JNU{month[2:]}"
        result = BF.run_breakout_cycle(code)
    except Exception as exc:
        return {"schema": BF.W34_SCHEMA_VERSION, "status": "ERROR",
                "error_type": type(exc).__name__, "values_exposed": False}
    if isinstance(result, dict):
        result["contract_source"] = source
    return result


def refresh_public_archive(month_count: int = 3) -> dict:
    provider = JPXOSEDailyReportProvider()
    months = public_daily_report_months()
    selected = months[-max(int(month_count), 1):]
    return provider.sync_public_months(selected, skip_existing=True)


def run(month_count: int = 3, lookback_days: int = 10) -> dict:
    settlement = refresh_current_settlement(lookback_days)
    open_interest = refresh_open_interest()
    w34 = run_w34_breakout(settlement.get("micro_months", []))
    return {
        "schema": "JPX_MICRO_DIRECT_SYNC_V1",
        "settlement": settlement,
        "archive": refresh_public_archive(month_count),
        "open_interest": open_interest,
        "w34_breakout": w34,
        "broker_used": False,
        "credentials_used": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--settlement-lookback-days", type=int, default=10)
    args = ap.parse_args()
    result = run(args.months, args.settlement_lookback_days)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    settlement_ok = result["settlement"].get("status") == "OK"
    archive_ok = result["archive"].get("status") in {"OK", "PARTIAL"}
    return 0 if settlement_ok and archive_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
