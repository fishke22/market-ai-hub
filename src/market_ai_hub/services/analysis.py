"""Analysis service：analyze_osaka_nikkei / analyze_taiwan_stock（V1.1）。

Wrapper 語義：
- role = ANALYSIS_WRAPPER（不是第 6 個 independent model）
- used_market_data / used_base_models / used_ensemble / cross_asset_inputs / rule_inputs
- analysis_direction = integrated_market_view（非「模型投票結果」）
- count semantics：independent_base_model_count / eligible_direction_vote_count /
  eligible_price_reference_count（獨立存在數 ≠ 可投票數）
- V1.1 target calendar：requested_dates 可指定 OSE 窗口；
  ^N225 依 TSE（XTKS）日曆交易，OSE futures 有 Holiday Trading →
  窗口與 target 日曆不一致時標 CALENDAR_TARGET_MISMATCH，絕不錯誤映射日期。
- confidence_inputs：data_quality / data_freshness / oos_validation_status /
  baseline_outperformance / interval_calibration / regime_performance /
  model_disagreement / sample_size
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from market_ai_hub.config.settings import load_symbols
from market_ai_hub.ensemble.ensemble import ensemble_equal_weight, independent_vote_summary
from market_ai_hub.models.baseline_ml import BaselineClassifier, baseline_forecast
from market_ai_hub.models.chronos_model import chronos_forecast
from market_ai_hub.models.timesfm_model import timesfm_forecast
from market_ai_hub.providers.finmind import FinMindProvider
from market_ai_hub.providers.twse import TWSEProvider
from market_ai_hub.providers.yfinance_provider import YFinanceProvider
from market_ai_hub.schemas.market_data import ModelRole
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.horizon import HorizonUnsupportedError, parse_horizon
from market_ai_hub.services.model_runtime import get_chronos, get_timesfm

log = logging.getLogger(__name__)

RULE_INPUTS = [
    "flat_threshold=0.005 作用於 k-bar 累積報酬（classification label）",
    "analysis_direction = price ensemble direction（integrated_market_view，非模型投票）",
    "獨立方向票只算 eligible_for_direction_vote 的 base models（independent_direction_votes）",
    "跨市場資產僅供 context，不進 ensemble",
    "PRICE_FORECAST 模型提供價格路徑；DIRECTION_CLASSIFICATION 模型只提供方向與類別機率",
]


def _daily_closes(df: pd.DataFrame) -> pd.Series:
    """回傳 DatetimeIndex 的 close 序列（forecast 日期必須從 index 取真實交易日）。"""
    return df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna()


def _horizon_steps_or_none(horizon: str, data_frequency: str = "1d") -> int | None:
    spec = parse_horizon(horizon, data_frequency)
    return spec.effective_horizon_steps if spec.supported else None


def _confidence_inputs(
    target_df: pd.DataFrame,
    models: list,
    horizon: str,
) -> dict:
    """Phase 12：研究信心 inputs（metadata，不是打包保證）。"""
    last_ts = pd.Timestamp(target_df["timestamp_utc"].max())
    age = (datetime.now(timezone.utc) - last_ts.tz_localize("UTC") if last_ts.tzinfo is None else datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
    oos_statuses = {f.model: f.predictive_validation_status for f in models}
    disagreement = "N/A"
    price_models = [f for f in models if f.model_task == "PRICE_FORECAST"]
    if price_models:
        dirs = [f.direction for f in price_models]
        top = max(set(dirs), key=dirs.count)
        ratio = dirs.count(top) / len(dirs)
        disagreement = "LOW" if ratio >= 0.75 else ("MEDIUM" if ratio >= 0.5 else "HIGH")
    return {
        "data_quality": target_df["data_grade"].iloc[0] if "data_grade" in target_df else "UNKNOWN",
        "data_freshness_hours": round(age, 1),
        "sample_size": int(len(target_df)),
        "oos_validation_status": oos_statuses,
        "baseline_outperformance": None,
        "interval_calibration": None,
        "regime_performance": "NOT_AVAILABLE",
        "model_disagreement": disagreement,
        "horizon": horizon,
    }


def _cross_market_entry(symbol: str, value: float, return_1d: float,
                        event_timestamp, received_at) -> dict:
    """Typed factor representation entry (V2-A.2). Keeps last/return_1d for compatibility."""
    from market_ai_hub.research.v2.factor_representation import build_cross_market_entry

    return build_cross_market_entry(
        symbol, value=value, return_1d=return_1d, event_timestamp=event_timestamp,
        asof=received_at, received_at=received_at,
        provider="yfinance", source_frequency="DAILY", data_grade="RESEARCH_PROXY",
        timestamp_precision="SESSION_DATE_ONLY", point_in_time_safe=False,
    )


def analyze_osaka_nikkei(horizon: str = "1d", requested_dates: str = "") -> dict:
    """大阪日經：PROXY 骨架（^N225 + 跨市場），非 OSE micro 即時模型。

    requested_dates（可選）："YYYY-MM-DD..YYYY-MM-DD" 或單一日期，表示使用者想要的研究窗口
    （例如 OSE 交易日窗口）。^N225 依 TSE 日曆交易，OSE futures 有 Holiday Trading；
    若窗口含 TSE 休市日（但 OSE 可能交易）→ CALENDAR_TARGET_MISMATCH，明確標示，
    不把 ^N225 bars 錯誤映射成 OSE sessions。
    """
    yf = YFinanceProvider()
    symbols = [s["symbol"] for s in load_symbols() if s["provider"] == "yfinance"]
    data: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []
    for sym in symbols:
        try:
            data[sym] = yf.fetch(sym, period="1y", interval="1d")
        except Exception as e:
            warnings.append(f"{sym}: {e}")

    target_sym = "^N225"
    if target_sym not in data:
        return {
            "status": "PROXY_DATA_UNAVAILABLE",
            "role": ModelRole.ANALYSIS_WRAPPER.value,
            "data_grade": "RESEARCH_PROXY",
            "message": "yfinance ^N225 取得失敗（此為 Nikkei 225 INDEX proxy，非 OSE micro futures）",
            "warnings": warnings,
            **build_fingerprint(),
        }

    closes = _daily_closes(data[target_sym])
    steps = _horizon_steps_or_none(horizon)
    if steps is None:
        return {
            "status": "UNSUPPORTED_WITH_CURRENT_DATA",
            "role": ModelRole.ANALYSIS_WRAPPER.value,
            "symbol": target_sym,
            "horizon": horizon,
            "data_frequency": "1d",
            "message": "日線資料不支援日內 horizon；不能把日線假造成分 K",
            **build_fingerprint(),
        }

    # ── V1.2 temporal anchor + target calendar ──
    from market_ai_hub.services.calendar import forecast_anchor, is_session

    anchor = forecast_anchor(target_sym, closes.index[-1], steps)
    target_dates = anchor["forecast_target_dates"]
    calendar_result: dict = {
        "target_calendar": anchor["target_calendar"],
        "proxy_target_calendar": anchor["target_calendar"],
        "calendar_name": anchor["calendar_name"],
        "calendar_source": anchor["calendar_source"],
        "calendar_verified": anchor["calendar_verified"],
        "calendar_grade": anchor["calendar_grade"],
        "target_trading_dates": target_dates,
        "forecast_target_dates": target_dates,
        "calendar_mismatch": False,
        "requested_window": requested_dates or "",
        "requested_calendar_window": requested_dates or "",
        "requested_market_sessions": "",
        "unmapped_sessions": [],
        "mismatch_detail": "",
    }
    if requested_dates:
        window = _parse_window(requested_dates)
        if window:
            calendar_result["requested_calendar_window"] = requested_dates
            calendar_result["requested_market_sessions"] = "USER_WINDOW"
            non_trading = [d for d in window if not is_session(target_sym, d)]
            if non_trading:
                calendar_result["calendar_mismatch"] = True
                calendar_result["unmapped_sessions"] = non_trading
                calendar_result["mismatch_detail"] = (
                    f"CALENDAR_TARGET_MISMATCH: 請求窗口 {requested_dates} 含 {len(non_trading)} 個 TSE 休市日 "
                    f"{non_trading}。^N225 預測是未來 {steps} 根 TSE 現貨交易 bars，不是這些日期的逐日預測；"
                    "OSE futures 可能於 TSE 休市日 Holiday Trading，本系統無免費 OSE session 日曆，不做日期映射。"
                )
                warnings.append(calendar_result["mismatch_detail"])

    results: dict = {
        "symbol": target_sym,
        "horizon": horizon,
        "role": ModelRole.ANALYSIS_WRAPPER.value,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "forecast_origin": anchor["forecast_origin"],
        "last_observed_trading_date": anchor["last_observed_trading_date"],
        "forecast_target_dates": target_dates,
        "exchange_timezone": anchor["exchange_timezone"],
        "target_calendar": calendar_result["target_calendar"],
        "proxy_target_calendar": calendar_result["proxy_target_calendar"],
        "target_trading_dates": calendar_result["target_trading_dates"],
        "requested_calendar_window": calendar_result["requested_calendar_window"],
        "requested_market_sessions": calendar_result["requested_market_sessions"],
        "calendar_grade": calendar_result["calendar_grade"],
        "calendar_verified": calendar_result["calendar_verified"],
        "calendar_mismatch": calendar_result["calendar_mismatch"],
        "unmapped_sessions": calendar_result["unmapped_sessions"],
        "mismatch_detail": calendar_result["mismatch_detail"],
    }
    models: list = []

    def _run_base(key: str, fn):
        try:
            fo = fn()
            results[key] = fo.model_dump()
            models.append(fo)
        except Exception as e:
            log.warning("%s failed in osaka analysis: %s", key, e)
            results[key] = {"status": "unavailable", "error": str(e)}
            warnings.append(f"{key}: {e}")

    _run_base("chronos", lambda: chronos_forecast(get_chronos(), target_sym, closes, horizon=horizon, horizon_steps=steps))
    _run_base("timesfm", lambda: timesfm_forecast(get_timesfm(), target_sym, closes, horizon=horizon, horizon_steps=steps))

    from market_ai_hub.features.features import build_features

    feat = build_features(data[target_sym])
    for name in ("xgb", "lgbm"):
        _run_base(name, lambda n=name: baseline_forecast(BaselineClassifier(n), target_sym, feat, horizon=horizon))

    if models:
        ens = ensemble_equal_weight(models, target_sym, horizon)
        results["ensemble"] = ens.model_dump()
        results["ensemble_result"] = ens.model_dump()
        mm = ens.model_metadata
        price_ens = mm.get("price_ensemble", {})
        results["price_forecast_ensemble"] = price_ens
        results["direction_classification_ensemble"] = mm.get("direction_ensemble", {})
        # V1.2 direction resolution（fixed rule，見 ensemble._resolve_direction）
        results["final_direction"] = mm.get("final_direction", "no_evidence")
        results["direction_resolution_method"] = mm.get("direction_resolution_method", "no_evidence")
        results["direction_disagreement"] = mm.get("direction_disagreement", False)
        results["vote_direction"] = mm.get("vote_direction", "N/A")
        results["probability_argmax_direction"] = mm.get("probability_argmax_direction", "N/A")
        results["analysis_direction"] = mm.get("final_direction", ens.direction)
        results["integrated_market_view"] = mm.get("final_direction", ens.direction)
        results["ensemble_validation_level"] = mm.get("validation_level", "RESEARCH")
    else:
        results["ensemble"] = {"status": "NO_MODELS_AVAILABLE"}
        results["analysis_direction"] = "no_evidence"

    vote = independent_vote_summary(models)
    results.update(vote)

    cross = {}
    received_at = datetime.now(timezone.utc)
    for sym, df in data.items():
        if sym != target_sym and len(df) > 2:
            c = _daily_closes(df)
            last_ts = c.index[-1]
            ts = last_ts.to_pydatetime() if hasattr(last_ts, "to_pydatetime") else last_ts
            cross[sym] = _cross_market_entry(sym, float(c.iloc[-1]), float(c.pct_change().iloc[-1]),
                                             ts, received_at)
    results["cross_market"] = cross

    results["used_market_data"] = list(data.keys())
    results["used_base_models"] = [f.model for f in models]
    results["used_ensemble"] = bool(models)
    results["cross_asset_inputs"] = [s for s in data if s != target_sym]
    results["rule_inputs"] = RULE_INPUTS
    results["confidence_inputs"] = _confidence_inputs(data[target_sym], models, horizon)
    results["status"] = "OK"
    results["data_grade"] = "RESEARCH_PROXY"
    results["disclaimer"] = (
        "^N225 為 Nikkei 225 INDEX 代理資料（RESEARCH_PROXY/DELAYED），"
        "非 OSE Nikkei 225 micro futures 即時行情。無 free exchange-grade OSE micro 資料源。"
    )
    results["warnings"] = warnings
    results.update(build_fingerprint())
    return results


def _parse_window(requested_dates: str) -> list[str]:
    """解析 "YYYY-MM-DD..YYYY-MM-DD" 或 "YYYY-MM-DD" → 日期字串 list。"""
    import re

    s = requested_dates.strip()
    if ".." in s:
        a, b = s.split("..", 1)
        try:
            start = pd.Timestamp(a.strip())
            end = pd.Timestamp(b.strip())
        except ValueError:
            return []
        if start > end:
            return []
        days = pd.date_range(start, end, freq="D")
        return [d.strftime("%Y-%m-%d") for d in days]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            pd.Timestamp(s)
            return [s]
        except ValueError:
            return []
    return []


def analyze_taiwan_stock(stock: str, horizon: str = "1d") -> dict:
    """台股分析：優先 FinMind（OFFICIAL_DAILY），fallback TWSE OpenAPI，再 fallback yfinance。"""
    warnings: list[str] = []
    df: pd.DataFrame | None = None
    provider_name = ""
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=730)).strftime("%Y-%m-%d")

    # 容忍 yfinance 風格後綴（3706.TW → TWSE/FinMind 用 3706）
    lookup_code = stock.split(".")[0] if stock.upper().endswith(".TW") else stock

    fm = FinMindProvider()
    if fm.status().status.value in ("ok", "needs_config"):
        try:
            df = fm.fetch_price(lookup_code, start, end)
            provider_name = "finmind"
        except Exception as e:
            warnings.append(f"finmind: {e}")

    if df is None:
        twse = TWSEProvider()
        try:
            twse_start = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y%m%d")
            df = twse.fetch_symbol_daily(lookup_code, twse_start, end.replace("-", ""))
            provider_name = "twse"
        except Exception as e:
            warnings.append(f"twse: {e}")

    if df is None or df.empty:
        return {
            "status": "DATA_UNAVAILABLE",
            "role": ModelRole.ANALYSIS_WRAPPER.value,
            "symbol": stock,
            "warnings": warnings,
            "message": "FinMind 與 TWSE 皆無法取得資料（FinMind 需要 FINMIND_TOKEN）",
            **build_fingerprint(),
        }

    closes = _daily_closes(df)
    steps = _horizon_steps_or_none(horizon)
    if steps is None:
        return {
            "status": "UNSUPPORTED_WITH_CURRENT_DATA",
            "role": ModelRole.ANALYSIS_WRAPPER.value,
            "symbol": stock,
            "horizon": horizon,
            "data_frequency": "1d",
            "message": "日線資料不支援日內 horizon；不能把日線假造成分 K",
            **build_fingerprint(),
        }

    from market_ai_hub.services.calendar import forecast_anchor

    anchor = forecast_anchor(stock, closes.index[-1], steps)
    results: dict = {
        "symbol": stock,
        "provider": provider_name,
        "horizon": horizon,
        "role": ModelRole.ANALYSIS_WRAPPER.value,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "forecast_origin": anchor["forecast_origin"],
        "last_observed_trading_date": anchor["last_observed_trading_date"],
        "forecast_target_dates": anchor["forecast_target_dates"],
        "exchange_timezone": anchor["exchange_timezone"],
        "target_calendar": anchor["target_calendar"],
        "calendar_name": anchor["calendar_name"],
        "calendar_source": anchor["calendar_source"],
        "calendar_verified": anchor["calendar_verified"],
        "calendar_grade": anchor["calendar_grade"],
    }
    models: list = []

    def _run_base(key: str, fn):
        try:
            fo = fn()
            results[key] = fo.model_dump()
            models.append(fo)
        except Exception as e:
            results[key] = {"status": "unavailable", "error": str(e)}
            warnings.append(f"{key}: {e}")

    _run_base("chronos", lambda: chronos_forecast(get_chronos(), stock, closes, horizon=horizon, horizon_steps=steps, data_grade="OFFICIAL_DAILY"))
    _run_base("timesfm", lambda: timesfm_forecast(get_timesfm(), stock, closes, horizon=horizon, horizon_steps=steps, data_grade="OFFICIAL_DAILY"))

    from market_ai_hub.features.features import build_features

    feat = build_features(df)
    for name in ("xgb", "lgbm"):
        _run_base(name, lambda n=name: baseline_forecast(BaselineClassifier(n), stock, feat, horizon=horizon, data_grade="OFFICIAL_DAILY"))

    if models:
        ens = ensemble_equal_weight(models, stock, horizon)
        results["ensemble"] = ens.model_dump()
        results["ensemble_result"] = ens.model_dump()
        mm = ens.model_metadata
        results["price_forecast_ensemble"] = mm.get("price_ensemble", {})
        results["direction_classification_ensemble"] = mm.get("direction_ensemble", {})
        results["final_direction"] = mm.get("final_direction", "no_evidence")
        results["direction_resolution_method"] = mm.get("direction_resolution_method", "no_evidence")
        results["direction_disagreement"] = mm.get("direction_disagreement", False)
        results["vote_direction"] = mm.get("vote_direction", "N/A")
        results["probability_argmax_direction"] = mm.get("probability_argmax_direction", "N/A")
        results["analysis_direction"] = mm.get("final_direction", ens.direction)
        results["integrated_market_view"] = mm.get("final_direction", ens.direction)
        results["ensemble_validation_level"] = mm.get("validation_level", "RESEARCH")
    else:
        results["ensemble"] = {"status": "NO_MODELS_AVAILABLE"}
        results["analysis_direction"] = "no_evidence"

    vote = independent_vote_summary(models)
    results.update(vote)

    results["used_market_data"] = [f"{provider_name}:{stock}"]
    results["used_base_models"] = [f.model for f in models]
    results["used_ensemble"] = bool(models)
    results["cross_asset_inputs"] = []
    results["rule_inputs"] = RULE_INPUTS
    results["confidence_inputs"] = _confidence_inputs(df, models, horizon)
    results["status"] = "OK"
    results["data_grade"] = "OFFICIAL_DAILY"
    results["warnings"] = warnings
    results.update(build_fingerprint())
    return results
