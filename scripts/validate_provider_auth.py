"""Phase 2Q-F.6.1 — deep read-only provider auth validation（explicit）。

只做最小 read-only 請求；不得寫資料 / 交易 / broker / side effect。
AUTH_FAILED 時不把 token 放 exception/log。只在 explicit 執行時打 network。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _fred() -> str:
    import httpx

    from market_ai_hub.services.secret_store import get_secret

    key = get_secret("FRED_API_KEY")
    if not key:
        return "NOT_CONFIGURED"
    try:
        r = httpx.get("https://api.stlouisfed.org/fred/series",
                      params={"series_id": "GDP", "api_key": key, "file_type": "json"}, timeout=20.0)
        if r.status_code in (401, 403):
            return "AUTH_FAILED"
        r.raise_for_status()
        return "OK"
    except Exception:
        return "AUTH_FAILED"  # 不帶 token 進訊息


def _finmind() -> str:
    import httpx

    from market_ai_hub.services.secret_store import get_secret

    token = get_secret("FINMIND_API_TOKEN")
    if not token:
        return "NOT_CONFIGURED"
    try:
        r = httpx.get("https://api.finmindtrade.com/api/v4/data",
                      params={"dataset": "TaiwanStockInfo", "token": token}, timeout=20.0)
        if r.status_code in (401, 403):
            return "AUTH_FAILED"
        r.raise_for_status()
        return "OK"
    except Exception:
        return "AUTH_FAILED"


def main() -> int:
    print("FRED deep validation:", _fred())
    print("FinMind deep validation:", _finmind())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
