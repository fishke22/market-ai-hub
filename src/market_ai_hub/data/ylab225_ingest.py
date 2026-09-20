"""Phase 2V-E — 225LABO manual ingest + forward daily cycle.

Incremental, idempotent ingest of 225LABO minute OHLCV → normalized daily bars.
Manual only (no auto-scrape). Source immutable. Forward forecast create/settle/status.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from market_ai_hub.config.settings import project_root

BARS_PATH = project_root() / "data" / "normalized" / "ose_micro" / "ose_micro_daily_bar_v1.parquet"
INBOX = Path(r"D:\MARKET_AI_HUB_PRIVATE_INBOX\225labo")
RAW_ARCHIVE = project_root() / "data" / "raw" / "ylab225" / "archive"
MICRO_LISTING = "2023-05-29"
TICK = 5


def _now():
    return datetime.now(timezone.utc)


def freshness_state(last_bar_date: datetime | None) -> str:
    """Return FRESH / STALE / MISSING_CURRENT_SESSION / IMPORT_PENDING."""
    if last_bar_date is None:
        return "MISSING_CURRENT_SESSION"
    age_days = (_now() - last_bar_date).total_seconds() / 86400
    if age_days <= 3:
        return "FRESH"
    if age_days <= 7:
        return "MISSING_CURRENT_SESSION"
    return "STALE"


def load_bars() -> pd.DataFrame:
    if not BARS_PATH.exists():
        return pd.DataFrame(columns=["trading_date", "open", "high", "low", "close", "volume", "count"])
    return pd.read_parquet(BARS_PATH).sort_values("trading_date")


def build_daily_bars_from_minutes(rows) -> dict:
    """Convert 225LABO minute rows (date,time,o,h,l,c,v) → OSE trading-day bars."""
    bars = {}
    for r in rows:
        if len(r) < 7 or r[0] is None or r[1] is None:
            continue
        try:
            cal_date = str(r[0])[:10]
            cal_time = str(r[1])
            o = float(r[2]); h = float(r[3]); l = float(r[4]); c = float(r[5])
            v = float(r[6]) if r[6] is not None else 0.0
        except Exception:
            continue
        # OSE trading date: night session (>=16:30) belongs to next trading date
        if cal_time >= "16:30:00":
            td = (pd.Timestamp(cal_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            td = cal_date
        if td not in bars:
            bars[td] = {"trading_date": td, "open": o, "high": h, "low": l, "close": c, "volume": v, "count": 1}
        else:
            d = bars[td]
            d["high"] = max(d["high"], h)
            d["low"] = min(d["low"], l)
            d["close"] = c
            d["volume"] += v
            d["count"] += 1
    return bars


def _validate_bar(row: dict) -> list[str]:
    """Validate a daily bar against Direct Target invariants. Returns list of errors."""
    errs = []
    if row["trading_date"] < MICRO_LISTING:
        errs.append("PRE_LISTING")
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if not (l <= o <= h and l <= c <= h):
        errs.append("INVALID_OHLC")
    if row["volume"] < 0:
        errs.append("NEGATIVE_VOLUME")
    # tick grid check (prices should be multiples of 5)
    for p in (o, h, l, c):
        if abs(p - round(p / TICK) * TICK) > 1e-6:
            errs.append("TICK_GRID_VIOLATION")
            break
    return errs


def ingest_from_inbox() -> dict:
    """Detect new 225LABO files in inbox, validate, hash, incremental append to normalized bars.

    Idempotent: same file re-run produces no duplicates. Source immutable (moved to archive, never overwritten).
    """
    INBOX.mkdir(parents=True, exist_ok=True)
    RAW_ARCHIVE.mkdir(parents=True, exist_ok=True)

    result = {"imported": [], "rejected": [], "skipped": [], "new_days": 0}

    for f in sorted(INBOX.iterdir()):
        if f.suffix.lower() not in (".zip", ".xlsx"):
            continue
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        # detect schema changes: file must be a 225LABO zip with 1 xlsx
        try:
            import zipfile, openpyxl, io
            if f.suffix.lower() == ".zip":
                with zipfile.ZipFile(f) as z:
                    names = z.namelist()
                    if len(names) != 1 or not names[0].endswith(".xlsx"):
                        result["rejected"].append({"file": f.name, "reason": "SCHEMA_CHANGED: unexpected zip structure"})
                        continue
                    with z.open(names[0]) as zf:
                        rows = list(openpyxl.load_workbook(zf, read_only=True).active.iter_rows(values_only=True))
            else:
                rows = list(openpyxl.load_workbook(f, read_only=True).active.iter_rows(values_only=True))
        except Exception as e:
            result["rejected"].append({"file": f.name, "reason": f"SCHEMA_CHANGED: {str(e)[:80]}"})
            continue

        # header check: expect date/time/o/h/l/c/v (7 cols)
        if not rows or len(rows[0]) < 7:
            result["rejected"].append({"file": f.name, "reason": "SCHEMA_CHANGED: missing columns"})
            continue

        bars = build_daily_bars_from_minutes(rows[1:])
        # validate
        valid = {}
        for td, d in bars.items():
            errs = _validate_bar(d)
            if errs:
                result["rejected"].append({"file": f.name, "trading_date": td, "reason": ",".join(errs)})
            else:
                valid[td] = d

        # incremental append (idempotent)
        existing = load_bars()
        existing_dates = set(existing["trading_date"].astype(str)) if len(existing) else set()
        new_rows = [v for td, v in sorted(valid.items()) if td not in existing_dates]
        if new_rows:
            new_df = pd.DataFrame(new_rows)
            new_df["trading_date"] = pd.to_datetime(new_df["trading_date"])
            merged = pd.concat([existing, new_df], ignore_index=True) if len(existing) else new_df
            merged = merged.drop_duplicates(subset="trading_date").sort_values("trading_date").reset_index(drop=True)
            merged.to_parquet(BARS_PATH, index=False)
            result["new_days"] = len(new_rows)

        # archive raw (immutable), never overwrite
        archive_path = RAW_ARCHIVE / f"{f.stem}_{sha[:16]}{f.suffix}"
        if not archive_path.exists():
            shutil.copy2(f, archive_path)
        f.unlink()  # remove from inbox after successful import
        result["imported"].append({"file": f.name, "sha256": sha, "new_days": len(new_rows)})

    return result


def coverage_summary() -> dict:
    bars = load_bars()
    if len(bars) == 0:
        return {"last_bar_date": None, "freshness": "MISSING_CURRENT_SESSION", "n_days": 0}
    last = bars["trading_date"].max()
    return {
        "last_bar_date": str(pd.Timestamp(last).date()),
        "freshness": freshness_state(pd.Timestamp(last).to_pydatetime().replace(tzinfo=timezone.utc)),
        "n_days": int(len(bars)),
        "first_bar_date": str(pd.Timestamp(bars["trading_date"].min()).date()),
    }


def run_daily_cycle() -> dict:
    """Daily forward operation: ingest → freshness → create → settle → status → summary."""
    from market_ai_hub.research import forward_shadow as fs

    ing = ingest_from_inbox()
    cov = coverage_summary()

    created = None
    if cov["freshness"] == "FRESH":
        created = fs.create_daily_forecasts()
    else:
        created = {"status": "FORECAST_SKIPPED_DATA_QUALITY", "reason": f"freshness={cov['freshness']}"}

    settled = fs.settle_pending()
    status = fs.build_status()
    summary = write_daily_summary(cov, created, settled, status)

    return {"ingest": ing, "coverage": cov, "create": created, "settled": settled, "summary": summary}


def write_daily_summary(cov: dict, created: dict, settled: dict, status: dict) -> str:
    """Write FORWARD_DAILY_SUMMARY.md (human-readable, no BUY/SELL)."""
    lines = [
        "# FORWARD DAILY SUMMARY",
        f"- Data: {cov['freshness']} (last bar {cov.get('last_bar_date', 'N/A')})",
        f"- Forecast today: {'CREATED' if created.get('created') else created.get('status', 'N/A')}",
        f"- Settled: {len(settled.get('settled', []))}",
        f"- Forward N: {status.get('forecasts_created', 0)} created / {status.get('settled', 0)} settled / {status.get('pending', 0)} pending",
        f"- Evidence label: RESEARCH_FORECAST_ONLY / NON_EXECUTABLE_FORECAST_EDGE",
        f"- Generated: {_now().isoformat()}",
    ]
    out = project_root() / "FORWARD_DAILY_SUMMARY.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "\n".join(lines)
