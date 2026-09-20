"""Phase 2G — Forecast Synthesis（O/Q/R/S）。

- 統合層分開保留 direct / joint / scenario / dynamic_ensemble / best_baseline /
  historical_edge / regime / event_state，不混成單一 final_price。
- research_center 必須 deterministic + reproducible（method/inputs/version），否則不建立。
- Historical Edge 只作 Research Evidence，不修改模型 forecast（MODEL_BULLISH + EDGE_UNPROVEN）。
- ResearchState 不強迫多空。
"""
from __future__ import annotations

import numpy as np
from uuid import uuid4

from market_ai_hub.forecast.contract import ForecastSynthesisResult, ResearchState


def weighted_median(values: list[float], weights: list[float]) -> float:
    idx = np.argsort(values)
    v = np.asarray(values)[idx]
    w = np.asarray(weights, dtype=float)[idx]
    cdf = np.cumsum(w) / w.sum()
    j = int(np.searchsorted(cdf, 0.5))
    return float(v[j])


def compute_research_center(method: str, inputs: dict, version: str = "v1") -> float:
    """deterministic research center。method 必須登錄，否則 raise（不允許 LLM 隨意改數字）。"""
    if method == "model_center":
        return float(inputs["model_center"])
    if method == "ensemble_p50":
        return float(inputs["ensemble_p50"])
    if method == "weighted_median":
        return weighted_median(inputs["values"], inputs["weights"])
    raise ValueError(f"unknown research_center_method '{method}' (not reproducible)")


def derive_research_state(direct_direction: str, ensemble_direction: str,
                          scenario_direction: str, edge_status: str,
                          baseline_dominant: bool = False,
                          data_sufficient: bool = True,
                          model_agreement: bool = True) -> str:
    """deterministic research state，不強迫多空。"""
    if not data_sufficient:
        return ResearchState.INSUFFICIENT_DATA
    if edge_status == "NO_EDGE":
        return ResearchState.NO_EDGE
    if baseline_dominant:
        return ResearchState.BASELINE_DOMINANT
    if not model_agreement:
        return ResearchState.MODEL_DISAGREEMENT
    dirs = [d for d in (direct_direction, ensemble_direction, scenario_direction) if d in ("bullish", "bearish")]
    if not dirs:
        return ResearchState.WAIT
    if all(d == "bullish" for d in dirs):
        return ResearchState.BULLISH_EVIDENCE
    if all(d == "bearish" for d in dirs):
        return ResearchState.BEARISH_EVIDENCE
    return ResearchState.MIXED


def integrate_historical_edge(model_direction: str, edge_status: str) -> dict:
    """Historical Edge 只作 evidence，不修改 forecast。"""
    return {
        "model_direction": model_direction,
        "edge_status": edge_status,
        "evidence": f"{model_direction.upper()} + EDGE_{edge_status}",
    }


def synthesize(*, target: str, horizon: str, direct_forecast: dict | None = None,
               joint_forecast: dict | None = None, scenario_forecast: dict | None = None,
               dynamic_ensemble: dict | None = None, best_baseline: dict | None = None,
               historical_edge: dict | None = None, regime: dict | None = None,
               event_state: dict | None = None,
               research_center_method: str = "", research_center_inputs: dict | None = None,
               research_center_version: str = "v1",
               ensemble_distribution_validated: bool = False,
               ensemble_quantile_method: str = "ENSEMBLE_RESEARCH_QUANTILE_SUMMARY",
               interval_calibration_status: str = "UNVALIDATED") -> ForecastSynthesisResult:
    """組出 ForecastSynthesisResult；research_center 只在有 deterministic method 時建立。"""
    r = ForecastSynthesisResult(
        synthesis_id=str(uuid4()), target=target, horizon=horizon,
        direct_forecast=direct_forecast or {},
        joint_forecast=joint_forecast or {},
        scenario_forecast=scenario_forecast or {},
        dynamic_ensemble=dynamic_ensemble or {},
        best_baseline=best_baseline or {},
        historical_edge=historical_edge or {},
        regime=regime or {},
        event_state=event_state or {},
        ensemble_distribution_validated=ensemble_distribution_validated,
        ensemble_quantile_method=ensemble_quantile_method,
        interval_calibration_status=interval_calibration_status,
    )
    if research_center_method:
        r.research_center = compute_research_center(
            research_center_method, research_center_inputs or {}, research_center_version)
        r.research_center_method = research_center_method
        r.research_center_inputs = research_center_inputs or {}
        r.research_center_version = research_center_version
    return r
