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


def _scalar(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    try:
        return float(v)
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
    items = NetList[WatchlistAll]()
    for market, code, _ in pairs:
        item = WatchlistAll()
        item.MarketType = enumMarketType(market)
        item.StockCode = code
        items.Add(item)
    rt._api.SubscribeWatchlistAll(account, items, enumLangType.UTF8)


def _dynamic_requests(root: Path, cfg: dict, rt: SparkRuntime, account: str,
                      subscribed: dict[tuple[int, str], str]) -> None:
    dc = cfg.get("dynamic_requests", {})
    if not dc.get("enabled"):
        return
    inbox = root / str(dc.get("inbox", "control/inbox"))
    processed = root / str(dc.get("processed", "control/processed"))
    failed = root / str(dc.get("failed", "control/failed"))
    for x in (inbox, processed, failed):
        x.mkdir(parents=True, exist_ok=True)
    allowed = {int(x) for x in dc.get("allowed_markets", [])}
    for req_path in sorted(inbox.glob("*.json")):
        dest = processed
        try:
            req = json.loads(req_path.read_text(encoding="utf-8-sig"))
            market = int(req["market_no"])
            symbol = str(req["symbol"])
            if market not in allowed or not _SYMBOL_RE.fullmatch(symbol):
                raise ValueError("market/symbol not allowed")
            if (market, symbol) not in subscribed:
                _subscribe(rt, account, [(market, symbol, "dynamic")])
                subscribed[(market, symbol)] = "dynamic"
        except Exception:
            dest = failed
        os.replace(req_path, dest / req_path.name)


def _write_parquet(root: Path, records: list[dict]) -> str | None:
    if not records:
        return None
    try:
        import pandas as pd
        out = root / "parquet" / _utcnow().strftime("%Y-%m-%d")
        out.mkdir(parents=True, exist_ok=True)
        p = out / ("part-" + _utcnow().strftime("%H%M%S-%f") + ".parquet")
        pd.DataFrame(records).to_parquet(p, index=False)
        return str(p)
    except Exception:
        return None


def run(config_path: Path = CONFIG_PATH) -> int:
    cfg = _load_config(config_path)
    rec = cfg["recording"]
    root = data_root() / str(cfg.get("storage", {}).get("root", "live/yuanta"))
    root.mkdir(parents=True, exist_ok=True)
    status_path = root / str(cfg["storage"].get("status_file", "status.json"))
    latest_path = root / str(cfg["storage"].get("latest_file", "latest.json"))
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard
    if OrderApiExposureGuard().scan()["gate"] != "PASS":
        raise RuntimeError("OrderApiExposureGuard failed")
    cred = read_profile_credential("securities")
    secret = read_profile_password("securities")
    if cred is None or not secret:
        raise RuntimeError("SPARK securities credential unavailable")
    defaults = resolve_default_subscriptions(cfg)
    rt = SparkRuntime()
    subscribed = {(m, s): k for m, s, k in defaults}
    latest: dict[str, dict] = {}
    buffer: list[dict] = []
    raw_day = ""
    raw_handle = None
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
        _subscribe(rt, cred.username, defaults)

        def on_quote(_mark, str_index, obj):
            nonlocal raw_day, raw_handle
            payload = _extract_payload(obj, str(str_index))
            if payload is None:
                return
            key = (payload["market_no"], payload["instrument_code"])
            if key not in subscribed:
                return
            payload["subscription_key"] = subscribed[key]
            latest_key = f"{key[0]}:{key[1]}"
            merged = dict(latest.get(latest_key, {}))
            merged.update(payload)
            latest[latest_key] = merged
            buffer.append(payload)
            if rec.get("raw_jsonl"):
                day = _utcnow().strftime("%Y-%m-%d")
                if raw_handle is None or raw_day != day:
                    if raw_handle is not None:
                        raw_handle.close()
                    raw_dir = root / "raw" / day
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    raw_handle = (raw_dir / "quotes.jsonl").open("a", encoding="utf-8", buffering=1)
                    raw_day = day
                raw_handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
                raw_handle.flush()

        rt.on_quote_callback = on_quote
        while True:
            rt.pump(0.2)
            now = time.time()
            _dynamic_requests(root, cfg, rt, cred.username, subscribed)
            if now - last_latest >= float(rec.get("latest_snapshot_seconds", 1)):
                _atomic_json(latest_path, {"updated_at": _utcnow().isoformat(), "quotes": latest})
                last_latest = now
            if now - last_status >= 5:
                _atomic_json(status_path, {
                    "status": "RUNNING", "pid": os.getpid(), "provider": "SPARK_SECURITIES_PROFILE",
                    "login_msg_code": outcome.msg_code, "subscriptions": len(subscribed),
                    "last_quote_at": max((x.get("received_at", "") for x in latest.values()), default=""),
                    "heartbeat_at": _utcnow().isoformat(),
                })
                last_status = now
            if rec.get("normalized_parquet") and now - last_parquet >= float(rec.get("parquet_flush_seconds", 30)):
                if buffer:
                    batch = list(buffer)
                    buffer.clear()
                    _write_parquet(root, batch)
                last_parquet = now
    except KeyboardInterrupt:
        return 0
    finally:
        secret = None
        if raw_handle is not None:
            raw_handle.close()
        if buffer and rec.get("normalized_parquet"):
            _write_parquet(root, buffer)
        # Recorder lifetime owns the login. Agents never logout it. Process/OS exit closes the socket.
        try:
            rt.close()
            rt.dispose()
        except Exception:
            pass
        _atomic_json(status_path, {
            "status": "STOPPED", "pid": os.getpid(), "stopped_at": _utcnow().isoformat()
        })
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="yuanta.live_quote_recorder")
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = ap.parse_args()
    return run(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
