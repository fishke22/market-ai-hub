"""Phase 2Q-F.6 — public MCP safe view（whitelist-based sanitizer）。

Raw domain objects → public semantic view。採 explicit whitelist（只允許明確核准欄位進
PUBLIC MCP response），不靠 blacklist 逐一把 dangerous fields 移除。

讓 MCP client 即使完全忽略 System Prompt，public payload 也不容易產生
probability lie / direction lie / proxy-direct lie / support lie / trade instruction。
"""
from __future__ import annotations

from typing import Any

# ── 2Q-F.5 §6：canonical instrument display names ──
CANONICAL_INSTRUMENT_NAMES = {
    "OSE_NIKKEI225_MICRO_FUTURES": "OSE Nikkei 225 Micro Futures",
    "OSE_NIKKEI225_MINI_FUTURES": "OSE Nikkei 225 mini Futures",
    "OSE_NIKKEI225_LARGE_FUTURES": "OSE Nikkei 225 Futures (Large)",
    "^N225": "Nikkei 225 index (^N225, PROXY)",
    "TAIEX": "TAIEX cash index (forecast/reference)",
}


def canonical_instrument_name(instrument: str) -> str:
    return CANONICAL_INSTRUMENT_NAMES.get(instrument, instrument)


# ── 2Q-F.5 §20/§26：position-aware research guard ──
POSITION_GUIDANCE_POLICY = {
    "mode": "RISK_ANALYSIS_ONLY",
    "personalized_trade_action": "PROHIBITED",
    "allowed": ["EXPOSURE", "PNL_SENSITIVITY", "SCENARIO_ANALYSIS"],
    "forbidden": [
        "ADD_POSITION", "REDUCE_POSITION", "STOP_PRICE",
        "TAKE_PROFIT_PRICE", "PERSONALIZED_ORDER_SIZE",
    ],
}


def position_guidance_policy() -> dict:
    return dict(POSITION_GUIDANCE_POLICY)


# ── 2Q-F.6 §5：PRICE_FORECAST public whitelist（source field → public field）──
_PUBLIC_FORECAST_WHITELIST = {
    "model": "model_name",
    "model_task": "model_task",
    "symbol": "forecast_target",
    "horizon": "horizon",
    "data_frequency": "data_frequency",
    "point_forecast": "point_forecast",
    "terminal_forecast": "terminal_forecast",
    "expected_return": "expected_return_research",
    "forecast_dates": "forecast_dates",
    "forecast_path": "forecast_path",
    "target_calendar": "calendar",
    "calendar_grade": "calendar_grade",
    "engineering_status": "engineering_status",
    "predictive_validation_status": "validation_status",
    "data_grade": "data_grade",
    "warnings": "warnings",
    "lower_reference": "lower_reference",
    "upper_reference": "upper_reference",
    "quantile_type": "quantile_type",
    "quantile_valid": "quantile_valid",
}

# 明確禁止進 PUBLIC 的欄位（即使意外出現）
_FORBIDDEN_PUBLIC = {
    "direction", "confidence", "class_probabilities", "class_probabilities_calibrated",
    "probability_available", "probability_calibrated", "calibration_method",
    "calibration_sample_size", "calibration_metrics", "support", "resistance",
    "support_levels", "resistance_levels", "entry", "stop", "take_profit",
    "model_agreement", "legacy_raw_unvalidated_agreement",
}


def sanitize_forecast_dump(d: dict, *, audit: bool = False) -> dict:
    """ForecastOutput.model_dump() → public-safe view（whitelist）。

    - 只保留 whitelist 欄位（rename 為 public 名）。
    - quantiles → predictive_quantile_range（不叫 support/resistance/stop/target）。
    - class_probabilities → 移除（uncalibrated 不稱 probability）；audit 才保留 raw_class_scores。
    - direction / confidence / agreement → 移除。
    - 加 direction contract（direction_status / direction_value / eligible vote count / validated agreement）。
    """
    if audit:
        out = dict(d)
        out["view"] = "audit"
        out["raw_class_scores_research_only"] = True
        out["UNCALIBRATED_RAW_SCORE"] = True
        out["NOT_PROBABILITY"] = True
        out["DO_NOT_USE_AS_VALIDATED_DIRECTION"] = True
        return out

    out: dict[str, Any] = {"view": "public"}
    for src, dst in _PUBLIC_FORECAST_WHITELIST.items():
        if src in d:
            out[dst] = d[src]

    # quantiles → predictive_quantile_range
    if "quantiles" in d:
        out["predictive_quantile_range"] = d["quantiles"]

    # forecast scope / instrument role（由 caller 或 model_task 推導）
    out.setdefault("research_only", True)

    # direction contract（authoritative）
    mm = d.get("model_metadata") or {}
    out["direction_status"] = mm.get("direction_status", "NO_VALIDATED_DIRECTION")
    out["direction_value"] = mm.get("direction_value")
    out["eligible_direction_vote_count"] = mm.get("eligible_direction_vote_count", 0)
    out["validated_direction_agreement"] = mm.get("validated_direction_agreement", "N/A")
    # §3：public 只標 raw score 可用性，不暴露 raw numeric（避免被當 probability）
    out["raw_score_available"] = bool(d.get("class_probabilities"))
    out["calibrated_probability_available"] = bool(d.get("probability_calibrated", False))

    # 明確移除任何意外殘留的 forbidden 欄位
    for k in list(out.keys()):
        if k in _FORBIDDEN_PUBLIC:
            out.pop(k, None)
    return out


def sanitize_ensemble_dump(d: dict, *, audit: bool = False) -> dict:
    """ensemble model_dump() → public-safe view（移除 raw agreement / class_probabilities / direction）。"""
    if audit:
        return dict(d)
    out = sanitize_forecast_dump(d)
    out["model_name"] = "ensemble"
    out["model_task"] = "ENSEMBLE"
    return out


def public_view(payload: dict, *, audit: bool = False) -> dict:
    """通用 public semantic view entry。audit=True 才保留 raw fields。"""
    return sanitize_forecast_dump(payload, audit=audit)


_MODEL_KEYS = ("chronos", "timesfm", "xgb", "lgbm", "ensemble", "ensemble_result")


def sanitize_analysis_output(d: dict, *, market: str = "osaka", audit: bool = False) -> dict:
    """analyze_osaka_nikkei / analyze_taiwan_stock 的 public-safe view。

    - 巢狀 model dicts 逐一 whitelist sanitize。
    - raw direction / agreement / class_probabilities 移除。
    - 加 authoritative direction contract + semantic_scope。
    """
    if audit:
        return dict(d)

    out = dict(d)
    for k in _MODEL_KEYS:
        v = out.get(k)
        if isinstance(v, dict) and "status" not in v:
            out[k] = sanitize_forecast_dump(v)
    # price_forecast_ensemble / direction_classification_ensemble：移除 class_probabilities / raw agreement
    for k in ("price_forecast_ensemble", "direction_classification_ensemble"):
        v = out.get(k)
        if isinstance(v, dict):
            v = dict(v)
            v.pop("class_probabilities", None)
            out[k] = v

    # 移除 raw legacy direction fields（改用 authoritative contract）
    for k in ("analysis_direction", "integrated_market_view", "vote_direction",
              "probability_argmax_direction", "final_direction"):
        out.pop(k, None)

    mm = {}
    ens = d.get("ensemble")
    if isinstance(ens, dict):
        mm = ens.get("model_metadata") or {}
    out["direction_status"] = mm.get("direction_status", "NO_VALIDATED_DIRECTION")
    out["direction_value"] = mm.get("direction_value")
    out["eligible_direction_vote_count"] = mm.get("eligible_direction_vote_count", 0)
    out["validated_direction_agreement"] = mm.get("validated_direction_agreement", "N/A")

    # semantic scope：analyze_osaka_nikkei 是 ^N225 PROXY ONLY
    if market == "osaka":
        out["semantic_scope"] = "PROXY_ONLY"
        out["target"] = "^N225"
        out["instrument_role"] = "PROXY"
        out["forecast_scope"] = "PROXY_MODEL_REFERENCE"
        out["not_execution_target"] = True
        out["not_micro_direct"] = True
        out["direct_execution_target"] = "OSE_NIKKEI225_MICRO_FUTURES"
    return out
