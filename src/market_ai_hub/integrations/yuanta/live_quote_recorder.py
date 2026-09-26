"""Persistent quote-only Yuanta SPARK recorder.

One process owns one SPARK login for its whole lifetime. Agents never receive
credentials; they read latest/status files or submit quote-only subscription
requests. No order/account/position/balance API is exposed here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
import re
import time
import math
import threading
from collections import deque
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

import yaml

from market_ai_hub.config.runtime_paths import data_root
from market_ai_hub.config.settings import project_root
from market_ai_hub.integrations.yuanta.credential_store import (
    read_profile_credential, read_profile_password,
)
from market_ai_hub.integrations.yuanta.function_list import load_stock_code_rows
from market_ai_hub.integrations.yuanta.resolver import function_list_path
from market_ai_hub.integrations.yuanta.spark_runtime import SparkRuntime
from market_ai_hub.integrations.yuanta.reconnect_lifecycle import (
    ReconnectLifecycleError,
    ReconnectPolicy,
    recover_quote_runtime,
)
from market_ai_hub.integrations.yuanta.durable_spool import (
    DurableQuoteSpool, DurableSpoolError, canonical_bytes,
    durable_json_replace, durable_replace, sha256_hex,
)

CONFIG_PATH = project_root() / "config" / "yuanta_live_recorder.yaml"
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9_./-]{1,40}$")
_JNU_CONTRACT_RE = re.compile(r"^JNU\d{4}$")
_DURABLE_BATCH_RE = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
_QUOTE_FIELDS = (
    "YstPrice", "OpenRefPrice", "UpStopPrice", "DownStopPrice", "YstVol",
    "OpenPrice", "HighPrice", "LowPrice", "BuyPrice", "SellPrice", "DealPrice",
    "TotalOutVol", "TotalInVol", "TotalDealAmt", "VolFlag", "Vol", "TotalVol",
    "FixedPriceVol", "ReserveVol", "SettlementPrice", "HiContractPrice",
    "LoContractPrice", "OrderBuyCount", "OrderBuyQty", "OrderSellCount",
    "OrderSellQty", "DealBuyCount", "DealSellCount", "Volatility", "TimeDiff",
    "PrincipalPercent", "UpDownDay", "BidQty", "AskQty", "PriceTrends",
    "EstDealPrice", "EstDealVol", "EstDealVolFlag",
    "SerialNo", "DealVol", "InOutFlag", "Type",
)


_MARKET_TIMEZONES = {
    1: "Asia/Taipei",   # TWSE
    2: "Asia/Taipei",   # TWOTC
    3: "Asia/Taipei",   # TAIFEX
    202: "Asia/Singapore",
    203: "America/Chicago",  # CME
    204: "America/Chicago",  # CBOT
    205: "Asia/Tokyo",       # TCE/TOCOM
    207: "Asia/Tokyo",       # OSE
    208: "Asia/Hong_Kong",
    209: "America/New_York", # NYBOT/ICE-US
    210: "Europe/London",
    211: "Europe/Berlin",
    212: "Australia/Sydney",
    215: "America/New_York", # CBOE
}
_DEFAULT_SUBSCRIPTION_REVALIDATION_SECONDS = 300.0


def _market_local_date(market: int, asof: date | datetime) -> date:
    """Resolve a venue-local calendar date; never use UTC date as trading-date proxy."""
    if isinstance(asof, datetime):
        if asof.tzinfo is None:
            raise ValueError("subscription asof datetime must be timezone-aware")
        timezone_name = _MARKET_TIMEZONES.get(int(market))
        if timezone_name is None:
            raise ValueError(f"unknown market timezone: {market}")
        return asof.astimezone(ZoneInfo(timezone_name)).date()
    return asof


def _subscription_revalidation_due(last_attempt: float, now: float, interval_seconds: float) -> bool:
    return now - last_attempt >= max(1.0, float(interval_seconds))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _current_build_id() -> str:
    """Build id frozen by the imported runtime process."""
    from market_ai_hub.services.build_info import build_fingerprint
    return str(build_fingerprint()["build_id"])


def _disk_build_id() -> str:
    """Recompute the current source/config fingerprint from disk."""
    from market_ai_hub.services.build_info import _compute_build_id
    return str(_compute_build_id())


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def recorder_root(config_path: Path = CONFIG_PATH) -> Path:
    cfg = _load_config(config_path)
    return _within(data_root(), str(cfg.get("storage", {}).get("root", "live/yuanta")))


def _within(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError("path must stay within recorder root")
    return path


@contextmanager
def _single_instance(root: Path):
    # Windows mutex is independent of DATA_ROOT: only one SPARK owner per session.
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateMutexW(None, False, "Local\\MARKET_AI_HUB_SPARK_QUOTE_OWNER")
        exists = ctypes.get_last_error() == 183
        if not handle or exists:
            if handle:
                kernel.CloseHandle(handle)
            raise RuntimeError("YUANTA_LIVE_ALREADY_RUNNING")
        try:
            yield
        finally:
            kernel.CloseHandle(handle)
    else:
        import fcntl
        with (root / ".recorder.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


class QuoteBuffer:
    """Bounded handoff; optional durable spool is the pending-record source of truth."""

    def __init__(self, capacity: int, spool: DurableQuoteSpool | None = None):
        if capacity < 1:
            raise ValueError("buffer capacity must be positive")
        self.capacity = capacity
        self.spool = spool
        self.records = deque()
        self.lock = threading.Lock()
        self.dropped = 0
        self.latest = {}
        self.spool_error: str | None = None
        if self.spool is not None:
            for record in self.spool.peek(self.spool.max_records):
                self._merge_latest(record.payload)

    def _merge_latest(self, payload: dict) -> None:
        key = f"{payload['market_no']}:{payload['instrument_code']}"
        self.latest[key] = _merge_quote(self.latest.get(key, {}), payload)

    def append(self, payload: dict) -> bool:
        if self.spool is not None:
            try:
                self.spool.append(payload)
            except (DurableSpoolError, OSError, ValueError) as exc:
                with self.lock:
                    self.dropped += 1
                    self.spool_error = type(exc).__name__
                return False
            with self.lock:
                self._merge_latest(payload)
            return True
        with self.lock:
            self._merge_latest(payload)
            if len(self.records) >= self.capacity:
                self.dropped += 1
                return False
            self.records.append(payload)
            return True

    def snapshot(self):
        with self.lock:
            latest = dict(self.latest)
            dropped = self.dropped
        if self.spool is not None:
            return latest, self.spool.stats()["pending_records"], dropped
        with self.lock:
            return latest, len(self.records), dropped

    def durability_status(self) -> dict:
        if self.spool is None:
            return {"mode": "BUFFERED_NOT_ZERO_LOSS", "spool_error": None}
        return {
            "mode": "DURABLE_SPOOL_FSYNC_BEFORE_ACCEPT",
            "spool_error": self.spool_error,
            **self.spool.stats(),
        }

    def flush(self, root: Path, batch_size: int = 100000) -> str | None:
        if self.spool is not None:
            batch = self.spool.peek(batch_size)
            if not batch:
                return None
            batch_id = self.spool.batch_id(batch)
            rows = [
                {**item.payload, "_wal_seq": item.seq, "_wal_record_sha256": item.payload_sha256}
                for item in batch
            ]
            result = _write_parquet(root, rows, batch_id=batch_id)
            try:
                self.spool.ack_through(batch[-1].seq, batch_id=batch_id)
            except (DurableSpoolError, OSError) as exc:
                with self.lock:
                    self.spool_error = type(exc).__name__
                raise
            return result
        with self.lock:
            batch = list(self.records)[:batch_size]
        if not batch:
            return None
        result = _write_parquet(root, batch)
        with self.lock:
            for _ in batch:
                self.records.popleft()
        return result


def _merge_quote(previous: dict, payload: dict) -> dict:
    # Each retained field keeps its own time; top-level received_at is callback time only.
    merged = dict(previous)
    stamps = dict(previous.get("field_provenance", {}))
    for key, value in payload.items():
        if key in _QUOTE_FIELDS or key in ("value", "deal", "vol", "totalvol", "totalamt", "totalinvol", "totaloutvol"):
            stamps[key] = {"received_at": payload["received_at"],
                           "timestamp_quality": payload["timestamp_quality"],
                           "source_time_of_day": payload.get("source_time_of_day"),
                           "callback_type": payload["callback_type"]}
    merged.pop("source_time_of_day", None)
    merged.update(payload)
    merged["field_provenance"] = stamps
    merged["freshness_semantics"] = "PER_FIELD_ONLY"
    return merged


def _scalar(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    try:
        number = float(v)
        return number if math.isfinite(number) else None
    except Exception:
        try:
            return int(v)
        except Exception:
            return str(v)[:200]
def _extract_payload(obj: Any, callback_type: str) -> dict | None:
    try:
        code = getattr(obj, "StkCode", None)
        market = getattr(obj, "MarketType", None)
        if code is None or market is None:
            return None
        out = {
            "provider": "YUANTA_SPARK",
            "callback_type": callback_type,
            "market_no": int(market),
            "instrument_code": str(code),
            "received_at": _utcnow().isoformat(),
        }
        idx = getattr(obj, "IndexFlag", None)
        if idx is not None:
            out["index_flag"] = int(idx)
        val = getattr(obj, "Value", None)
        if val is not None:
            out["value"] = _scalar(val)
        for name in _QUOTE_FIELDS:
            x = getattr(obj, name, None)
            if x is not None:
                out[name] = _scalar(x)
        flag29 = getattr(obj, "IndexFlag_29", None)
        if flag29 is not None:
            t = getattr(flag29, "Time", None)
            if t is not None:
                out["source_time_of_day"] = "%02d:%02d:%02d.%03d" % (
                    int(getattr(t, "bytHour", 0) or 0),
                    int(getattr(t, "bytMin", 0) or 0),
                    int(getattr(t, "bytSec", 0) or 0),
                    int(getattr(t, "ushtMSec", 0) or 0),
                )
                out["timestamp_quality"] = "SOURCE_TIME_OF_DAY_ONLY"
            for name in ("Deal", "Vol", "TotalVol", "TotalInVol", "TotalOutVol", "TotalAmt"):
                x = getattr(flag29, name, None)
                if x is not None:
                    out[name.lower()] = _scalar(x)

        if callback_type == "SubscribeStockTick":
            t = getattr(obj, "Time", None)
            if t is not None:
                out["source_time_of_day"] = "%02d:%02d:%02d.%03d" % (
                    int(getattr(t, "bytHour", 0) or 0),
                    int(getattr(t, "bytMin", 0) or 0),
                    int(getattr(t, "bytSec", 0) or 0),
                    int(getattr(t, "ushtMSec", 0) or 0),
                )
                out["timestamp_quality"] = "SOURCE_TIME_OF_DAY_ONLY"
            for name in ("SerialNo", "BuyPrice", "SellPrice", "DealPrice", "DealVol", "InOutFlag", "Type"):
                x = getattr(obj, name, None)
                if x is not None:
                    out[name] = _scalar(x)
            out["microstructure_kind"] = "TRADE_TICK"

        if callback_type == "SubscribeFiveTickA":
            flag = int(getattr(obj, "IndexFlag", -1))
            out["microstructure_kind"] = "DEPTH"
            out["depth_index_flag"] = flag
            if flag in (50, 51):
                nested = getattr(obj, f"IndexFlag_{flag}", None)
                level_offset = 0 if flag == 50 else 5
                if nested is not None:
                    for i in range(1, 6):
                        level = level_offset + i
                        for side, pfx in (("bid", "Buy"), ("ask", "Sell")):
                            price = getattr(nested, f"{pfx}Price{i}", None)
                            vol = getattr(nested, f"{pfx}Vol{i}", None)
                            if price is not None:
                                out[f"{side}_price_{level}"] = _scalar(price)
                            if vol is not None:
                                out[f"{side}_size_{level}"] = _scalar(vol)
            elif flag in (20, 21, 42, 43):
                nested = getattr(obj, f"IndexFlag_{flag}", None)
                side = "bid" if flag in (20, 42) else "ask"
                level_offset = 0 if flag in (20, 21) else 5
                if nested is not None:
                    for i in range(1, 6):
                        level = level_offset + i
                        price = getattr(nested, f"Price{i}", None)
                        vol = getattr(nested, f"Vol{i}", None)
                        if price is not None:
                            out[f"{side}_price_{level}"] = _scalar(price)
                        if vol is not None:
                            out[f"{side}_size_{level}"] = _scalar(vol)

        out.setdefault("timestamp_quality", "LOCAL_RECEIVE_TIME_ONLY")
        return out
    except Exception:
        return None
def _load_config(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("enabled"):
        raise RuntimeError("Yuanta live recorder config is disabled or invalid")
    return data


def _runtime_config(cfg: dict, *, enable_tick_detail_measurements: bool = False) -> dict:
    """Apply maintenance-only overrides without changing tracked safe defaults."""
    out = deepcopy(cfg)
    if enable_tick_detail_measurements:
        out.setdefault("tick_detail_measurements", {})["enabled"] = True
    return out


def _yyyymm(order_code: str) -> str:
    m = re.search(r"(20\d{4})", order_code or "")
    return m.group(1) if m else "999999"


def _resolve_spec(
    spec: dict,
    rows: list[dict],
    *,
    asof: date | datetime | None = None,
) -> list[tuple[int, str, str]]:
    asof = asof or _utcnow()
    if spec.get("symbol"):
        return [(int(spec["market_no"]), str(spec["symbol"]), str(spec["key"]))]
    market = int(spec["market_no"])
    local_asof = _market_local_date(market, asof)
    prefix = str(spec.get("code_prefix", ""))
    order_root = str(spec.get("order_root", "")).strip()
    n = int(spec.get("contracts", 1))
    variant = str(spec.get("session_variant", "")).upper()
    now_month = local_asof.strftime("%Y%m")
    matches = []
    for r in rows:
        if int(r["market_code"]) != market:
            continue
        code = str(r["code"] or "")
        if prefix and not code.startswith(prefix):
            continue
        oc = str(r.get("order_code") or "")
        oc_root = (oc.strip().split() or [""])[0]
        if order_root and oc_root != order_root:
            continue
        # Drop near/next aliases and spreads; keep actual contract quote codes only.
        if "/" in code:
            continue
        if market == 3:
            taifex_pattern = re.escape(prefix) + r"(?:PM)?[A-L]\d"
            if not prefix or not re.fullmatch(taifex_pattern, code):
                continue
        if market == 207 and code.startswith("JNU") and not re.fullmatch(r"JNU(?:PM)?\d{4}", code):
            continue
        ym = _yyyymm(oc)
        if ym < now_month:
            continue
        if market in (3, 207) and len(ym) == 6 and ym.isdigit():
            from market_ai_hub.integrations.yuanta.resolver import taifex_last_trading_date, ose_last_trading_date
            year, month = int(ym[:4]), int(ym[4:])
            expiry = taifex_last_trading_date(year, month) if market == 3 else ose_last_trading_date(year, month)
            if local_asof > expiry:
                continue
        matches.append((ym, code))
    months = sorted({ym for ym, _ in matches})[:n]
    out: list[tuple[int, str, str]] = []
    for ym in months:
        codes = sorted({code for m, code in matches if m == ym})
        if variant in ("TAIFEX_PM", "OSE_PM"):
            codes = [c for c in codes if "PM" in c]
        elif variant in ("TAIFEX_DAY", "OSE_DAY"):
            codes = [c for c in codes if "PM" not in c]
        elif variant in ("BOTH", "AUTO"):
            pass
        for code in codes:
            if "/" not in code:
                out.append((market, code, str(spec["key"])))
    return out
def resolve_default_subscriptions(
    cfg: dict,
    *,
    asof: date | datetime | None = None,
) -> list[tuple[int, str, str]]:
    asof = asof or _utcnow()
    p = function_list_path()
    if p is None:
        raise RuntimeError("FunctionList.xlsx unavailable")
    rows = load_stock_code_rows(p)
    out: list[tuple[int, str, str]] = []
    for spec in list(cfg.get("subscriptions", [])) + list(cfg.get("daytime_context", [])):
        out.extend(_resolve_spec(spec, rows, asof=asof))
    dedup = {}
    for market, code, key in out:
        dedup[(market, code)] = (market, code, key)
    return list(dedup.values())


def _subscribe(rt: SparkRuntime, account: str, pairs: list[tuple[int, str, str]]) -> None:
    from System.Collections.Generic import List as NetList
    from YuantaOneAPI import WatchlistAll, enumLangType, enumMarketType
    if not pairs:
        return
    for offset in range(0, len(pairs), 200):
        delay = 0.2 - (time.monotonic() - getattr(rt, "_last_subscription_at", 0))
        if delay > 0:
            time.sleep(delay)
        items = NetList[WatchlistAll]()
        for market, code, _ in pairs[offset:offset + 200]:
            item = WatchlistAll()
            item.MarketType = enumMarketType(market)
            item.StockCode = code
            items.Add(item)
        # Bundled vendor sample omits optional Lng; installed DLL also accepts explicit UTF8.
        rt._api.SubscribeWatchlistAll(account, items, enumLangType.UTF8)
        rt._last_subscription_at = time.monotonic()


def _jnu_microstructure_pairs(cfg: dict, pairs: list[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
    mc = cfg.get("jnu_microstructure", {})
    if not mc.get("enabled", False):
        return []
    market_no = int(mc.get("market_no", 207))
    prefix = str(mc.get("code_prefix", "JNU")).upper()
    limit = max(1, min(int(mc.get("max_contracts", 2)), 8))
    selected = [
        (m, code, key)
        for m, code, key in pairs
        if int(m) == market_no and str(code).upper().startswith(prefix)
        and _JNU_CONTRACT_RE.fullmatch(str(code).upper())
    ]
    return selected[:limit]


def _subscribe_jnu_microstructure(
    rt: SparkRuntime,
    account: str,
    pairs: list[tuple[int, str, str]],
    cfg: dict,
) -> dict:
    """Best-effort quote-only JNU StockTick/FiveTick subscriptions on the existing owner."""
    mc = cfg.get("jnu_microstructure", {})
    selected = _jnu_microstructure_pairs(cfg, pairs)
    result = {
        "enabled": bool(mc.get("enabled", False)),
        "contracts": [code for _, code, _ in selected],
        "stock_tick_requested": 0,
        "five_tick_requested": 0,
        "stock_tick_error": None,
        "five_tick_error": None,
    }
    if not selected:
        return result
    from System.Collections.Generic import List as NetList
    from YuantaOneAPI import FiveTickA, StockTick, enumLangType, enumMarketType

    if mc.get("stock_tick", True):
        items = NetList[StockTick]()
        for market, code, _ in selected:
            item = StockTick()
            item.MarketType = enumMarketType(market)
            item.StockCode = code
            items.Add(item)
        try:
            rt._api.SubscribeStockTick(account, items, enumLangType.UTF8)
            result["stock_tick_requested"] = len(selected)
        except Exception as exc:
            result["stock_tick_error"] = type(exc).__name__
            if not mc.get("fail_soft", True):
                raise

    if mc.get("five_tick", True):
        items = NetList[FiveTickA]()
        for market, code, _ in selected:
            item = FiveTickA()
            item.MarketType = enumMarketType(market)
            item.StockCode = code
            items.Add(item)
        try:
            rt._api.SubscribeFiveTickA(account, items, enumLangType.UTF8)
            result["five_tick_requested"] = len(selected)
        except Exception as exc:
            result["five_tick_error"] = type(exc).__name__
            if not mc.get("fail_soft", True):
                raise
    return result


def _unsubscribe_jnu_microstructure(
    rt: SparkRuntime,
    account: str,
    pairs: list[tuple[int, str, str]],
    cfg: dict,
) -> None:
    selected = _jnu_microstructure_pairs(cfg, pairs)
    if not selected:
        return
    from System.Collections.Generic import List as NetList
    from YuantaOneAPI import FiveTickA, StockTick, enumLangType, enumMarketType
    mc = cfg.get("jnu_microstructure", {})
    if mc.get("stock_tick", True):
        try:
            items = NetList[StockTick]()
            for market, code, _ in selected:
                item = StockTick()
                item.MarketType = enumMarketType(market)
                item.StockCode = code
                items.Add(item)
            rt._api.UnSubscribeStockTick(account, items, enumLangType.UTF8)
        except Exception:
            pass
    if mc.get("five_tick", True):
        try:
            items = NetList[FiveTickA]()
            for market, code, _ in selected:
                item = FiveTickA()
                item.MarketType = enumMarketType(market)
                item.StockCode = code
                items.Add(item)
            rt._api.UnSubscribeFiveTickA(account, items, enumLangType.UTF8)
        except Exception:
            pass


def _unsubscribe(rt: SparkRuntime, account: str, pairs: list[tuple[int, str, str]]) -> None:
    from System.Collections.Generic import List as NetList
    from YuantaOneAPI import WatchlistAll, enumLangType, enumMarketType
    if not pairs:
        return
    for offset in range(0, len(pairs), 200):
        delay = 0.2 - (time.monotonic() - getattr(rt, "_last_subscription_at", 0))
        if delay > 0:
            time.sleep(delay)
        items = NetList[WatchlistAll]()
        for market, code, _ in pairs[offset:offset + 200]:
            item = WatchlistAll()
            item.MarketType = enumMarketType(market)
            item.StockCode = code
            items.Add(item)
        # Installed DLL exposes the same optional Lng parameter for unsubscribe.
        rt._api.UnSubscribeWatchlistAll(account, items, enumLangType.UTF8)
        rt._last_subscription_at = time.monotonic()


def _refresh_default_subscriptions(
    rt: SparkRuntime,
    account: str,
    cfg: dict,
    default_subscribed: dict[tuple[int, str], str],
    subscribed: dict[tuple[int, str], str],
    dynamic_subscribed: set[tuple[int, str]] | None = None,
    *,
    asof: date | datetime,
) -> dict:
    if dynamic_subscribed is None:
        dynamic_subscribed = {pair for pair, key in subscribed.items() if key == "dynamic"}
    desired_pairs = resolve_default_subscriptions(cfg, asof=asof)
    if len(desired_pairs) > 2000:
        raise ValueError("total subscription limit")
    desired = {(m, s): k for m, s, k in desired_pairs}
    additions = [(m, s, desired[(m, s)]) for m, s in desired if (m, s) not in default_subscribed]
    removals = [(m, s, default_subscribed[(m, s)]) for m, s in default_subscribed if (m, s) not in desired]
    provider_new_pairs = [(m, s) for m, s, _ in additions if (m, s) not in subscribed]
    # Keep add-before-remove continuity, but never exceed the provider's unique-subscription cap
    # even transiently. At the cap we fail closed and retain the old coverage for a later retry.
    if len(subscribed) + len(provider_new_pairs) > 2000:
        raise ValueError("total subscription limit during safe refresh")

    # Refresh changes are normally tiny. Apply one identity at a time so state remains truthful
    # if a later provider call fails after earlier calls succeeded.
    for market, code, key in additions:
        pair = (market, code)
        if pair not in subscribed:
            _subscribe(rt, account, [(market, code, key)])
        default_subscribed[pair] = key
        # Default routing wins while active, but dynamic ownership is retained separately.
        subscribed[pair] = key

    for market, code, old_key in removals:
        pair = (market, code)
        if pair in dynamic_subscribed:
            default_subscribed.pop(pair, None)
            subscribed[pair] = "dynamic"
            continue
        if subscribed.get(pair) == old_key:
            _unsubscribe(rt, account, [(market, code, old_key)])
            subscribed.pop(pair, None)
        default_subscribed.pop(pair, None)

    for pair in set(default_subscribed).intersection(desired):
        new_key = desired[pair]
        default_subscribed[pair] = new_key
        if pair in subscribed:
            subscribed[pair] = new_key
    return {"added": len(additions), "removed": len(removals), "desired": len(desired)}



def _tick_detail_measurement(
    root: Path,
    cfg: dict,
    rt: SparkRuntime,
    account: str,
    req: dict,
    runtime_build_id: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Run one bounded same-owner OSE tick-detail measurement; never logs account/prices."""
    from market_ai_hub.research.v2 import tick_detail_source as TD
    from market_ai_hub.research.v2 import tick_detail_verification as TV

    mc = cfg.get("tick_detail_measurements", {})
    if not mc.get("enabled", False):
        return False, {"status": "TICK_DETAIL_MEASUREMENT_DISABLED", "values_exposed": False}
    market = int(req.get("market_no", -1))
    symbol = str(req.get("symbol", "") or "").strip().upper()
    last_count = int(req.get("last_count", TD.MAX_LAST_COUNT))
    if market != TD.OSE_MARKET_NO:
        return False, {"status": "TICK_DETAIL_MEASUREMENT_MARKET_NOT_OSE", "values_exposed": False}
    if not _JNU_CONTRACT_RE.fullmatch(symbol):
        return False, {"status": "TICK_DETAIL_MEASUREMENT_INVALID_CONTRACT", "values_exposed": False}
    max_count = min(int(mc.get("max_last_count", TD.MAX_LAST_COUNT)), TD.MAX_LAST_COUNT)
    if last_count < 1 or last_count > max_count:
        return False, {"status": "TICK_DETAIL_MEASUREMENT_LAST_COUNT_BLOCKED", "values_exposed": False}
    raw_dir = _within(root, str(mc.get("raw_dir", "evidence/tick_detail/raw")))
    evidence_dir = _within(root, str(mc.get("evidence_dir", "evidence/tick_detail/verification")))
    loaded_build_id = str(runtime_build_id or _current_build_id())
    disk_build_id = _disk_build_id()
    if not loaded_build_id or loaded_build_id != disk_build_id:
        return False, {
            "status": "TICK_DETAIL_MEASUREMENT_RUNTIME_BUILD_STALE",
            "runtime_build_id": loaded_build_id,
            "values_exposed": False,
        }
    window = TD.ose_close_query_window(_utcnow())
    if window["status"] != TD.STATUS_QUERY_WINDOW_READY:
        return False, {
            "status": "TICK_DETAIL_MEASUREMENT_OUTSIDE_WINDOW",
            "reason": window["reason"],
            "values_exposed": False,
        }

    traces = rt.tick_detail_runtime_traces()
    matched = {x.get("request_id") for x in traces.get("callbacks", []) if x.get("request_id")}
    outstanding = [x for x in traces.get("requests", []) if x.get("request_id") not in matched]
    if outstanding:
        return False, {"status": "TICK_DETAIL_MEASUREMENT_REQUEST_ALREADY_PENDING", "values_exposed": False}
    prior_same_identity = [
        x for x in traces.get("requests", [])
        if int(x.get("market_no", -1)) == market
        and str(x.get("stock_code", "") or "").strip().upper() == symbol
    ]
    if prior_same_identity:
        return False, {
            "status": "TICK_DETAIL_MEASUREMENT_ALREADY_ATTEMPTED_IN_PROCESS",
            "values_exposed": False,
        }

    captured: dict[str, Any] = {}
    previous_hook = rt.on_tick_detail_callback

    def capture(mark, obj):
        captured["mark"] = int(mark)
        captured["obj"] = obj
        if previous_hook is not None:
            previous_hook(mark, obj)

    rt.on_tick_detail_callback = capture
    try:
        if not rt.request_tick_detail_last(account, market, symbol, last_count):
            return False, {"status": "TICK_DETAIL_MEASUREMENT_REQUEST_NOT_ACCEPTED", "values_exposed": False}
        request_trace = rt.latest_tick_detail_request()
        if request_trace is None:
            return False, {"status": "TICK_DETAIL_MEASUREMENT_REQUEST_TRACE_MISSING", "values_exposed": False}
        timeout_seconds = max(0.5, min(float(mc.get("timeout_seconds", 5.0)), 5.0))
        deadline = time.monotonic() + timeout_seconds
        exchange = None
        while time.monotonic() < deadline:
            rt.pump(0.1)
            pair = rt.latest_tick_detail_exchange()
            if pair is not None and pair[0].request_id == request_trace.request_id:
                exchange = pair
                break
        if exchange is None or "obj" not in captured:
            return False, {
                "status": "TICK_DETAIL_MEASUREMENT_CALLBACK_TIMEOUT",
                "runtime_request_id": request_trace.request_id,
                "values_exposed": False,
            }
        request_trace, callback_trace = exchange
        batch = TD.parse_tick_detail_result(
            captured["obj"],
            received_at=callback_trace.callback_received_at_utc,
        )
        raw_path = raw_dir / f"{batch.source_snapshot_id}.json"
        _atomic_json(raw_path, {
            **batch.identity_payload(),
            "timestamp_basis_status": batch.timestamp_basis_status,
            "source_snapshot_id": batch.source_snapshot_id,
        })
        crosscheck = TV.crosscheck_ose_local_timestamp_basis(
            batch,
            request_time=request_trace.request_time_utc,
            callback_received_at=callback_trace.callback_received_at_utc,
        )
        if not crosscheck["timestamp_crosscheck_passed"]:
            return False, {
                "status": "TICK_DETAIL_TIMESTAMP_BASIS_BLOCKED",
                "reason": crosscheck["reason"],
                "runtime_request_id": request_trace.request_id,
                "source_snapshot_id": batch.source_snapshot_id,
                "raw_artifact": raw_path.relative_to(root).as_posix(),
                "values_exposed": False,
            }
        evidence = TV.build_ose_runtime_verification_from_exchange(
            batch,
            request_trace=request_trace,
            callback_trace=callback_trace,
            runtime_build_id=loaded_build_id,
        )
        evidence_path = evidence_dir / f"{evidence.evidence_id}.json"
        _atomic_json(evidence_path, evidence.model_dump())
        return True, {
            "status": "TICK_DETAIL_RUNTIME_EVIDENCE_RECORDED",
            "runtime_request_id": request_trace.request_id,
            "source_snapshot_id": batch.source_snapshot_id,
            "evidence_id": evidence.evidence_id,
            "raw_artifact": raw_path.relative_to(root).as_posix(),
            "evidence_artifact": evidence_path.relative_to(root).as_posix(),
            "values_exposed": False,
        }
    finally:
        rt.on_tick_detail_callback = previous_hook


def _dynamic_requests(root: Path, cfg: dict, rt: SparkRuntime, account: str,
                      subscribed: dict[tuple[int, str], str],
                      dynamic_subscribed: set[tuple[int, str]] | None = None,
                      runtime_build_id: str = "") -> bool:
    if dynamic_subscribed is None:
        dynamic_subscribed = {pair for pair, key in subscribed.items() if key == "dynamic"}
    dc = cfg.get("dynamic_requests", {})
    if not dc.get("enabled"):
        return False
    inbox = _within(root, str(dc.get("inbox", "control/inbox")))
    processed = _within(root, str(dc.get("processed", "control/processed")))
    failed = _within(root, str(dc.get("failed", "control/failed")))
    for x in (inbox, processed, failed):
        x.mkdir(parents=True, exist_ok=True)
    allowed = {int(x) for x in dc.get("allowed_markets", [])}
    for req_path in sorted(inbox.glob("*.json"))[:10]:
        dest = processed
        result = "REQUEST_SENT_NOT_LIVE_VERIFIED"
        try:
            if req_path.is_symlink() or req_path.stat().st_size > 4096:
                raise ValueError("invalid request file")
            if (processed / req_path.name).exists() or (failed / req_path.name).exists():
                req_path.unlink()  # already recorded by this ID, do not resubmit
                continue
            req = json.loads(req_path.read_text(encoding="utf-8-sig"))
            action = str(req.get("action", ""))
            result_payload: dict[str, Any]
            if action == "subscribe":
                market = int(req["market_no"])
                symbol = str(req["symbol"])
                if market not in allowed or not _SYMBOL_RE.fullmatch(symbol):
                    raise ValueError("market/symbol not allowed")
                pair = (market, symbol)
                if pair not in dynamic_subscribed:
                    if len(dynamic_subscribed) >= int(cfg["recording"].get("max_dynamic_subscriptions", 200)):
                        raise ValueError("dynamic subscription limit")
                    if pair not in subscribed:
                        if len(subscribed) >= 2000:
                            raise ValueError("total subscription limit")
                        _subscribe(rt, account, [(market, symbol, "dynamic")])
                        subscribed[pair] = "dynamic"
                    else:
                        result = "ALREADY_SUBSCRIBED_NOT_LIVE_VERIFIED"
                    dynamic_subscribed.add(pair)
                else:
                    result = "ALREADY_SUBSCRIBED_NOT_LIVE_VERIFIED"
                result_payload = {"status": result}
            elif action == "tick_detail_measurement":
                ok, result_payload = _tick_detail_measurement(
                    root, cfg, rt, account, req,
                    runtime_build_id=runtime_build_id or _current_build_id(),
                )
                if not ok:
                    dest = failed
            elif action == "shutdown":
                result_payload = {
                    "status": "SHUTDOWN_ACCEPTED",
                    "values_exposed": False,
                }
            else:
                raise ValueError("unsupported action")
        except Exception as exc:
            dest = failed
            result_payload = {"status": "REJECTED_" + type(exc).__name__}
        result_payload["processed_at"] = _utcnow().isoformat()
        _atomic_json(dest / (req_path.stem + ".result.json"), result_payload)
        os.replace(req_path, dest / req_path.name)
        if action == "shutdown" and dest == processed:
            return True
    return False


def _durable_batch_manifest(path: Path, batch_id: str, records: list[dict]) -> dict:
    received = [str(x.get("received_at")) for x in records if x.get("received_at")]
    return {
        "version": 1,
        "status": "COMMITTED",
        "batch_id": batch_id,
        "record_count": len(records),
        "first_received_at": min(received) if received else None,
        "last_received_at": max(received) if received else None,
        "input_sha256": sha256_hex(canonical_bytes(records)),
        "parquet_sha256": sha256_hex(path.read_bytes()),
        "schema": sorted({key for record in records for key in record}),
    }


def _write_parquet(root: Path, records: list[dict], *, batch_id: str | None = None) -> str | None:
    if not records:
        return None
    import pandas as pd
    from uuid import uuid4

    out = root / "parquet" / _utcnow().strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    if batch_id is not None and not _DURABLE_BATCH_RE.fullmatch(batch_id):
        raise ValueError("invalid durable batch id")
    name = ("part-" + batch_id) if batch_id is not None else ("part-" + uuid4().hex)
    p = out / (name + ".parquet")
    tmp = p.with_suffix(".partial")
    manifest = out / (name + ".manifest.json")
    failed = out / (name + ".failed.json")

    try:
        if batch_id is not None and manifest.exists():
            if not p.exists():
                raise RuntimeError("durable batch manifest exists without parquet")
            frame = pd.read_parquet(p)
            if "_wal_seq" not in frame or "_wal_record_sha256" not in frame:
                raise RuntimeError("existing durable batch lacks WAL identity")
            actual = list(zip(frame["_wal_seq"].astype(int), frame["_wal_record_sha256"].astype(str)))
            expected = [(int(x["_wal_seq"]), str(x["_wal_record_sha256"])) for x in records]
            if actual != expected:
                raise RuntimeError("existing durable batch identity mismatch")
            expected_manifest = _durable_batch_manifest(p, batch_id, records)
            observed = json.loads(manifest.read_text(encoding="utf-8"))
            for key in ("status", "batch_id", "record_count", "input_sha256", "parquet_sha256"):
                if observed.get(key) != expected_manifest.get(key):
                    raise RuntimeError("durable batch manifest mismatch")
            failed.unlink(missing_ok=True)
            return str(p)
        # Parquet without a committed manifest is an interrupted publish. Rewrite the
        # same deterministic path from WAL before committing the manifest.

        pd.DataFrame(records).to_parquet(tmp, index=False)
        with tmp.open("rb+") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        durable_replace(tmp, p)
        if batch_id is not None:
            durable_json_replace(manifest, _durable_batch_manifest(p, batch_id, records))
            failed.unlink(missing_ok=True)
        return str(p)
    except Exception as exc:
        if batch_id is not None:
            try:
                durable_json_replace(failed, {
                    "version": 1,
                    "status": "FAILED",
                    "batch_id": batch_id,
                    "record_count": len(records),
                    "input_sha256": sha256_hex(canonical_bytes(records)),
                    "error_type": type(exc).__name__,
                    "failed_at": _utcnow().isoformat(),
                })
            except Exception:
                pass
        raise
    finally:
        tmp.unlink(missing_ok=True)


def run(
    config_path: Path = CONFIG_PATH,
    *,
    enable_tick_detail_measurements: bool = False,
) -> int:
    root = recorder_root(config_path)
    root.mkdir(parents=True, exist_ok=True)
    with _single_instance(root):
        # Pre-lock releases may still be running. A fresh heartbeat blocks an overlapping login.
        for legacy in {root, project_root() / "data" / "live" / "yuanta"}:
            status_file = legacy / "status.json"
            if status_file.exists():
                status = json.loads(status_file.read_text(encoding="utf-8"))
                heartbeat = status.get("heartbeat_at")
                if heartbeat and status.get("pid") != os.getpid():
                    if (_utcnow() - datetime.fromisoformat(heartbeat)).total_seconds() < 60:
                        raise RuntimeError("YUANTA_LIVE_ALREADY_RUNNING")
        return _run_locked(
            config_path,
            root,
            enable_tick_detail_measurements=enable_tick_detail_measurements,
        )


def _run_locked(
    config_path: Path,
    root: Path,
    *,
    enable_tick_detail_measurements: bool = False,
) -> int:
    cfg = _runtime_config(
        _load_config(config_path),
        enable_tick_detail_measurements=enable_tick_detail_measurements,
    )
    runtime_build_id = _current_build_id()
    rec = cfg["recording"]
    reconnect_policy = ReconnectPolicy.from_config(cfg.get("auto_reconnect", {}))
    if reconnect_policy.enabled and cfg.get("tick_detail_measurements", {}).get("enabled", False):
        raise ValueError("auto reconnect is disabled during tick-detail maintenance")
    status_path = _within(root, str(cfg["storage"].get("status_file", "status.json")))
    latest_path = _within(root, str(cfg["storage"].get("latest_file", "latest.json")))
    started_at = _utcnow()
    spool_cfg = cfg.get("durable_spool", {})
    spool = None
    if spool_cfg.get("enabled", False):
        try:
            spool = DurableQuoteSpool(
                _within(root, str(spool_cfg.get("dir", "spool"))),
                max_bytes=int(spool_cfg.get("max_bytes", 268435456)),
                max_records=int(spool_cfg.get("max_records", rec.get("max_buffer_records", 100000))),
            )
        except Exception as exc:
            _atomic_json(status_path, {
                "status": "START_FAILED",
                "pid": os.getpid(),
                "started_at": started_at.isoformat(),
                "stopped_at": _utcnow().isoformat(),
                "runtime_build_id": runtime_build_id,
                "auto_reconnect_enabled": reconnect_policy.enabled,
                "startup_stage": "SPOOL_RECOVERY",
                "fatal_error": type(exc).__name__,
                "crash_durability": "DURABLE_SPOOL_FAIL_CLOSED",
            })
            return 1
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard
    if OrderApiExposureGuard().scan()["gate"] != "PASS":
        raise RuntimeError("OrderApiExposureGuard failed")
    cred = read_profile_credential("securities")
    secret = read_profile_password("securities")
    if cred is None or not secret:
        raise RuntimeError("SPARK securities credential unavailable")
    defaults = resolve_default_subscriptions(cfg, asof=started_at)
    if len(defaults) > 2000:
        raise ValueError("total subscription limit")
    rt = SparkRuntime()
    default_subscribed = {(m, s): k for m, s, k in defaults}
    subscribed = dict(default_subscribed)
    dynamic_subscribed: set[tuple[int, str]] = set()
    buffer = QuoteBuffer(int(rec.get("max_buffer_records", 100000)), spool=spool)
    write_error = None
    revalidation_interval = float(
        rec.get("subscription_revalidation_seconds", _DEFAULT_SUBSCRIPTION_REVALIDATION_SECONDS)
    )
    if not math.isfinite(revalidation_interval) or revalidation_interval < 1:
        raise ValueError("subscription_revalidation_seconds must be finite and >= 1")
    last_revalidation_attempt = time.monotonic()
    revalidation_attempted_at = None
    revalidation_error = None
    revalidated_at = None
    revalidation_added: int | None = 0
    revalidation_removed: int | None = 0
    reconnect_successes = 0
    reconnect_attempts_total = 0
    last_reconnect_at = None
    last_reconnect_error = None
    last_reconnect_retry_error = None
    microstructure_subscription = {
        "enabled": bool(cfg.get("jnu_microstructure", {}).get("enabled", False)),
        "contracts": [],
        "stock_tick_requested": 0,
        "five_tick_requested": 0,
        "stock_tick_error": None,
        "five_tick_error": None,
    }
    microstructure_callbacks = {"stock_tick": 0, "five_tick": 0}
    microstructure_pairs: list[tuple[int, str, str]] = []
    startup_stage = "PRE_BROKER_READY"
    fatal_error = None
    login_msg_code = None
    exit_code = 0
    if rec.get("raw_jsonl") or not rec.get("normalized_parquet"):
        raise ValueError("persistent recorder requires Parquet; raw_jsonl is unsupported")
    last_latest = last_parquet = last_status = 0.0

    def write_startup_status(stage: str) -> None:
        durability = buffer.durability_status()
        _atomic_json(status_path, {
            "status": "STARTING",
            "pid": os.getpid(),
            "provider": "SPARK_SECURITIES_PROFILE",
            "started_at": started_at.isoformat(),
            "startup_stage": stage,
            "runtime_build_id": runtime_build_id,
            "crash_durability": durability["mode"],
            "auto_reconnect_enabled": reconnect_policy.enabled,
            "spool_pending_records": durability.get("pending_records"),
            "spool_pending_bytes": durability.get("pending_bytes"),
            "spool_acked_seq": durability.get("acked_seq"),
            "spool_error": durability.get("spool_error"),
            "tick_detail_measurements_runtime_enabled": bool(
                cfg.get("tick_detail_measurements", {}).get("enabled", False)
            ),
            "heartbeat_at": _utcnow().isoformat(),
        })

    write_startup_status(startup_stage)
    try:
        if spool is not None and buffer.snapshot()[1]:
            startup_stage = "SPOOL_REPLAY"
            write_startup_status(startup_stage)
            while buffer.snapshot()[1]:
                buffer.flush(root)
        startup_stage = "INSTANTIATE"
        write_startup_status(startup_stage)
        rt.instantiate()
        startup_stage = "OPEN_PROD"
        write_startup_status(startup_stage)
        rt.open_prod()
        startup_stage = "WAIT_CONNECTED"
        write_startup_status(startup_stage)
        if not rt.wait_connected(timeout=15.0):
            raise ConnectionError("SPARK connection was not established")
        startup_stage = "LOGIN_REQUEST"
        write_startup_status(startup_stage)
        rt.login(cred.username, secret)
        startup_stage = "WAIT_LOGIN"
        write_startup_status(startup_stage)
        outcome = rt.wait_login(timeout=25.0)
        login_msg_code = outcome.msg_code
        secret = None
        if not outcome.received or outcome.msg_code not in ("0001", "00001"):
            raise RuntimeError(f"SPARK login failed: {outcome.msg_code}")
        def on_quote(_mark, str_index, obj):
            callback_type = str(str_index)
            payload = _extract_payload(obj, callback_type)
            if payload is None:
                return
            key = (payload["market_no"], payload["instrument_code"])
            subscription_key = subscribed.get(key)
            if subscription_key is None:
                return
            payload["subscription_key"] = subscription_key
            if callback_type == "SubscribeStockTick":
                microstructure_callbacks["stock_tick"] += 1
            elif callback_type == "SubscribeFiveTickA":
                microstructure_callbacks["five_tick"] += 1
            buffer.append(payload)

        rt.on_quote_callback = on_quote
        startup_stage = "SUBSCRIBE"
        write_startup_status(startup_stage)
        _subscribe(rt, cred.username, defaults)
        microstructure_pairs = _jnu_microstructure_pairs(cfg, defaults)
        microstructure_subscription = _subscribe_jnu_microstructure(
            rt, cred.username, defaults, cfg
        )
        startup_stage = "RUNNING"
        while True:
            rt.pump(0.2)
            connection = rt.connection_snapshot()
            durability = buffer.durability_status()
            if durability.get("spool_error"):
                startup_stage = "RUNNING_SPOOL_FAULT"
                raise OSError("durable quote spool append/ack failed")
            if connection["faulted"]:
                if not reconnect_policy.enabled:
                    startup_stage = "RUNNING_CONNECTION_FAULT"
                    raise ConnectionError("SPARK connection fault")
                startup_stage = "RUNNING_RECONNECT_FLUSH"
                try:
                    while buffer.snapshot()[1]:
                        buffer.flush(root)
                except Exception:
                    startup_stage = "RUNNING_RECONNECT_PRECONDITION_FAILED"
                    raise
                desired_subscriptions = [
                    (market, symbol, key)
                    for (market, symbol), key in sorted(subscribed.items())
                ]
                startup_stage = "RUNNING_RECONNECT"
                try:
                    rt, reconnect_result = recover_quote_runtime(
                        rt,
                        policy=reconnect_policy,
                        runtime_factory=SparkRuntime,
                        account=cred.username,
                        password_provider=lambda: read_profile_password("securities"),
                        subscriptions=desired_subscriptions,
                        subscribe_fn=_subscribe,
                        quote_callback=on_quote,
                    )
                except ReconnectLifecycleError as exc:
                    reconnect_attempts_total += int(getattr(exc, "attempts", 0))
                    last_reconnect_error = getattr(exc, "last_error_type", None) or type(exc).__name__
                    startup_stage = "RUNNING_RECONNECT_FAILED"
                    raise
                reconnect_successes += 1
                reconnect_attempts_total += reconnect_result.attempts
                login_msg_code = reconnect_result.login_msg_code
                last_reconnect_retry_error = reconnect_result.last_error_type
                last_reconnect_error = None
                last_reconnect_at = _utcnow().isoformat()
                microstructure_subscription = _subscribe_jnu_microstructure(
                    rt, cred.username, desired_subscriptions, cfg
                )
                startup_stage = "RUNNING"
                continue
            now = time.time()
            if _dynamic_requests(
                root, cfg, rt, cred.username, subscribed, dynamic_subscribed,
                runtime_build_id=runtime_build_id,
            ):
                break
            monotonic_now = time.monotonic()
            if _subscription_revalidation_due(last_revalidation_attempt, monotonic_now, revalidation_interval):
                last_revalidation_attempt = monotonic_now
                revalidation_asof = _utcnow()
                revalidation_attempted_at = revalidation_asof.isoformat()
                try:
                    refresh = _refresh_default_subscriptions(
                        rt, cred.username, cfg, default_subscribed, subscribed, dynamic_subscribed,
                        asof=revalidation_asof,
                    )
                    revalidation_error = None
                    revalidated_at = _utcnow().isoformat()
                    revalidation_added = int(refresh["added"])
                    revalidation_removed = int(refresh["removed"])
                    if revalidation_added or revalidation_removed:
                        refreshed_defaults = [
                            (market, symbol, key)
                            for (market, symbol), key in sorted(default_subscribed.items())
                        ]
                        new_micro_pairs = _jnu_microstructure_pairs(cfg, refreshed_defaults)
                        old_ids = {(m, s) for m, s, _ in microstructure_pairs}
                        new_ids = {(m, s) for m, s, _ in new_micro_pairs}
                        if old_ids != new_ids:
                            _unsubscribe_jnu_microstructure(
                                rt, cred.username, microstructure_pairs, cfg
                            )
                            microstructure_pairs = new_micro_pairs
                            microstructure_subscription = _subscribe_jnu_microstructure(
                                rt, cred.username, refreshed_defaults, cfg
                            )
                except Exception as exc:
                    revalidation_error = type(exc).__name__
                    revalidation_added = None
                    revalidation_removed = None
            latest, pending, dropped = buffer.snapshot()
            if now - last_latest >= float(rec.get("latest_snapshot_seconds", 1)):
                _atomic_json(latest_path, {"updated_at": _utcnow().isoformat(), "quotes": latest})
                last_latest = now
            if now - last_status >= 5:
                last_quote = max((x.get("received_at", "") for x in latest.values()), default="")
                age = (_utcnow() - datetime.fromisoformat(last_quote)).total_seconds() if last_quote else None
                reasons = []
                if write_error:
                    reasons.append("PERSISTENCE_ERROR")
                if durability.get("spool_error"):
                    reasons.append("DURABLE_SPOOL_ERROR")
                elif dropped:
                    reasons.append("BUFFER_OVERFLOW")
                if age is None or age > 60:
                    reasons.append("NO_RECENT_CALLBACK_SESSION_UNCHECKED")
                if revalidation_error:
                    reasons.append("CONTRACT_REVALIDATION_FAILED")
                _atomic_json(status_path, {
                    "status": "DEGRADED" if reasons else "RUNNING", "pid": os.getpid(), "provider": "SPARK_SECURITIES_PROFILE",
                    "login_msg_code": login_msg_code, "subscriptions": len(subscribed),
                    "dynamic_subscriptions": len(dynamic_subscribed),
                    "last_quote_at": last_quote, "quote_age_seconds": age,
                    "health_reasons": reasons, "pending_records": pending, "dropped_records": dropped,
                    "persistence_error": write_error, "started_at": started_at.isoformat(),
                    "connection_status": "NOT_CONTINUOUSLY_VERIFIED", "freshness_semantics": "PER_FIELD_ONLY",
                    "connection_event_state": connection["state"],
                    "connection_event_code": connection["system_code"],
                    "restart_policy": (
                        "BOUNDED_FULL_RUNTIME_REPLACEMENT" if reconnect_policy.enabled
                        else "MANUAL_SINGLE_OWNER"
                    ),
                    "auto_reconnect_enabled": reconnect_policy.enabled,
                    "reconnect_successes": reconnect_successes,
                    "reconnect_attempts_total": reconnect_attempts_total,
                    "last_reconnect_at": last_reconnect_at,
                    "last_reconnect_error": last_reconnect_error,
                    "last_reconnect_retry_error": last_reconnect_retry_error,
                    "crash_durability": durability["mode"],
                    "spool_pending_records": durability.get("pending_records"),
                    "spool_pending_bytes": durability.get("pending_bytes"),
                    "spool_acked_seq": durability.get("acked_seq"),
                    "spool_error": durability.get("spool_error"),
                    "subscription_revalidation_basis": "PERIODIC_VENUE_LOCAL_DATE",
                    "subscription_revalidation_interval_seconds": revalidation_interval,
                    "subscription_revalidation_attempted_at": revalidation_attempted_at,
                    "subscription_revalidation_error": revalidation_error,
                    "subscription_revalidated_at": revalidated_at,
                    "subscription_revalidation_added": revalidation_added,
                    "subscription_revalidation_removed": revalidation_removed,
                    "startup_stage": startup_stage,
                    "tick_detail_measurements_runtime_enabled": bool(
                        cfg.get("tick_detail_measurements", {}).get("enabled", False)
                    ),
                    "jnu_microstructure_subscription": microstructure_subscription,
                    "jnu_microstructure_callbacks": dict(microstructure_callbacks),
                    "jnu_microstructure_live_verified": bool(
                        microstructure_callbacks["stock_tick"] or microstructure_callbacks["five_tick"]
                    ),
                    "heartbeat_at": _utcnow().isoformat(), "runtime_build_id": runtime_build_id,
                })
                last_status = now
            if rec.get("normalized_parquet") and now - last_parquet >= float(rec.get("parquet_flush_seconds", 30)):
                try:
                    buffer.flush(root)
                    write_error = None
                except Exception as exc:
                    write_error = type(exc).__name__  # no provider/credential text
                last_parquet = now
    except KeyboardInterrupt:
        startup_stage = "INTERRUPTED"
    except Exception as exc:
        fatal_error = type(exc).__name__
        exit_code = 1
    finally:
        secret = None
        connection = rt.connection_snapshot()
        # Recorder lifetime owns the login. Agents never logout it. Process/OS exit closes the socket.
        try:
            rt.close()
            rt.dispose()
        except Exception:
            pass
        try:
            while buffer.snapshot()[1]:
                buffer.flush(root)
            write_error = None
        except Exception as exc:
            write_error = type(exc).__name__
        durability = buffer.durability_status()
        _atomic_json(status_path, {
            "status": (
                ("RUNTIME_FAILED" if startup_stage.startswith("RUNNING") else "START_FAILED")
                if fatal_error
                else ("STOPPED_WITH_UNFLUSHED_DATA" if write_error else "STOPPED")
            ),
            "pid": os.getpid(), "stopped_at": _utcnow().isoformat(),
            "runtime_build_id": runtime_build_id,
            "startup_stage": startup_stage,
            "fatal_error": fatal_error,
            "login_msg_code": login_msg_code,
            "connection_event_state": connection["state"],
            "connection_event_code": connection["system_code"],
            "connection_faulted": connection["faulted"],
            "auto_reconnect_enabled": reconnect_policy.enabled,
            "reconnect_successes": reconnect_successes,
            "reconnect_attempts_total": reconnect_attempts_total,
            "last_reconnect_at": last_reconnect_at,
            "last_reconnect_error": last_reconnect_error,
            "last_reconnect_retry_error": last_reconnect_retry_error,
            "crash_durability": durability["mode"],
            "spool_pending_records": durability.get("pending_records"),
            "spool_pending_bytes": durability.get("pending_bytes"),
            "spool_acked_seq": durability.get("acked_seq"),
            "spool_error": durability.get("spool_error"),
            "tick_detail_measurements_runtime_enabled": bool(
                cfg.get("tick_detail_measurements", {}).get("enabled", False)
            ),
            "jnu_microstructure_subscription": microstructure_subscription,
            "jnu_microstructure_callbacks": dict(microstructure_callbacks),
            "jnu_microstructure_live_verified": bool(
                microstructure_callbacks["stock_tick"] or microstructure_callbacks["five_tick"]
            ),
            "pending_records": buffer.snapshot()[1], "dropped_records": buffer.snapshot()[2],
            "persistence_error": write_error,
        })
    return exit_code


def main() -> int:
    ap = argparse.ArgumentParser(prog="yuanta.live_quote_recorder")
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    ap.add_argument(
        "--enable-tick-detail-measurements",
        action="store_true",
        help="maintenance-only runtime override; tracked config stays disabled by default",
    )
    args = ap.parse_args()
    return run(
        args.config,
        enable_tick_detail_measurements=args.enable_tick_detail_measurements,
    )


if __name__ == "__main__":
    raise SystemExit(main())
