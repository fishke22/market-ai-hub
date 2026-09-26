"""Phase 2H — Analysis Packet schema（§4）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

# price type 語義（§5）
PRICE_TYPE_SETTLEMENT = "SETTLEMENT"
PRICE_TYPE_CLOSE = "CLOSE"
PRICE_TYPE_LIVE = "LIVE_PRICE"
PRICE_TYPE_REFERENCE = "REFERENCE"
PRICE_TYPE_PROXY = "PROXY"

# forecast 語義（§6）
RESEARCH_ENSEMBLE = "RESEARCH_ENSEMBLE"
UNVALIDATED_FORWARD = "UNVALIDATED_FORWARD"
ENSEMBLE_RESEARCH_QUANTILE_SUMMARY = "ENSEMBLE_RESEARCH_QUANTILE_SUMMARY"


class AnalysisPacket(BaseModel):
    analysis_packet_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    information_cutoff: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    execution_target: str = "OSE_NIKKEI225_MICRO_FUTURES"
    contract_month: str = ""
    exchange: str = "OSE"

    reference_price: float | None = None
    reference_price_type: str = PRICE_TYPE_REFERENCE
    price_timestamp: str = ""

    target_data_status: str = ""          # e.g. LIVE_VERIFIED / CONTRACT_ONLY / MISSING
    target_price_source: str = ""         # settlement / reference / proxy

    forecast_target_dates: list[str] = Field(default_factory=list)
    horizon: str = "1d"

    market_session: str = ""
    freshness: str = ""

    regime: dict[str, Any] = Field(default_factory=dict)
    event_state: str = ""
    upcoming_events: list[dict[str, Any]] = Field(default_factory=list)

    direct_forecast_summary: dict[str, Any] = Field(default_factory=dict)
    joint_forecast_summary: dict[str, Any] = Field(default_factory=dict)
    scenario_summary: dict[str, Any] = Field(default_factory=dict)
    dynamic_ensemble_summary: dict[str, Any] = Field(default_factory=dict)

    best_baseline: dict[str, Any] = Field(default_factory=dict)
    best_validated_model: dict[str, Any] = Field(default_factory=dict)
    challenger_status: str = ""

    model_range: list[float] = Field(default_factory=list)
    research_center: float | None = None
    research_center_method: str = ""
    research_center_version: str = ""

    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    invalidation_levels: list[float] = Field(default_factory=list)

    historical_edge_summary: dict[str, Any] = Field(default_factory=dict)
    strategy_research_state: str = "WAIT"
    research_decision_support: dict[str, Any] = Field(default_factory=dict)

    top_positive_drivers: list[str] = Field(default_factory=list)
    top_negative_drivers: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)

    data_quality: dict[str, Any] = Field(default_factory=dict)
    data_coverage_summary: list[dict[str, Any]] = Field(default_factory=list)
    # W2: persisted V2-A.2 factor-observation provenance (source/quality, not a trading signal).
    factor_observation_summary: list[dict[str, Any]] = Field(default_factory=list)
    model_input_readiness: dict[str, Any] = Field(default_factory=dict)

    research_gates: dict[str, Any] = Field(default_factory=dict)
    reanalysis_conditions: list[str] = Field(default_factory=list)

    # ── V2 target semantics（§6）：direct / continuous / proxy / calendar 分離，不得合併 ──
    target_semantics: dict[str, Any] = Field(default_factory=dict)

    # ── V2 calendar 分離（§7）：direct 與 proxy 各別 session/bar ──
    direct_next_session: str = ""
    proxy_next_model_bar: str = ""

    # ── V2 support/resistance（§16）：不可用時 NOT_AVAILABLE，quantile 獨立為 statistical reference ──
    support_resistance_status: str = "NOT_AVAILABLE"
    model_statistical_reference_range: dict[str, Any] = Field(default_factory=dict)

    # ── V2 research truth（§8）：單一來源 ValidationTruth ──
    validation_truth: dict[str, Any] = Field(default_factory=dict)

    # ── V2 market environment vs economic edge（§13）：risk_on/trend/vol 是環境，非經濟 edge ──
    market_environment: dict[str, Any] = Field(default_factory=dict)
    economic_edge_summary: dict[str, Any] = Field(default_factory=dict)

    # ── V2 driver panel（§12）：context/explanatory features，非 formal causal validation ──
    driver_panel: dict[str, Any] = Field(default_factory=dict)

    # ── 2Q-F.4：display policy（answer layer 不需重建 safety logic）──
    display_policy: dict[str, Any] = Field(default_factory=dict)

    # ── 2Q-F.5：position-aware research guard ──
    position_guidance_policy: dict[str, Any] = Field(default_factory=dict)

    # data lake 狀態（§11）
    data_reused: list[str] = Field(default_factory=list)
    data_fetched: list[str] = Field(default_factory=list)
    data_stale: list[str] = Field(default_factory=list)
    data_missing: list[str] = Field(default_factory=list)

    # forecast 語義（§6/§7）
    ensemble_validation: str = UNVALIDATED_FORWARD
    ensemble_distribution_validated: bool = False
    ensemble_quantile_method: str = ENSEMBLE_RESEARCH_QUANTILE_SUMMARY

    # archive 連結
    analysis_id: str = ""
    saved_to_archive: bool = False

    def render(self, detail_level: str) -> dict:
        d = self.model_dump(mode="json")
        if detail_level == "compact":
            for k in ("upcoming_events", "data_coverage_summary", "factor_observation_summary",
                      "data_reused", "data_fetched", "data_stale", "contradictions", "data_quality"):
                # compact 精簡長 list / debug 細節
                if k in d:
                    d[k] = d[k][:3] if isinstance(d[k], list) else {}
            d.pop("top_negative_drivers", None)
            d.pop("research_gates", None)
            return d
        if detail_level == "normal":
            return d
        # audit：加 model revisions / provenance（由 builder 補上）
        d["audit"] = {
            "model_revisions": self.joint_forecast_summary.get("model_revision", ""),
            "dataset_versions": self.joint_forecast_summary.get("dataset_version", ""),
            "gate_status": self.research_gates,
            "coverage": self.data_coverage_summary,
        }
        return d
