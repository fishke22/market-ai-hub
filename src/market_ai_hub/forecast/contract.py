"""Phase 2G — Joint / Scenario / Ensemble / Synthesis 合約。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

# --- 權重語義（F） ---
UNVALIDATED_WEIGHT = "UNVALIDATED_WEIGHT"        # 未經 OOS calibration，不得稱機率/發生率/成功率
CALIBRATED_PROBABILITY = "CALIBRATED_PROBABILITY"  # 只有 Forward/OOS calibration 後才可

# --- Ensemble quantile 語義（P） ---
ENSEMBLE_RESEARCH_QUANTILE_SUMMARY = "ENSEMBLE_RESEARCH_QUANTILE_SUMMARY"  # 只是 component 平均
SAMPLE_LEVEL_MIXTURE = "SAMPLE_LEVEL_MIXTURE"    # 真正 sample-level mixture → 可回 predictive quantiles

# --- 研究最終狀態（S） ---
RESEARCH_STATES = [
    "BULLISH_EVIDENCE", "BEARISH_EVIDENCE", "MIXED", "WAIT", "NO_EDGE",
    "INSUFFICIENT_DATA", "MODEL_DISAGREEMENT", "BASELINE_DOMINANT",
]

# --- Auto routing 限制（W） ---
AUTO_SELECT_FOR_RESEARCH = True
AUTO_TRADE = False
AUTO_PROMOTE_CHAMPION = False


class JointForecastResult(BaseModel):
    joint_forecast_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    information_cutoff: datetime

    target: str = ""
    horizon: str = ""
    forecast_target_dates: list[str] = Field(default_factory=list)

    input_panel_version: str = ""
    feature_version: str = ""
    regime_version: str = ""

    model_name: str = ""
    model_revision: str = ""

    future_paths: list[dict[str, Any]] = Field(default_factory=list)   # cross-asset paths
    factor_distributions: dict[str, Any] = Field(default_factory=dict)
    target_distribution: list[float] = Field(default_factory=list)     # 樣本（可 mixture）

    p10: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    p90: float | None = None

    sampling_method: str = ""
    sample_count: int = 0
    seed: int | None = None

    calibration_status: str = "UNVALIDATED"
    data_quality: str = ""
    model_status: str = ""


class ScenarioPath(BaseModel):
    scenario_id: str
    horizon: str = ""
    NQ_path: list[float] = Field(default_factory=list)
    ES_path: list[float] = Field(default_factory=list)
    SOX_path: list[float] = Field(default_factory=list)
    USDJPY_path: list[float] = Field(default_factory=list)
    VIX_path: list[float] = Field(default_factory=list)
    rates_path: list[float] = Field(default_factory=list)

    nikkei_distribution: list[float] = Field(default_factory=list)

    scenario_source: str = ""          # feature/regime rule 或 model distribution
    scenario_weight: float = 0.0
    weight_calibration_status: str = UNVALIDATED_WEIGHT


class ForecastSynthesisResult(BaseModel):
    """統合層：三者（direct / joint / scenario）必須保留 provenance，不能混成單一數字。"""
    synthesis_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    information_cutoff: datetime | None = None
    target: str = ""
    horizon: str = ""

    direct_forecast: dict[str, Any] = Field(default_factory=dict)
    joint_forecast: dict[str, Any] = Field(default_factory=dict)
    scenario_forecast: dict[str, Any] = Field(default_factory=dict)
    dynamic_ensemble: dict[str, Any] = Field(default_factory=dict)
    best_baseline: dict[str, Any] = Field(default_factory=dict)
    historical_edge: dict[str, Any] = Field(default_factory=dict)
    regime: dict[str, Any] = Field(default_factory=dict)
    event_state: dict[str, Any] = Field(default_factory=dict)

    research_state: str = "WAIT"       # ResearchState（不強迫多空）

    # ensemble quantile 語義（P）
    ensemble_distribution_validated: bool = False
    ensemble_quantile_method: str = ENSEMBLE_RESEARCH_QUANTILE_SUMMARY
    interval_calibration_status: str = "UNVALIDATED"

    # research center（Q）：無 deterministic method 則不建立
    research_center: float | None = None
    research_center_method: str = ""
    research_center_inputs: dict[str, Any] = Field(default_factory=dict)
    research_center_version: str = ""


class ResearchState:
    BULLISH_EVIDENCE = "BULLISH_EVIDENCE"
    BEARISH_EVIDENCE = "BEARISH_EVIDENCE"
    MIXED = "MIXED"
    WAIT = "WAIT"
    NO_EDGE = "NO_EDGE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"
    BASELINE_DOMINANT = "BASELINE_DOMINANT"


def is_research_state(x: str) -> bool:
    return x in RESEARCH_STATES
