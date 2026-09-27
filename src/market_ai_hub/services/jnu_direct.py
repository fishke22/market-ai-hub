"""Direct Osaka Nikkei 225 Micro settlement research path.

Uses official JPX/OSE Micro contract settlements only. The forecast target is the
next-session settlement for the current exact contract, not an intraday trade price.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_ai_hub.automation.data_lake import default_data_root
from market_ai_hub.services.calendar import next_ose_derivatives_sessions
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
    required = DIRECT_VALIDATION_HISTORY_LEN + DIRECT_VALIDATION_ORIGINS + 2
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
    for name, factory in (("chronos-2", get_chronos), ("timesfm-3.0", get_timesfm)):
        cached = None if force else store.latest(name, symbol)
        result = (cached or {}).get("result") if cached else None
        current = bool(
            result
            and result.get("validation_schema_version") == TS_VALIDATION_SCHEMA_VERSION
            and result.get("window", {}).get("end") == meta["latest_date"]
            and int(result.get("history_len", 0)) == DIRECT_VALIDATION_HISTORY_LEN
            and int(result.get("n_origins", 0)) == DIRECT_VALIDATION_ORIGINS
        )
        if not current:
            result = run_ts_oos_validation(
                factory(),
                name,
                symbol,
                series,
                n_origins=DIRECT_VALIDATION_ORIGINS,
                history_len=DIRECT_VALIDATION_HISTORY_LEN,
            )
            status, reasons = determine_validation_status(result)
            if result.get("status") == "OK":
                store.save(result, status, run_kind="RUNTIME_VALIDATION")
        else:
            status, reasons = determine_validation_status(result)

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
        frames.append(df[["contract_month", "date", "settlement", "source_url", "source_hash", "_priority"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_direct_micro_settlements(contract_month: str = "") -> tuple[pd.Series, dict[str, Any]]:
    """Load an exact-contract settlement series from persisted official JPX sources."""
    daily = JPXOSEDailyReportProvider().load("Nikkei 225 Micro")
    frames = []
    if daily is not None and not daily.empty:
        d = daily.copy()
        d["date"] = d["date"].map(_date_text)
        d["settlement"] = pd.to_numeric(d["settlement"], errors="coerce")
        d["_priority"] = 1
        keep = ["contract_month", "date", "settlement", "source_url", "source_hash", "_priority"]
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
    df = df[df["settlement"] > 0]
    df = df.sort_values(["date", "_priority"]).drop_duplicates(
        subset=["date", "contract_month"], keep="last"
    )
    latest_date = str(df["date"].max())
    latest = df[df["date"].eq(latest_date)]
    if not contract_month:
        valid = sorted(c for c in latest["contract_month"].unique() if len(c) == 6 and c.isdigit())
        contract_month = valid[0] if valid else ""
    exact = df[df["contract_month"].eq(str(contract_month))].copy()
    exact = exact.sort_values("date")
    if exact.empty:
        return pd.Series(dtype=float), {
            "status": "CONTRACT_HISTORY_NOT_AVAILABLE",
            "contract_month": contract_month,
            "latest_official_date": latest_date,
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
        "contract_month": str(contract_month),
        "quote_code": f"JNU{str(contract_month)[2:]}" if len(str(contract_month)) == 6 else "JNU",
        "sample_count": int(len(series)),
        "first_date": str(exact["date"].iloc[0]),
        "latest_date": str(exact["date"].iloc[-1]),
        "latest_settlement": float(series.iloc[-1]),
        "source": "JPX/OSE 官方每日報告與清算價",
        "series_semantics": "EXACT_CONTRACT",
        "price_semantics": "SETTLEMENT",
    }
    return series, meta


def _model_result(adapter, name: str, series: pd.Series, steps: int, target_dates: list[str]) -> dict:
    raw = adapter.predict(series, horizon=steps)
    path = raw.get("path") or {}
    p10 = list(path.get("p10") or [])
    p50 = list(path.get("p50") or [])
    p90 = list(path.get("p90") or [])
    if len(p50) < steps or not p50:
        raise ValueError("model returned incomplete path")
    last = float(series.iloc[-1])
    terminal = float(p50[-1])
    return {
        "model": name,
        "p10": float(p10[-1]) if len(p10) >= steps else None,
        "p50": terminal,
        "p90": float(p90[-1]) if len(p90) >= steps else None,
        "expected_return": (terminal - last) / last if last else 0.0,
        "target_dates": list(target_dates),
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
    target_dates = next_ose_derivatives_sessions(meta["latest_date"], steps)
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
    for name, factory in (("Chronos-2", get_chronos), ("TimesFM-3.0", get_timesfm)):
        try:
            models.append(_model_result(factory(), name, series, steps, target_dates))
        except Exception as exc:
            errors.append(f"{name}:{type(exc).__name__}")
    if not models:
        return {
            "status": "DIRECT_MODELS_UNAVAILABLE",
            "direct_model_available": False,
            "data": meta,
            "errors": errors,
        }

    def avg(field: str) -> float | None:
        vals = [float(m[field]) for m in models if m.get(field) is not None]
        return sum(vals) / len(vals) if vals else None

    ensemble = {
        "p10": avg("p10"),
        "p50": avg("p50"),
        "p90": avg("p90"),
        "expected_return": avg("expected_return"),
        "method": "equal_weight_available_price_models",
    }
    stance = _stance(ensemble["expected_return"])
    historical_validation = (
        validate_jnu_direct_history(str(meta["contract_month"]))
        if validate_history
        else {"status": "NOT_RUN"}
    )
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
        "forecast_price_type": "NEXT_SESSION_SETTLEMENT",
        "horizon": horizon,
        "target_dates": target_dates,
        "data": meta,
        "models": models,
        "ensemble": ensemble,
        "research_stance": stance,
        "research_stance_strength": stance_strength,
        "historical_validation": historical_validation,
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
    paired_rows = [
        row.get("paired_vs_last_price_naive") or {}
        for row in (historical.get("models") or {}).values()
        if row.get("paired_vs_last_price_naive")
    ]
    comparison_note = "目前尚沒有足夠的同一批歷史預測樣本，不能可靠判斷模型相對簡單基準的穩定差異。"
    if paired_rows:
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
    if historical.get("status") == "OK" and not historical.get("any_model_beats_last_price_naive", False):
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

    return {
        "商品": "大阪日經225微型期貨（JNU）",
        "目前合約": data["contract_month"],
        "最新官方資料": f"{data['latest_date']} 清算價 {data['latest_settlement']:,.0f} 點",
        "預測目標": "下一交易日的官方清算價",
        "直接價格模型": {
            "綜合預測": f"{ens['p50']:,.0f} 點" if ens.get("p50") is not None else "目前無法提供",
            "研究方向": stance_text,
            "預測變動": f"{ens['expected_return'] * 100:+.2f}%" if ens.get("expected_return") is not None else "目前無法提供",
            "參考範圍": (
                f"{ens['p10']:,.0f} ～ {ens['p90']:,.0f} 點"
                if ens.get("p10") is not None and ens.get("p90") is not None else "目前無法提供"
            ),
            "可信度": "低信心研究參考" if historical.get("status") == "OK" and not historical.get("any_model_beats_last_price_naive", False)
            else "研究用、尚未完成前向驗證",
        },
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
