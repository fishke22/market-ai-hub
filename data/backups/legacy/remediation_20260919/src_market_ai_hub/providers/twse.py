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
        """symbol 日線（by iterating STOCK_DAY_ALL；免費端無單股歷史 endpoint 時的正確做法）。

        start/end 為西元 YYYYMMDD；STOCK_DAY_ALL 的 date 參數用民國年（民國 = 西元 - 1911）。
        """
        d = datetime.strptime(start, "%Y%m%d")
        e = datetime.strptime(end, "%Y%m%d")
        frames = []
        while d <= e:
            roc_day = f"{d.year - 1911:04d}{d:%m%d}"
            try:
                all_df = self.fetch_stock_day_all(roc_day)
            except ProviderError:
                d += timedelta(days=1)
                continue
            row = all_df[all_df["Code"] == symbol]
            if not row.empty:
                row = row.copy()
                row["Date"] = d.strftime("%Y%m%d")
                frames.append(row)
            d += timedelta(days=1)
        if not frames:
            raise ProviderError(f"no twse data for {symbol} {start}..{end}")
        df = pd.concat(frames).sort_values("Date").reset_index(drop=True)
        return self._to_uniform(df, symbol)

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
