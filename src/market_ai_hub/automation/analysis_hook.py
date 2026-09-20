"""Phase 2E — Analysis save hook（不改 V1 response schema）。

透過 internal hook 把正式分析存進 AnalysisArchive，MCP response 不變。
LLM 文字不得拿來訓練價格模型（避免 self-reinforcement）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from market_ai_hub.automation.archive import AnalysisArchive, AnalysisRecord

log = logging.getLogger(__name__)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def archive_analysis(result: dict) -> str:
    """把 analyze_* 的 dict 結果轉成 AnalysisRecord 存入 archive。回傳 analysis_id。"""
    archive = AnalysisArchive()
    aid = str(uuid4())
    ens = result.get("ensemble", {}) if isinstance(result.get("ensemble"), dict) else {}
    pe = result.get("price_forecast_ensemble", {}) if isinstance(result.get("price_forecast_ensemble"), dict) else {}
    rec = AnalysisRecord(
        analysis_id=aid,
        information_cutoff=datetime.now(timezone.utc),
        market=result.get("market", ""),
        target=result.get("symbol", ""),
        instrument=result.get("symbol", ""),
        horizon=result.get("horizon", ""),
        forecast_target_dates=result.get("forecast_target_dates", []),
        reference_price=_f(ens.get("terminal_forecast")) or _f(pe.get("point_forecast")),
        model_center=_f(pe.get("point_forecast")),
        research_center=_f(pe.get("point_forecast")),
        model_range=[_f(pe.get("quantiles", {}).get("p10")), _f(pe.get("quantiles", {}).get("p90"))] if pe.get("quantiles") else [],
        direction=result.get("analysis_direction", ""),
        research_confidence=_f(ens.get("confidence")) if isinstance(ens, dict) else None,
        regime=result.get("confidence_inputs", {}).get("regime_performance", "") if isinstance(result.get("confidence_inputs"), dict) else "",
        event_state="",
        forecast_ids=[],
        model_versions=result.get("build", {}).get("build_id", "") and {"build_id": result.get("build", {}).get("build_id")} or {},
        dataset_version="v1",
        feature_version="base-v1",
    )
    rec.analysis_packet_hash = rec.packet_hash()
    archive.save(rec)
    return aid
