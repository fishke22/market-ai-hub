"""Phase 2Q-F.5 — public MCP safe view（safe-by-default sanitizer）。

Raw domain objects → public semantic view。讓 MCP client 即使完全忽略 System Prompt，
public payload 也不容易產生 probability lie / direction lie / proxy-direct lie / support lie /
trading advice。
"""
from __future__ import annotations

from typing import Any

# 2Q-F.5 §6：canonical instrument display names
CANONICAL_INSTRUMENT_NAMES = {
    "OSE_NIKKEI225_MICRO_FUTURES": "OSE Nikkei 225 Micro Futures",
    "OSE_NIKKEI225_MINI_FUTURES": "OSE Nikkei 225 mini Futures",
    "OSE_NIKKEI225_LARGE_FUTURES": "OSE Nikkei 225 Futures (Large)",
    "^N225": "Nikkei 225 index (^N225, PROXY)",
    "TAIEX": "TAIEX cash index (forecast/reference)",
}


def canonical_instrument_name(instrument: str) -> str:
    return CANONICAL_INSTRUMENT_NAMES.get(instrument, instrument)


# 2Q-F.5 §20/§26：position-aware research guard
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


# 2Q-F.5 §3/§10：public semantic field sanitization
def sanitize_forecast_dump(d: dict) -> dict:
    """ForecastOutput.model_dump() → public-safe view。

    - class_probabilities → 移除（uncalibrated 不稱 probability；保留 raw_class_scores 標 research_only）
    - quantiles → predictive_quantile_range（不叫 support/resistance/stop/target）
    - confidence → 移除（非 calibrated probability）
    - direction → 以 direction_status/direction_value 取代；0 votes → null
    """
    out = {}
    for k, v in d.items():
        if k == "class_probabilities":
            # 只在有值時標 raw_class_scores（research_only），不叫 probability
            if v:
                out["raw_class_scores"] = v
                out["raw_class_scores_research_only"] = True
                out["raw_class_scores_calibrated"] = False
            continue
        if k == "quantiles":
            out["predictive_quantile_range"] = v
            continue
        if k == "confidence":
            continue
        if k == "direction":
            continue  # 以 direction_status/direction_value 取代
        out[k] = v

    # direction contract：從 model_metadata 取 authoritative direction_status/direction_value
    mm = d.get("model_metadata") or {}
    out["direction_status"] = mm.get("direction_status", "NO_VALIDATED_MODEL_CONSENSUS")
    out["direction_value"] = mm.get("direction_value")
    out["eligible_direction_vote_count"] = mm.get("eligible_direction_vote_count", 0)
    out["validated_direction_agreement"] = mm.get("validated_direction_agreement", "N/A")
    return out


def sanitize_ensemble_dump(d: dict) -> dict:
    """ensemble model_dump() → public-safe view（移除 raw agreement / class_probabilities）。"""
    out = dict(d)
    mm = out.get("model_metadata")
    if isinstance(mm, dict):
        # 移除 raw agreement（不得當 consensus）；保留 validated agreement + direction contract
        mm.pop("legacy_raw_unvalidated_agreement", None)
        mm.pop("model_agreement", None)
        # 移除 raw class scores / probabilities（只在 audit 呈現）
        de = mm.get("direction_ensemble") or {}
        if isinstance(de, dict):
            de.pop("class_probabilities", None)
        out["model_metadata"] = mm
    # direction 欄位以 contract 取代
    out.pop("direction", None)
    return out


def public_view(payload: dict, *, audit: bool = False) -> dict:
    """通用 public semantic view entry。audit=True 才保留 raw fields。"""
    if audit:
        return payload
    return sanitize_forecast_dump(payload)
