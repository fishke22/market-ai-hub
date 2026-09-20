"""TWSE OpenAPI provider（spec §9）。

host: openapi.twse.com.tw — OFFICIAL_HIGH_TRUST, FREE。
要求：HTTP timeout / retry / cache / schema validation / error logging。
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

from market_ai_hub.config.settings import project_root
from market_ai_hub.providers.base import BaseProvider, ProviderError, ProviderInfo, ProviderStatus

log = logging.getLogger(__name__)

BASE_URL = "https://openapi.twse.com.tw/v1"
CACHE_DIR = project_root() / "data" / "cache"


class TWSEProvider(BaseProvider):
    name = "twse"

    def __init__(self, timeout: float = 15.0, retries: int = 3) -> None:
        self._timeout = timeout
        self._retries = retries
        self._cache_dir = CACHE_DIR / self.name
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> ProviderInfo:
        try:
            self._get_json("/exchangeReport/STOCK_DAY_ALL", params={"response": "json", "date": "20260101"}, cache=False)
            return ProviderInfo(name=self.name, status=ProviderStatus.OK)
        except Exception as e:
            return ProviderInfo(name=self.name, status=ProviderStatus.UNAVAILABLE, message=str(e))

    def status_shallow(self) -> ProviderInfo:
        """TWSE 為 public API 無 key；shallow 只回 configured（不做 live network probe，避免 health 卡住）。"""
        return ProviderInfo(name=self.name, status=ProviderStatus.OK)

    def _get_json(self, path: str, params: dict, cache: bool = True) -> list[dict] | dict:
        url = BASE_URL + path
        cache_key = hashlib.sha256((url + str(sorted(params.items()))).encode()).hexdigest()[:16]
        cache_file = self._cache_dir / f"{cache_key}.json"
        if cache and cache_file.exists():
            return _load_json(cache_file)
        for attempt in range(1, self._retries + 1):
            try:
                resp = httpx.get(url, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()
                if cache:
                    import json

                    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data
            except Exception as e:
                log.warning("twse %s attempt %d failed: %s", path, attempt, e)
                if attempt == self._retries:
                    raise ProviderError(f"twse {path} failed after {self._retries} retries: {e}") from e
                time.sleep(1.0 * attempt)
        raise ProviderError("unreachable")

    def fetch_stock_day_all(self, date_str: str = "") -> pd.DataFrame:
        """某日全市場日線（TWSE 上市）。date 格式 YYYYMMDD。"""
        if not date_str:
            date_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        data = self._get_json(
            "/exchangeReport/STOCK_DAY_ALL",
            params={"response": "json", "date": date_str},
        )
        if not isinstance(data, list):
            raise ProviderError(f"unexpected twse payload for {date_str}")
        df = _validate_day_all(data)
        if df.empty:
            raise ProviderError(f"twse STOCK_DAY_ALL empty for {date_str}")
        return df

    def fetch_symbol_daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """symbol 日線（用 TWSE 官方單股 `STOCK_DAY` endpoint，逐月拉取）。

        start/end 為西元 YYYYMMDD。STOCK_DAY 以 R.O.C. 月為單位回傳該月每日 OHLC。
        注意：不能用 STOCK_DAY_ALL 逐日迭代（該 endpoint 對歷史日期只回最新一日，
        會製造重複序列）；此為資料層修正。
        """
        from datetime import datetime as _dt, timedelta as _td

        s = _dt.strptime(start, "%Y%m%d")
        e = _dt.strptime(end, "%Y%m%d")
        frames: list[dict] = []
        cursor = s.replace(day=1)
        while cursor <= e:
            # TWSE STOCK_DAY 的 date 參數是西元年月（YYYYMM01），不是民國年；
            # 回應的 data[0] 才是民國年（113/01/02 → +1911）。
            roc_month = f"{cursor.year:04d}{cursor.month:02d}01"
            try:
                payload = self._get_stock_day_json(symbol, roc_month)
            except ProviderError:
                cursor = _next_month(cursor)
                continue
            if payload.get("stat") != "OK" or not payload.get("data"):
                cursor = _next_month(cursor)
                continue
            for r in payload["data"]:
                try:
                    y, m, d = str(r[0]).split("/")
                    iso = f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"
                    o, h, l, c = _num(r[3]), _num(r[4]), _num(r[5]), _num(r[6])
                    v = _num(r[1])
                except Exception:
                    continue
                if c is None:
                    continue
                frames.append({"Date": iso, "Open": o, "High": h, "Low": l, "Close": c, "TradeVolume": v})
            cursor = _next_month(cursor)

        if not frames:
            raise ProviderError(f"no twse data for {symbol} {start}..{end}")
        df = pd.DataFrame(frames).drop_duplicates(subset=["Date"]).sort_values("Date")
        lo = s.strftime("%Y-%m-%d")
        hi = e.strftime("%Y-%m-%d")
        df = df[(df["Date"] >= lo) & (df["Date"] <= hi)].reset_index(drop=True)
        if df.empty:
            raise ProviderError(f"no twse data for {symbol} {start}..{end}")
        return self._to_uniform(df, symbol)

    def _get_stock_day_json(self, symbol: str, roc_month: str) -> dict:
        url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
        params = {"response": "json", "date": roc_month, "stockNo": symbol}
        resp = httpx.get(url, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def _to_uniform(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        local = pd.to_datetime(df["Date"]).dt.tz_localize("Asia/Taipei", ambiguous="infer")
        out = pd.DataFrame(
            {
                "timestamp_utc": local.dt.tz_convert("UTC"),
                "timestamp_local": local,
                "open": df["Open"].astype(float),
                "high": df["High"].astype(float),
                "low": df["Low"].astype(float),
                "close": df["Close"].astype(float),
                "volume": pd.to_numeric(df.get("TradeVolume", 0), errors="coerce").fillna(0),
            }
        )
        return self.to_uniform_df(out, symbol, provider=self.name, data_grade="OFFICIAL_DAILY", local_tz="Asia/Taipei")


def _validate_day_all(data: list[dict]) -> pd.DataFrame:
    """schema validation：確保必要欄位存在且型別可轉。"""
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    required = {"Code", "Name", "TradeVolume", "TradeValue", "OpeningPrice", "HighestPrice", "LowestPrice", "ClosingPrice"}
    missing = required - set(df.columns)
    if missing:
        raise ProviderError(f"twse schema missing columns: {missing}")
    df = df.rename(
        columns={
            "OpeningPrice": "Open",
            "HighestPrice": "High",
            "LowestPrice": "Low",
            "ClosingPrice": "Close",
        }
    )
    for c in ("Open", "High", "Low", "Close", "TradeVolume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "Close"])
    if "Date" not in df.columns:
        raise ProviderError("twse schema missing Date")
    return df


def _load_json(path: Path) -> list[dict] | dict:
    import json

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _next_month(d):
    """回傳下一個月的 1 號。"""
    from datetime import timedelta

    if d.month == 12:
        return d.replace(year=d.year + 1, month=1, day=1)
    return d.replace(month=d.month + 1, day=1)


def _num(x):
    """把 TWSE 字串數字轉 float；"--" / 空 → None。"""
    if x is None:
        return None
    s = str(x).replace(",", "").strip()
    if s in ("", "--", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None
