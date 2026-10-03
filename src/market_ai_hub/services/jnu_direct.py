"""Direct Osaka Nikkei 225 Micro settlement research path.

Uses official JPX/OSE Micro contract settlements only. The Accuracy v2 forecast
target is the next published settlement observation for the current exact contract,
not an intraday trade price and not necessarily the next OSE holiday session.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
import math
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_ai_hub.automation.data_lake import default_data_root
from market_ai_hub.schemas.market_data import validate_price_path
from market_ai_hub.services.calendar import next_ose_derivatives_sessions, next_trading_sessions
from market_ai_hub.services.horizon import parse_horizon
from market_ai_hub.services.model_runtime import get_chronos, get_timesfm
from market_ai_hub.targets.jpx_daily import JPXOSEDailyReportProvider, public_daily_report_months
from market_ai_hub.targets.jpx_settlement import JPXSettlementProvider

DIRECT_MODEL_SCOPE = "DIRECT_MICRO_SETTLEMENT_RESEARCH"
MIN_DIRECT_SAMPLES = 20
FLAT_THRESHOLD = 0.005

DIRECT_VALIDATION_HISTORY_LEN = 32
DIRECT_VALIDATION_ORIGINS = 10
_REFRESH_TTL_SECONDS = 1800
_refresh_cache: tuple[float, dict[str, Any]] | None = None


def normalize_jnu_contract_month(value: str = "") -> str:
    """Normalize common JNU contract aliases to canonical YYYYMM form."""
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if text.startswith("JNUPM") and len(text) == 9 and text[-4:].isdigit():
        text = text[-4:]
    elif text.startswith("JNU") and len(text) == 7 and text[-4:].isdigit():
        text = text[-4:]
    if len(text) == 4 and text.isdigit():
        return f"20{text}"
    if len(text) == 6 and text.isdigit():
        return text
    return text


def refresh_jnu_direct_data(*, force: bool = False) -> dict[str, Any]:
    """Best-effort public JPX refresh; never uses broker credentials or trading APIs."""
    global _refresh_cache
    now_mono = time.monotonic()
    if (
        not force
        and _refresh_cache is not None
        and now_mono - _refresh_cache[0] <= _REFRESH_TTL_SECONDS
    ):
        return dict(_refresh_cache[1])

    result: dict[str, Any] = {
        "status": "OK",
        "broker_used": False,
        "credentials_used": False,
        "settlement": {"status": "NOT_REFRESHED"},
        "archive": {"status": "NOT_REFRESHED"},
    }

    # Latest official settlement CSV: walk back across weekends/holidays.
    settlement = JPXSettlementProvider()
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    settlement_errors: list[str] = []
    for i in range(10):
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        try:
            rows = settlement.fetch_parse(d)
        except Exception as exc:
            settlement_errors.append(f"{d}:{type(exc).__name__}")
            continue
        micro = [r for r in rows if r.product == "Nikkei 225 Micro Futures"]
        if not micro:
            continue
        path = settlement.save(d, rows)
        result["settlement"] = {
            "status": "OK",
            "trade_date": d,
            "micro_contracts": len(micro),
            "saved": str(path),
        }
        break
    else:
        result["settlement"] = {
            "status": "NO_RECENT_SETTLEMENT",
            "errors": settlement_errors,
        }
        result["status"] = "PARTIAL"

    # Current public daily-report month keeps exact-contract history fresh.
    try:
        months = public_daily_report_months()
        selected = months[-1:] if months else []
        result["archive"] = (
            JPXOSEDailyReportProvider().sync_public_months(selected, skip_existing=True)
            if selected else {"status": "NO_PUBLIC_MONTH"}
        )
        if result["archive"].get("status") not in {"OK", "PARTIAL"}:
            result["status"] = "PARTIAL"
    except Exception as exc:
        result["archive"] = {"status": "REFRESH_FAILED", "error": type(exc).__name__}
        result["status"] = "PARTIAL"

    _refresh_cache = (now_mono, dict(result))
    return result


def validate_jnu_direct_history(
    contract_month: str = "",
    *,
    force: bool = False,
    horizon_steps: int = 1,
) -> dict[str, Any]:
    """Rolling-origin historical diagnostic for exact-contract settlement forecasts.

    This is historical OOS evidence only. It is never W3 forward evidence and never
    W4 calibrated probability evidence.
    """
    from market_ai_hub.services.validation import (
        TS_VALIDATION_SCHEMA_VERSION,
        TsValidationStore,
        determine_validation_status,
        run_ts_oos_validation,
    )

    series, meta = load_direct_micro_settlements(contract_month)
    if meta.get("status") != "OK":
        return {"status": "DATA_NOT_READY", "models": {}, "data": meta}
    steps = int(horizon_steps)
    if steps < 1:
        raise ValueError("horizon_steps must be >= 1")
    required = DIRECT_VALIDATION_HISTORY_LEN + DIRECT_VALIDATION_ORIGINS + steps - 1
    if len(series) < required:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "models": {},
            "sample_count": len(series),
            "minimum_samples": required,
        }

    symbol = f"{meta['quote_code']}_SETTLEMENT"
    store = TsValidationStore()
    models: dict[str, Any] = {}
    model_availability: list[dict[str, Any]] = []
    for name, factory in (("chronos-2", get_chronos), ("timesfm-3.0", get_timesfm)):
        cached = None if force else store.latest(name, symbol)
        result = (cached or {}).get("result") if cached else None
        current = bool(
            result
            and result.get("validation_schema_version") == TS_VALIDATION_SCHEMA_VERSION
            and result.get("window", {}).get("end") == meta["latest_date"]
            and int(result.get("history_len", 0)) == DIRECT_VALIDATION_HISTORY_LEN
            and int(result.get("n_origins", 0)) == DIRECT_VALIDATION_ORIGINS
            and int(result.get("horizon_steps", 0)) == steps
        )
        if not current:
            try:
                result = run_ts_oos_validation(
                    factory(),
                    name,
                    symbol,
                    series,
                    n_origins=DIRECT_VALIDATION_ORIGINS,
                    history_len=DIRECT_VALIDATION_HISTORY_LEN,
                    horizon_steps=steps,
                )
            except Exception as exc:  # noqa: BLE001
                # A governance-blocked or unloadable model must not abort the other
                # models' historical validation. Mirror analyze_jnu_direct's
                # model_availability pattern: record UNAVAILABLE with the reason and
                # continue. The purpose gate itself stays fail-closed (TimesFM-3
                # weights remain RESEARCH-only and are never loaded on a serving path).
                reason = type(exc).__name__
                model_availability.append(
                    {"model": name, "status": "UNAVAILABLE", "reason": reason})
                models[name] = {
                    "status": "MODEL_UNAVAILABLE",
                    "n_oos": 0,
                    "mase": None,
                    "direction_accuracy": None,
                    "beats_last_price_naive": False,
                    "beats_drift": False,
                    "paired_vs_last_price_naive": None,
                    "window_end": None,
                    "horizon_steps": steps,
                    "reasons": [f"model unavailable: {reason}"],
                }
                continue
            status, reasons = determine_validation_status(result)
            if result.get("status") == "OK":
                store.save(result, status, run_kind="RUNTIME_VALIDATION")
        else:
            status, reasons = determine_validation_status(result)
        model_availability.append({"model": name, "status": "AVAILABLE"})

        ev = (result or {}).get("eval", {})
        models[name] = {
            "status": status,
            "n_oos": int(ev.get("n_oos", 0) or 0),
            "mase": ev.get("model", {}).get("mase"),
            "direction_accuracy": ev.get("model", {}).get("direction_accuracy"),
            "beats_last_price_naive": bool(ev.get("beats_naive_mae", False)),
            "beats_drift": bool(ev.get("beats_drift_mae", False)),
            "paired_vs_last_price_naive": (result or {}).get("paired_vs_last_price_naive"),
            "window_end": (result or {}).get("window", {}).get("end"),
            "horizon_steps": int((result or {}).get("horizon_steps", steps) or steps),
            "reasons": reasons,
        }

    statuses = {v["status"] for v in models.values()}
    beats = [v["beats_last_price_naive"] for v in models.values()]
    if "VALIDATED" in statuses:
        overall = "HISTORICAL_VALIDATED"
    elif "EXPERIMENTAL" in statuses:
        overall = "HISTORICAL_EXPERIMENTAL"
    else:
        overall = "HISTORICAL_UNVALIDATED"
    return {
        "status": "OK",
        "overall": overall,
        "models": models,
        "model_availability": model_availability,
        "horizon_steps": steps,
        "target_semantics": "EXACT_CONTRACT_TERMINAL_SETTLEMENT_AT_REQUESTED_HORIZON",
        "all_models_beat_last_price_naive": bool(beats) and all(beats),
        "any_model_beats_last_price_naive": any(beats),
        "scope": "HISTORICAL_OOS_ONLY",
        "not_forward_evidence": True,
        "not_calibration_evidence": True,
        "latest_date": meta["latest_date"],
    }


def _date_text(value: object) -> str:
    s = str(value or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s[:10]


def _current_settlement_frame() -> pd.DataFrame:
    base = default_data_root() / "raw" / "jpx" / "settlement"
    files = list(base.rglob("*.parquet")) if base.exists() else []
    frames = []
    for p in files:
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        if "product" not in df.columns:
            continue
        df = df[df["product"].astype(str).eq("Nikkei 225 Micro Futures")].copy()
        if df.empty:
            continue
        df["contract_month"] = df["contract"].astype(str)
        df["date"] = df["date"].map(_date_text)
        df["settlement"] = pd.to_numeric(df["settlement_price"], errors="coerce")
        df["_priority"] = 2
        df["_received_at"] = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        df["_source_path"] = str(p)
        frames.append(df[[
            "contract_month", "date", "settlement", "source_url", "source_hash",
            "_priority", "_received_at", "_source_path",
        ]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_current_micro_settlement_receipts(contract_month: str = "") -> pd.DataFrame:
    """Load official JPX settlement-CSV rows carrying observed local receipt time.

    Archive rows without an observed local receipt timestamp are intentionally excluded:
    P5 uses this narrow view to prove prediction-before-outcome causality.
    """
    contract_month = normalize_jnu_contract_month(contract_month)
    frame = _current_settlement_frame()
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["contract_month"] = frame["contract_month"].astype(str)
    frame["date"] = frame["date"].map(_date_text)
    frame["settlement"] = pd.to_numeric(frame["settlement"], errors="coerce")
    frame["_received_at"] = pd.to_datetime(frame["_received_at"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["settlement", "_received_at"])
    frame = frame[frame["settlement"].map(math.isfinite) & (frame["settlement"] > 0)]
    if contract_month:
        frame = frame[frame["contract_month"].eq(str(contract_month))]
    return frame.sort_values(["date", "_received_at", "source_hash"]).reset_index(drop=True)


def load_direct_micro_settlements(contract_month: str = "") -> tuple[pd.Series, dict[str, Any]]:
    """Load an exact-contract settlement series from persisted official JPX sources."""
    contract_month = normalize_jnu_contract_month(contract_month)
    daily = JPXOSEDailyReportProvider().load("Nikkei 225 Micro")
    frames = []
    if daily is not None and not daily.empty:
        d = daily.copy()
        d["date"] = d["date"].map(_date_text)
        d["settlement"] = pd.to_numeric(d["settlement"], errors="coerce")
        d["_priority"] = 1
        d["_received_at"] = pd.NaT
        d["_source_path"] = ""
        keep = [
            "contract_month", "date", "settlement", "source_url", "source_hash",
            "_priority", "_received_at", "_source_path",
        ]
        frames.append(d[keep])
    current = _current_settlement_frame()
    if not current.empty:
        frames.append(current)
    if not frames:
        return pd.Series(dtype=float), {
            "status": "NO_DIRECT_HISTORY",
            "reason": "尚未落地大阪微型日經官方限月清算價歷史",
        }

    df = pd.concat(frames, ignore_index=True)
    df["contract_month"] = df["contract_month"].astype(str)
    df = df.dropna(subset=["settlement"])
    df = df[df["settlement"].map(math.isfinite) & (df["settlement"] > 0)]
    df = df.sort_values(["date", "_priority"]).drop_duplicates(
        subset=["date", "contract_month"], keep="last"
    )
    latest_date = str(df["date"].max())
    latest = df[df["date"].eq(latest_date)]
    if not contract_month:
        # Target contract policy: the broker-tradable month wins. JPX publishes rows for
        # months the broker never lists (202610/202611), so the old "earliest month" rule
        # silently anchored the whole analysis on an untradable contract.
        from market_ai_hub.integrations.yuanta.resolver import select_target_contract_month

        contract_month, contract_source = select_target_contract_month(
            latest["contract_month"].unique())
    exact = df[df["contract_month"].eq(str(contract_month))].copy()
    exact = exact.sort_values("date")
    if exact.empty:
        return pd.Series(dtype=float), {
            "status": "CONTRACT_HISTORY_NOT_AVAILABLE",
            "contract_month": contract_month,
            "latest_official_date": latest_date,
            "contract_source": contract_source,
        }

    idx = pd.to_datetime(exact["date"], errors="coerce")
    valid = idx.notna()
    exact = exact.loc[valid].copy()
    idx = idx[valid]
    # OSE daytime terminal/settlement reference timestamp, represented in UTC.
    idx = idx.dt.tz_localize("Asia/Tokyo").dt.tz_convert("UTC") + pd.Timedelta(hours=15, minutes=45)
    series = pd.Series(exact["settlement"].astype(float).to_numpy(), index=pd.DatetimeIndex(idx), name="settlement")
    meta = {
        "status": "OK",
        "contract_source": contract_source,
        "contract_month": str(contract_month),
        "quote_code": f"JNU{str(contract_month)[2:]}" if len(str(contract_month)) == 6 else "JNU",
        "sample_count": int(len(series)),
        "first_date": str(exact["date"].iloc[0]),
        "latest_date": str(exact["date"].iloc[-1]),
        "latest_settlement": float(series.iloc[-1]),
        "source": "JPX/OSE 官方每日報告與清算價",
        "series_semantics": "EXACT_CONTRACT",
        "price_semantics": "SETTLEMENT",
        "latest_source_hash": str(exact["source_hash"].iloc[-1] or ""),
        "latest_source_url": str(exact["source_url"].iloc[-1] or ""),
        "latest_received_at": (
            pd.Timestamp(exact["_received_at"].iloc[-1]).isoformat()
            if pd.notna(exact["_received_at"].iloc[-1]) else None
        ),
    }
    return series, meta


def _model_result(adapter, name: str, series: pd.Series, steps: int, target_dates: list[str]) -> dict:
    raw = adapter.predict(series, horizon=steps)
    path = raw.get("path") or {}
    validate_price_path(path, steps)
    p10 = list(path.get("p10") or [])
    p50 = list(path.get("p50") or [])
    p90 = list(path.get("p90") or [])
    if len(p50) < steps or not p50:
        raise ValueError("model returned incomplete path")
    last = float(series.iloc[-1])
    terminal = float(p50[-1])
    forecast_path = {
        "semantics": "PUBLISHED_SETTLEMENT_PATH_QUANTILES",
        "target_dates": list(target_dates),
        "p10": [float(x) for x in p10],
        "p50": [float(x) for x in p50],
        "p90": [float(x) for x in p90],
        "not_intraday_high_low": True,
        "not_support_resistance": True,
        "not_touch_probability": True,
        "not_first_passage_probability": True,
    }
    return {
        "model": name,
        "p10": float(p10[-1]) if len(p10) >= steps else None,
        "p50": terminal,
        "p90": float(p90[-1]) if len(p90) >= steps else None,
        "expected_return": (terminal - last) / last if last else 0.0,
        "target_dates": list(target_dates),
        "forecast_path": forecast_path,
        "terminal_value_semantics": "FINAL_STEP_OF_PUBLISHED_SETTLEMENT_PATH",
        "validation": "UNVALIDATED",
    }


def _stance(expected_return: float | None) -> str:
    if expected_return is None:
        return "INSUFFICIENT_EVIDENCE"
    if expected_return > FLAT_THRESHOLD:
        return "BULLISH_LEAN"
    if expected_return < -FLAT_THRESHOLD:
        return "BEARISH_LEAN"
    return "NEUTRAL"


def next_published_settlement_observation_dates(
    reference_date: str,
    steps: int,
) -> list[str]:
    """Expected dates for the next published daily settlement observations.

    Accuracy v2 evaluates the next row in the official published-settlement series,
    not every OSE holiday-trading session.  JPX report availability is governed
    conservatively by the XTKS cash-business publication calendar, so the expected
    observation dates follow those business dates as well.  This prevents the
    2026-09-18 -> 2026-09-21 holiday-session mismatch from reappearing.
    """
    if int(steps) < 1:
        return []
    return next_trading_sessions("^N225", reference_date, int(steps))


def analyze_jnu_direct(
    horizon: str = "1d",
    contract_month: str = "",
    *,
    validate_history: bool = False,
) -> dict[str, Any]:
    """Forecast the current JNU exact-contract settlement from official Micro history."""
    spec = parse_horizon(horizon, "1d")
    if not spec.supported:
        return {"status": "UNSUPPORTED_HORIZON", "message": "目前直接模型只支援日線交易日 horizon"}
    steps = int(spec.effective_horizon_steps)
    series, meta = load_direct_micro_settlements(contract_month)
    if meta.get("status") != "OK":
        return {"status": meta.get("status"), "data": meta, "direct_model_available": False}
    try:
        from market_ai_hub.research.accuracy_v2_p4_engine import analyze_no_new_forward_outcome
        robust_analysis = analyze_no_new_forward_outcome(
            current_series=series,
            current_meta=meta,
        )
    except Exception as exc:
        robust_analysis = {
            "status": "UNAVAILABLE",
            "reason": type(exc).__name__,
        }
    if len(series) < MIN_DIRECT_SAMPLES:
        return {
            "status": "INSUFFICIENT_DIRECT_HISTORY",
            "direct_model_available": False,
            "data": meta,
            "minimum_samples": MIN_DIRECT_SAMPLES,
        }

    from market_ai_hub.integrations.yuanta.resolver import ose_last_trading_date
    month = str(meta["contract_month"])
    expiry = ose_last_trading_date(int(month[:4]), int(month[4:]))
    target_dates = next_published_settlement_observation_dates(
        str(meta["latest_date"]),
        steps,
    )
    if not target_dates or any(pd.Timestamp(d).date() > expiry for d in target_dates):
        return {
            "status": "ROLL_BOUNDARY_BLOCKED",
            "direct_model_available": False,
            "data": meta,
            "target_dates": target_dates,
            "expiry": str(expiry),
        }

    models = []
    errors = []
    model_availability = []
    for name, factory in (("Chronos-2", get_chronos), ("TimesFM-3.0", get_timesfm)):
        try:
            models.append(_model_result(factory(), name, series, steps, target_dates))
            model_availability.append({"model": name, "status": "AVAILABLE"})
        except Exception as exc:
            reason = type(exc).__name__
            errors.append(f"{name}:{reason}")
            model_availability.append({"model": name, "status": "UNAVAILABLE", "reason": reason})
    if not models:
        if robust_analysis.get("status") == "OK":
            reference = float(meta["latest_settlement"])
            interval = robust_analysis.get("empirical_interval") or {}
            return {
                "status": "OK",
                "direct_model_available": False,
                "scope": DIRECT_MODEL_SCOPE,
                "target": "OSE_NIKKEI225_MICRO_FUTURES",
                "product_name": "大阪日經225微型期貨（JNU）",
                "contract_month": meta["contract_month"],
                "quote_code": meta["quote_code"],
                "forecast_price_type": "NEXT_PUBLISHED_SETTLEMENT_OBSERVATION",
                "horizon": horizon,
                "target_dates": target_dates,
                "data": meta,
                "models": [],
                "model_availability": model_availability,
                "ensemble": {
                    "p10": interval.get("lower_price"),
                    "p50": reference,
                    "p90": interval.get("upper_price"),
                    "expected_return": 0.0,
                    "method": "zero_return_naive_with_development_interval",
                    "ensemble_mode": "BASELINE_ONLY",
                    "available_model_count": 0,
                    "available_models": [],
                },
                "research_stance": "NEUTRAL",
                "research_stance_strength": "BASELINE_ONLY_NO_PREDICTIVE_GAIN",
                "historical_validation": {"status": "NOT_RUN"},
                "historical_prequential": {"status": "NOT_RUN"},
                "robust_analysis": robust_analysis,
                "calibrated_probability_available": False,
                "not_trading_edge": True,
                "errors": errors,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "status": "DIRECT_MODELS_UNAVAILABLE",
            "direct_model_available": False,
            "data": meta,
            "robust_analysis": robust_analysis,
            "model_availability": model_availability,
            "errors": errors,
        }

    def avg(field: str) -> float | None:
        vals = [float(m[field]) for m in models if m.get(field) is not None]
        return sum(vals) / len(vals) if vals else None

    ensemble_mode = (
        "MULTI_MODEL_AVAILABLE_ENSEMBLE"
        if len(models) >= 2
        else "SINGLE_MODEL_DEGRADED"
    )
    ensemble = {
        "p10": avg("p10"),
        "p50": avg("p50"),
        "p90": avg("p90"),
        "expected_return": avg("expected_return"),
        "method": "equal_weight_available_price_models",
        "ensemble_mode": ensemble_mode,
        "available_model_count": len(models),
        "available_models": [str(m.get("model")) for m in models],
    }
    stance = _stance(ensemble["expected_return"])
    historical_validation = (
        validate_jnu_direct_history(str(meta["contract_month"]), horizon_steps=steps)
        if validate_history
        else {"status": "NOT_RUN"}
    )
    if validate_history:
        try:
            from market_ai_hub.research.historical_prequential import (
                compact_evidence_summary,
                load_sealed_evidence,
            )

            historical_prequential = compact_evidence_summary(load_sealed_evidence())
        except Exception as exc:
            historical_prequential = {
                "status": "UNAVAILABLE",
                "reason": type(exc).__name__,
            }
    else:
        historical_prequential = {"status": "NOT_RUN"}
    validation_overall = historical_validation.get("overall")
    if validation_overall == "HISTORICAL_VALIDATED":
        stance_strength = "HISTORICAL_VALIDATED_ONLY"
    elif validation_overall == "HISTORICAL_EXPERIMENTAL":
        stance_strength = "EXPERIMENTAL_HISTORICAL"
    else:
        stance_strength = "WEAK_UNVALIDATED"
    return {
        "status": "OK",
        "direct_model_available": True,
        "scope": DIRECT_MODEL_SCOPE,
        "target": "OSE_NIKKEI225_MICRO_FUTURES",
        "product_name": "大阪日經225微型期貨（JNU）",
        "contract_month": meta["contract_month"],
        "quote_code": meta["quote_code"],
        "forecast_price_type": "NEXT_PUBLISHED_SETTLEMENT_OBSERVATION",
        "horizon": horizon,
        "target_dates": target_dates,
        "data": meta,
        "models": models,
        "model_availability": model_availability,
        "ensemble": ensemble,
        "research_stance": stance,
        "research_stance_strength": stance_strength,
        "historical_validation": historical_validation,
        "historical_prequential": historical_prequential,
        "robust_analysis": robust_analysis,
        "calibrated_probability_available": False,
        "not_trading_edge": True,
        "errors": errors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def jnu_user_summary(result: dict[str, Any], *, calibration_status: dict[str, Any] | None = None) -> dict[str, Any]:
    """Small Chinese presentation object for normal users; no internal enum dumping."""
    if result.get("status") != "OK":
        reason = {
            "NO_DIRECT_HISTORY": "目前還沒有足夠的大阪微型日經官方歷史資料。",
            "CONTRACT_HISTORY_NOT_AVAILABLE": "目前找不到這個限月的官方歷史資料。",
            "INSUFFICIENT_DIRECT_HISTORY": "官方歷史資料已開始累積，但樣本還不足以啟動直接價格模型。",
            "ROLL_BOUNDARY_BLOCKED": "預測期間跨過合約到期／換月，系統先停止直接預測，避免把不同合約混在一起。",
        }.get(result.get("status"), "目前直接價格模型暫時無法使用。")
        return {
            "商品": "大阪日經225微型期貨（JNU）",
            "直接模型狀態": reason,
            "資料來源說明": "直接資料是大阪微型日經本身的官方限月清算價；日經225現貨只作輔助參考。",
        }

    data = result["data"]
    ens = result["ensemble"]
    stance_text = {
        "BULLISH_LEAN": "偏多",
        "BEARISH_LEAN": "偏空",
        "NEUTRAL": "中性",
        "INSUFFICIENT_EVIDENCE": "證據不足",
    }.get(result.get("research_stance"), "證據不足")
    historical = result.get("historical_validation") or {}
    prequential = result.get("historical_prequential") or {}
    preq_ensemble = prequential.get("ensemble") or {}
    preq_final = (preq_ensemble.get("partitions") or {}).get("HISTORICAL_FINAL_HOLDOUT") or {}
    preq_all = preq_ensemble.get("all") or {}
    paired_rows = [
        row.get("paired_vs_last_price_naive") or {}
        for row in (historical.get("models") or {}).values()
        if row.get("paired_vs_last_price_naive")
    ]
    comparison_note = "目前尚沒有足夠的同一批歷史預測樣本，不能可靠判斷模型相對簡單基準的穩定差異。"
    preq_blocked = prequential.get("status", "").startswith("BLOCKED")
    if preq_blocked:
        comparison_note = "歷史重播包含與預測交易日期不一致的樣本，已停止引用該批績效，等待新規格重新驗證。"
    elif prequential.get("status") == "OK" and preq_final.get("n"):
        final_pair = preq_final.get("paired_vs_last_price_naive") or {}
        final_eval = preq_final.get("evaluation") or {}
        final_model = final_eval.get("model") or {}
        all_pair = preq_all.get("paired_vs_last_price_naive") or {}
        final_n = int(preq_final.get("n", 0) or 0)
        total_n = int(prequential.get("origin_count", 0) or 0)
        lo = final_pair.get("delta_ci_lower")
        hi = final_pair.get("delta_ci_upper")
        crosses_zero = lo is None or hi is None or float(lo) <= 0.0 <= float(hi)
        pooled_lo = all_pair.get("delta_ci_lower")
        pooled_warning = pooled_lo is not None and float(pooled_lo) > 0
        comparison_note = (
            f"已完成 {total_n} 筆逐日歷史重播，其中預先留出的最終區段有 {final_n} 筆；"
            f"等權價格模型在最終區段的 MASE 約 {float(final_model.get('mase', float('nan'))):.2f}。"
            + (
                "模型與簡單基準的誤差差異區間仍包含「沒有差異」，尚未證明穩定優勢。"
                if crosses_zero
                else "模型與簡單基準的誤差差異區間已不含零，但仍只屬歷史重播證據。"
            )
            + (
                "把全部歷史樣本池化後，平均誤差偏高是一項風險警訊。"
                if pooled_warning else ""
            )
            + "模型訓練資料截止日目前無法確認，因此這不是乾淨的訓練期外 OOS，也不是真實前向證據。"
        )
    elif paired_rows:
        paired_n = min(int(row.get("common_origin_count", 0) or 0) for row in paired_rows)
        states = {str(row.get("uncertainty_status") or "") for row in paired_rows}
        if "INSUFFICIENT_PAIRED_SAMPLE" in states:
            comparison_note = (
                f"目前只有 {paired_n} 個同一批歷史預測樣本，樣本太少，"
                "不能可靠判斷模型是否穩定優於簡單基準。"
            )
        elif "EXPLORATORY_ONLY" in states:
            comparison_note = (
                f"目前有 {paired_n} 個同一批歷史預測樣本，模型與簡單基準的誤差差異仍屬探索性；"
                "不能把目前的平均誤差勝負當成穩定預測優勢。"
            )
        else:
            crosses_zero = any(
                row.get("delta_ci_lower") is None
                or row.get("delta_ci_upper") is None
                or float(row["delta_ci_lower"]) <= 0.0 <= float(row["delta_ci_upper"])
                for row in paired_rows
            )
            comparison_note = (
                f"目前有 {paired_n} 個同一批歷史預測樣本；"
                + (
                    "模型與簡單基準的誤差差異區間仍包含「沒有差異」，尚不能確認穩定優勢。"
                    if crosses_zero
                    else "模型與簡單基準的誤差差異已較穩定，但這仍只是歷史樣本，不是前向交易優勢。"
                )
            )
    preq_low_confidence = bool(
        prequential.get("status") == "OK"
        and preq_final.get("n")
        and not (preq_final.get("evaluation") or {}).get("beats_naive_mae", False)
    )
    if preq_blocked:
        validation_note = "歷史證據的預測期間檢查未通過；目前只提供未驗證的研究價格參考。"
        action_note = "先修正資料與交易日對齊，使用新預先登記的評估區段；不重開已使用的最終留出樣本。"
    elif preq_low_confidence:
        validation_note = (
            "較大規模的逐日歷史重播已完成；預先留出的最終區段中，現行等權價格模型平均誤差"
            "沒有優於直接沿用前一日價格的簡單基準，而且差異區間仍包含沒有差異。"
            "因此目前只能視為低信心研究參考。"
        )
        action_note = (
            "目前不把單日模型方向單獨當主要依據；優先等待更多真正前向樣本，"
            "以及可驗證的模型訓練截止日，再判斷是否存在可重複的預測優勢。"
        )
    elif historical.get("status") == "OK" and not historical.get("any_model_beats_last_price_naive", False):
        validation_note = (
            "近期的歷史回看中，就目前平均絕對誤差而言，兩個價格模型都沒有優於"
            "「直接沿用前一日價格」的簡單基準；但共同樣本仍少，這不代表已證明模型穩定較差。"
            "因此這次價格預測只能當低信心研究參考，不能單獨當成成熟方向訊號。"
        )
        action_note = (
            "目前以最新官方價格與模型範圍作觀察，不把單日模型方向單獨當主要依據；"
            "若後續即時／收盤資料與其他市場證據同向，再提高該情境優先級；反向時就重新分析。"
        )
    else:
        validation_note = "直接價格模型仍屬研究用途，必須持續接受歷史與真實前向驗證。"
        action_note = (
            "以直接模型方向作研究參考；若最新盤中／收盤資料與其他市場證據同向，可提高該情境優先級；"
            "若反向，先撤銷原研究假設並重新分析。"
        )

    settled_samples = int((calibration_status or {}).get("settled_samples", 0) or 0)
    probability_note = (
        f"目前已有 {settled_samples} 筆合格的真實前向機率樣本；樣本還不足，所以不能提供可靠的校準機率。"
        "依目前驗證規則，至少要依時間累積 50 筆校準、50 筆驗證、50 筆最終留出樣本，"
        "而且三階段都通過才可公開機率；滿 150 筆也不代表一定通過。"
    )
    if calibration_status and calibration_status.get("public_calibrated"):
        probability_note = "已有通過獨立驗證的校準機率，可使用系統正式機率輸出。"

    robust = result.get("robust_analysis") or {}
    robust_interval = robust.get("empirical_interval") or {}
    robust_vol = robust.get("volatility") or {}
    quantile = robust.get("lightgbm_quantile_challenger") or {}
    q_prices = quantile.get("price_quantiles") or {}
    robust_summary = {
        "基準價格": (
            f"{float((robust.get('point_reference') or {}).get('price')):,.0f} 點"
            if (robust.get("point_reference") or {}).get("price") is not None
            else "目前無法提供"
        ),
        "EWMA日報酬波動": (
            f"{float(robust_vol.get('ewma_return_volatility')) * 100:.2f}%"
            if robust_vol.get("ewma_return_volatility") is not None else "目前無法提供"
        ),
        "波動狀態": {
            "LOW_VOLATILITY": "相對低波動",
            "HIGH_VOLATILITY": "相對高波動",
        }.get(str(robust_vol.get("regime")), "未知"),
        "開發期經驗區間": (
            f"{float(robust_interval.get('lower_price')):,.0f} ～ "
            f"{float(robust_interval.get('upper_price')):,.0f} 點"
            if robust_interval.get("lower_price") is not None and robust_interval.get("upper_price") is not None
            else "目前無法提供"
        ),
        "固定LightGBM分位挑戰模型": (
            f"{float(q_prices.get('q10')):,.0f} / {float(q_prices.get('q50')):,.0f} / {float(q_prices.get('q90')):,.0f} 點"
            if all(q_prices.get(k) is not None for k in ("q10", "q50", "q90"))
            else "未通過可用性檢查或資料不足"
        ),
        "證據限制": (
            "這些波動與區間只使用開發期規則與目前已知資料；"
            "沒有新的真實前向結果時，不升級為預測增益、校準機率或交易優勢。"
        ),
    }

    return {
        "商品": "大阪日經225微型期貨（JNU）",
        "目前合約": data["contract_month"],
        "最新官方資料": f"{data['latest_date']} 清算價 {data['latest_settlement']:,.0f} 點",
        "預測目標": "下一筆官方發布的清算價觀測（不一定等於下一個 OSE 假日交易時段）",
        "直接價格模型": {
            "綜合預測": f"{ens['p50']:,.0f} 點" if ens.get("p50") is not None else "目前無法提供",
            "研究方向": stance_text,
            "預測變動": f"{ens['expected_return'] * 100:+.2f}%" if ens.get("expected_return") is not None else "目前無法提供",
            "終端清算價統計參考範圍": (
                f"{ens['p10']:,.0f} ～ {ens['p90']:,.0f} 點"
                if ens.get("p10") is not None and ens.get("p90") is not None else "目前無法提供"
            ),
            "範圍語義": "這是預測 horizon 最後一步的清算價統計區間，不是盤中最高／最低、支撐壓力或觸價機率。",
            "可信度": "低信心研究參考" if preq_blocked or preq_low_confidence or (
                historical.get("status") == "OK" and not historical.get("any_model_beats_last_price_naive", False)
            )
            else "研究用、尚未完成前向驗證",
        },
        "模型組成": (
            (
                f"多模型可用：{', '.join(str(x) for x in ens.get('available_models', []))}；"
                "目前只是研究用等權組合，不代表模型共識已被驗證。"
            )
            if ens.get("ensemble_mode") == "MULTI_MODEL_AVAILABLE_ENSEMBLE"
            else (
                f"單模型可用：{', '.join(str(x) for x in ens.get('available_models', []))}；"
                "ensemble 已降級，這不是多模型一致預測。"
            )
            if ens.get("ensemble_mode") == "SINGLE_MODEL_DEGRADED"
            else "目前沒有可用 foundation price model，使用 baseline fallback。"
        ),
        "無新前向資料時的穩健分析": robust_summary,
        "歷史驗證": validation_note,
        "模型比較可信度": comparison_note,
        "資料說明": (
            f"模型使用大阪微型日經 {data['contract_month']} 限月本身的官方清算價歷史，"
            "不是用日經225現貨指數冒充微型期貨。"
        ),
        "輔助資料": "日經225現貨指數與其他市場資料只用來補充市場環境，不當成微型期貨本身的價格。",
        "機率狀態": probability_note,
        "操作參考": action_note,
    }
