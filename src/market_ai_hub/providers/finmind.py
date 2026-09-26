"""FinMind provider（spec §10）。REST 版本；Cherry Studio 亦可直連 finmind-mcp（見 docs）。

token 從 env FINMIND_TOKEN 讀取，絕不 hardcode。
Free tier 預設；付費 dataset 回傳 DATA_REQUIRES_PAID_TIER，不付費。
"""
from __future__ import annotations

import logging
import threading

import httpx
import pandas as pd

from market_ai_hub.config.settings import get_secret
from market_ai_hub.providers.base import BaseProvider, ProviderError, ProviderInfo, ProviderStatus

log = logging.getLogger(__name__)
_HTTPX_LOG_LOCK = threading.Lock()

API = "https://api.finmindtrade.com/api/v4/data"


def _redact_secret(text: object, secret: str) -> str:
    out = str(text)
    return out.replace(secret, "<REDACTED_FINMIND_TOKEN>") if secret else out


def _safe_http_error(exc: Exception, dataset: str) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = getattr(getattr(exc, "response", None), "status_code", "UNKNOWN")
        return f"HTTP {status} for dataset={dataset}"
    if isinstance(exc, httpx.HTTPError):
        return f"{type(exc).__name__} for dataset={dataset}"
    return f"{type(exc).__name__} for dataset={dataset}"


def _get_without_sensitive_request_logging(*args, **kwargs):
    # httpx INFO request logs include the full URL, including query parameters.
    # FinMind authenticates with a token query parameter, so temporarily suppress
    # that logger while this request is in flight. The lock keeps level changes
    # deterministic for concurrent FinMind calls.
    httpx_log = logging.getLogger("httpx")
    with _HTTPX_LOG_LOCK:
        old_level = httpx_log.level
        if old_level == logging.NOTSET or old_level < logging.WARNING:
            httpx_log.setLevel(logging.WARNING)
        try:
            return httpx.get(*args, **kwargs)
        finally:
            httpx_log.setLevel(old_level)

# 常用 dataset tier 標註（詳細見 docs/reference/DATA_SOURCE_MATRIX.md）
DATASET_TIER: dict[str, str] = {
    "TaiwanStockPrice": "FREE",
    "TaiwanStockPriceAdj": "FREE",
    "TaiwanStockPER": "FREE",
    "TaiwanStockMonthRevenue": "FREE",
    "TaiwanStockFinancialStatements": "FREE",
    "TaiwanStockBalanceSheet": "FREE",
    "TaiwanStockCashFlowsStatement": "FREE",
    "TaiwanStockDividend": "FREE",
    "TaiwanStockDividendResult": "FREE",
    "TaiwanStockInstitutionalInvestorsBuySell": "FREE",
    "TaiwanStockMarginPurchaseShortSale": "FREE",
    "TaiwanStockSecuritiesLending": "FREE",
    "TaiwanStockDayTrading": "FREE",
    "TaiwanFuturesDaily": "FREE",
    "TaiwanOptionDaily": "FREE",
}


class FinMindProvider(BaseProvider):
    name = "finmind"

    def status(self) -> ProviderInfo:
        token = get_secret("FINMIND_TOKEN")
        if not token:
            return ProviderInfo(name=self.name, status=ProviderStatus.NEEDS_CONFIG, message="FINMIND_TOKEN not set")
        return ProviderInfo(name=self.name, status=ProviderStatus.OK)

    def fetch_dataset(
        self,
        dataset: str,
        data_id: str = "",
        start_date: str = "",
        end_date: str = "",
        timeout: float = 30.0,
    ) -> pd.DataFrame:
        token = get_secret("FINMIND_TOKEN")
        if not token:
            raise ProviderError("FINMIND_TOKEN not set")
        tier = DATASET_TIER.get(dataset, "UNKNOWN")
        params = {"dataset": dataset, "token": token}
        if data_id:
            params["data_id"] = data_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        try:
            resp = _get_without_sensitive_request_logging(API, params=params, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            safe = _safe_http_error(exc, dataset)
            log.error("finmind request failed: %s", safe)
            raise ProviderError(f"finmind request failed: {safe}") from exc

        if payload.get("msg") == "success":
            return pd.DataFrame(payload.get("data", []))
        msg = _redact_secret(payload.get("msg", ""), token)
        if "權限" in msg or "permission" in msg.lower() or "token" in msg.lower():
            raise ProviderError(f"DATA_REQUIRES_PAID_TIER for {dataset} (tier={tier}): {msg}")
        raise ProviderError(f"finmind error for {dataset}: {msg}")

    def fetch_price(self, symbol: str, start_date: str, end_date: str, adjusted: bool = True) -> pd.DataFrame:
        dataset = "TaiwanStockPriceAdj" if adjusted else "TaiwanStockPrice"
        df = self.fetch_dataset(dataset, symbol, start_date, end_date)
        if df.empty:
            raise ProviderError(f"finmind empty for {symbol}")
        local = pd.to_datetime(df["date"]).dt.tz_localize("Asia/Taipei", ambiguous="infer")
        out = pd.DataFrame(
            {
                "timestamp_utc": local.dt.tz_convert("UTC"),
                "timestamp_local": local,
                "open": df["open"].astype(float),
                "high": df["max"].astype(float),
                "low": df["min"].astype(float),
                "close": df["close"].astype(float),
                "volume": pd.to_numeric(df.get("Trading_Volume", 0), errors="coerce").fillna(0),
            }
        )
        return self.to_uniform_df(
            out, symbol, provider=self.name, data_grade="OFFICIAL_DAILY", local_tz="Asia/Taipei"
        )
