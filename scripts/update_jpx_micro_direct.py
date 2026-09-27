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
            "saved": str(path),
            "errors_before_success": errors,
        }
    return {"status": "NO_RECENT_SETTLEMENT", "errors": errors}


def refresh_public_archive(month_count: int = 3) -> dict:
    provider = JPXOSEDailyReportProvider()
    months = public_daily_report_months()
    selected = months[-max(int(month_count), 1):]
    return provider.sync_public_months(selected, skip_existing=True)


def run(month_count: int = 3, lookback_days: int = 10) -> dict:
    return {
        "schema": "JPX_MICRO_DIRECT_SYNC_V1",
        "settlement": refresh_current_settlement(lookback_days),
        "archive": refresh_public_archive(month_count),
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
