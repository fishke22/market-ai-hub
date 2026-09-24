"""Persistent quote-only Yuanta SPARK recorder.

One process owns one SPARK login for its whole lifetime. Agents never receive
credentials; they read latest/status files or submit quote-only subscription
requests. No order/account/position/balance API is exposed here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import math
import threading
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
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

CONFIG_PATH = project_root() / "config" / "yuanta_live_recorder.yaml"
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9_./-]{1,40}$")
_QUOTE_FIELDS = (
    "YstPrice", "OpenRefPrice", "UpStopPrice", "DownStopPrice", "YstVol",
    "OpenPrice", "HighPrice", "LowPrice", "BuyPrice", "SellPrice", "DealPrice",
    "TotalOutVol", "TotalInVol", "TotalDealAmt", "VolFlag", "Vol", "TotalVol",
    "FixedPriceVol", "ReserveVol", "SettlementPrice", "HiContractPrice",
    "LoContractPrice", "OrderBuyCount", "OrderBuyQty", "OrderSellCount",
    "OrderSellQty", "DealBuyCount", "DealSellCount", "Volatility", "TimeDiff",
    "PrincipalPercent", "UpDownDay", "BidQty", "AskQty", "PriceTrends",
    "EstDealPrice", "EstDealVol", "EstDealVolFlag",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    """Bounded callback handoff. Failed writes keep the unacknowledged batch."""

    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("buffer capacity must be positive")
        self.capacity = capacity
        self.records = deque()
        self.lock = threading.Lock()
        self.dropped = 0
        self.latest = {}

    def append(self, payload: dict) -> None:
        with self.lock:
            key = f"{payload['market_no']}:{payload['instrument_code']}"
            self.latest[key] = _merge_quote(self.latest.get(key, {}), payload)
            if len(self.records) >= self.capacity:
                self.dropped += 1
            else:
                self.records.append(payload)

    def snapshot(self):
        with self.lock:
            return dict(self.latest), len(self.records), self.dropped

    def flush(self, root: Path, batch_size: int = 100000) -> str | None:
        with self.lock:
            batch = list(self.records)[:batch_size]
        if not batch:
            return None
        result = _write_parquet(root, batch)  # exceptions propagate; no ack on failure
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
        out.setdefault("timestamp_quality", "LOCAL_RECEIVE_TIME_ONLY")
        return out
    except Exception:
        return None
def _load_config(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("enabled"):
        raise RuntimeError("Yuanta live recorder config is disabled or invalid")
    return data


def _yyyymm(order_code: str) -> str:
    m = re.search(r"(20\d{4})", order_code or "")
    return m.group(1) if m else "999999"


def _resolve_spec(spec: dict, rows: list[dict]) -> list[tuple[int, str, str]]:
    if spec.get("symbol"):
        return [(int(spec["market_no"]), str(spec["symbol"]), str(spec["key"]))]
    market = int(spec["market_no"])
    prefix = str(spec.get("code_prefix", ""))
    order_root = str(spec.get("order_root", "")).strip()
    n = int(spec.get("contracts", 1))
    variant = str(spec.get("session_variant", "")).upper()
    now_month = _utcnow().strftime("%Y%m")
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
            if datetime.now().date() > expiry:
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
def resolve_default_subscriptions(cfg: dict) -> list[tuple[int, str, str]]:
    p = function_list_path()
    if p is None:
        raise RuntimeError("FunctionList.xlsx unavailable")
    rows = load_stock_code_rows(p)
    out: list[tuple[int, str, str]] = []
    for spec in list(cfg.get("subscriptions", [])) + list(cfg.get("daytime_context", [])):
        out.extend(_resolve_spec(spec, rows))
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
        rt._api.SubscribeWatchlistAll(account, items, enumLangType.UTF8)
        rt._last_subscription_at = time.monotonic()


def _dynamic_requests(root: Path, cfg: dict, rt: SparkRuntime, account: str,
                      subscribed: dict[tuple[int, str], str]) -> None:
    dc = cfg.get("dynamic_requests", {})
    if not dc.get("enabled"):
        return
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
            if req.get("action") != "subscribe":
                raise ValueError("unsupported action")
            market = int(req["market_no"])
            symbol = str(req["symbol"])
            if market not in allowed or not _SYMBOL_RE.fullmatch(symbol):
                raise ValueError("market/symbol not allowed")
            if (market, symbol) not in subscribed:
                if sum(k == "dynamic" for k in subscribed.values()) >= int(cfg["recording"].get("max_dynamic_subscriptions", 200)):
                    raise ValueError("dynamic subscription limit")
                if len(subscribed) >= 2000:
                    raise ValueError("total subscription limit")
                _subscribe(rt, account, [(market, symbol, "dynamic")])
                subscribed[(market, symbol)] = "dynamic"
            else:
                result = "ALREADY_SUBSCRIBED_NOT_LIVE_VERIFIED"
        except Exception as exc:
            dest = failed
            result = "REJECTED_" + type(exc).__name__
        _atomic_json(dest / (req_path.stem + ".result.json"), {"status": result, "processed_at": _utcnow().isoformat()})
        os.replace(req_path, dest / req_path.name)


def _write_parquet(root: Path, records: list[dict]) -> str | None:
    if not records:
        return None
    import pandas as pd
    from uuid import uuid4
    out = root / "parquet" / _utcnow().strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    p = out / ("part-" + uuid4().hex + ".parquet")
    tmp = p.with_suffix(".partial")
    try:
        pd.DataFrame(records).to_parquet(tmp, index=False)
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)
    return str(p)


def run(config_path: Path = CONFIG_PATH) -> int:
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
        return _run_locked(config_path, root)


def _run_locked(config_path: Path, root: Path) -> int:
    cfg = _load_config(config_path)
    rec = cfg["recording"]
    status_path = _within(root, str(cfg["storage"].get("status_file", "status.json")))
    latest_path = _within(root, str(cfg["storage"].get("latest_file", "latest.json")))
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard
    if OrderApiExposureGuard().scan()["gate"] != "PASS":
        raise RuntimeError("OrderApiExposureGuard failed")
    cred = read_profile_credential("securities")
    secret = read_profile_password("securities")
    if cred is None or not secret:
        raise RuntimeError("SPARK securities credential unavailable")
    defaults = resolve_default_subscriptions(cfg)
    if len(defaults) > 2000:
        raise ValueError("total subscription limit")
    rt = SparkRuntime()
    subscribed = {(m, s): k for m, s, k in defaults}
    buffer = QuoteBuffer(int(rec.get("max_buffer_records", 100000)))
    write_error = None
    started_at = _utcnow()
    recording_day = started_at.date()
    if rec.get("raw_jsonl") or not rec.get("normalized_parquet"):
        raise ValueError("persistent recorder requires Parquet; raw_jsonl is unsupported")
    last_latest = last_parquet = last_status = 0.0
    try:
        rt.instantiate()
        rt.open_prod()
        rt.wait_connected(timeout=15.0)
        rt.login(cred.username, secret)
        outcome = rt.wait_login(timeout=25.0)
        secret = None
        if not outcome.received or outcome.msg_code not in ("0001", "00001"):
            raise RuntimeError(f"SPARK login failed: {outcome.msg_code}")
        def on_quote(_mark, str_index, obj):
            payload = _extract_payload(obj, str(str_index))
            if payload is None:
                return
            key = (payload["market_no"], payload["instrument_code"])
            subscription_key = subscribed.get(key)
            if subscription_key is None:
                return
            payload["subscription_key"] = subscription_key
            buffer.append(payload)

        rt.on_quote_callback = on_quote
        _subscribe(rt, cred.username, defaults)
        while True:
            rt.pump(0.2)
            now = time.time()
            _dynamic_requests(root, cfg, rt, cred.username, subscribed)
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
                if dropped:
                    reasons.append("BUFFER_OVERFLOW")
                if age is None or age > 60:
                    reasons.append("NO_RECENT_CALLBACK_SESSION_UNCHECKED")
                if _utcnow().date() != recording_day:
                    reasons.append("CONTRACT_REVALIDATION_REQUIRED")
                _atomic_json(status_path, {
                    "status": "DEGRADED" if reasons else "RUNNING", "pid": os.getpid(), "provider": "SPARK_SECURITIES_PROFILE",
                    "login_msg_code": outcome.msg_code, "subscriptions": len(subscribed),
                    "last_quote_at": last_quote, "quote_age_seconds": age,
                    "health_reasons": reasons, "pending_records": pending, "dropped_records": dropped,
                    "persistence_error": write_error, "started_at": started_at.isoformat(),
                    "connection_status": "NOT_CONTINUOUSLY_VERIFIED", "freshness_semantics": "PER_FIELD_ONLY",
                    "restart_policy": "MANUAL_SINGLE_OWNER", "crash_durability": "BUFFERED_NOT_ZERO_LOSS",
                    "heartbeat_at": _utcnow().isoformat(),
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
        return 0
    finally:
        secret = None
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
        _atomic_json(status_path, {
            "status": "STOPPED_WITH_UNFLUSHED_DATA" if write_error else "STOPPED",
            "pid": os.getpid(), "stopped_at": _utcnow().isoformat(),
            "pending_records": buffer.snapshot()[1], "dropped_records": buffer.snapshot()[2],
            "persistence_error": write_error,
        })
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="yuanta.live_quote_recorder")
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = ap.parse_args()
    return run(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
