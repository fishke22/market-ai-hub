"""統一市場資料 schema。所有時間戳 storage 一律 UTC；顯示轉換在 presentation 層做。

V1.1 擴充（全部 additive）：
- build fingerprint：market_ai_version / build_id / source_root / python_executable / server_started_at / schema_version
- model_task：PRICE_FORECAST / DIRECTION_CLASSIFICATION
- quantile contract：p10<=p50<=p90 必須成立；不是真 quantile 的欄位不得叫 p10/p90
  （quantile_type = PREDICTIVE / NOT_AVAILABLE，quantile_valid 標記，invalid 不進 ensemble）
- target calendar：target_calendar / target_trading_dates / calendar_grade
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DataGrade(str, Enum):
    RESEARCH_PROXY = "RESEARCH_PROXY"
    DELAYED = "DELAYED"
    OFFICIAL_DAILY = "OFFICIAL_DAILY"
    BROKER_REALTIME = "BROKER_REALTIME"
    EXCHANGE_REALTIME = "EXCHANGE_REALTIME"


class RealtimeGrade(str, Enum):
    BEST_EFFORT = "BEST_EFFORT"
    DELAYED_POSSIBLE = "DELAYED_POSSIBLE"
    PERSONAL_RESEARCH = "PERSONAL_RESEARCH"
    DELAYED = "DELAYED"


class ModelRole(str, Enum):
    BASE_MODEL = "BASE_MODEL"
    ENSEMBLE = "ENSEMBLE"
    ANALYSIS_WRAPPER = "ANALYSIS_WRAPPER"


class ModelTask(str, Enum):
    PRICE_FORECAST = "PRICE_FORECAST"
    DIRECTION_CLASSIFICATION = "DIRECTION_CLASSIFICATION"


class QuantileType(str, Enum):
    PREDICTIVE = "PREDICTIVE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class EngineeringStatus(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


class PredictiveValidationStatus(str, Enum):
    VALIDATED = "VALIDATED"
    EXPERIMENTAL = "EXPERIMENTAL"
    UNVALIDATED = "UNVALIDATED"
    DEGRADED = "DEGRADED"
    REJECTED = "REJECTED"


class GateStatus(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    UNPROVEN = "UNPROVEN"
    FAIL = "FAIL"


class MarketBar(BaseModel):
    """單根 K 線（統一 schema，spec §17）。"""

    timestamp_utc: datetime
    timestamp_local: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    provider: str
    data_grade: DataGrade
    retrieved_at: datetime

    @field_validator("timestamp_utc", "timestamp_local", "retrieved_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        return v


def validate_quantiles(q: dict[str, float | None]) -> tuple[bool, str]:
    """Quantile contract：p10 <= p50 <= p90 必須成立。

    缺值（null）視為 NOT_AVAILABLE（合法）；有值但違反單調性 = invalid，
    不得靜默排序，不得進 ensemble。
    """
    if not q:
        return True, "empty"
    for k in ("p10", "p50", "p90"):
        if q.get(k) is None:
            return True, "NOT_AVAILABLE (missing quantiles)"
    try:
        p10, p50, p90 = float(q["p10"]), float(q["p50"]), float(q["p90"])  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False, "non-numeric quantile value"
    if not (p10 <= p50 <= p90):
        return False, f"monotonicity violated: p10={p10} p50={p50} p90={p90}"
    return True, "valid"


class ForecastOutput(BaseModel):
    """預測統一輸出（spec §22 + V1 remediation + V1.1，全部 additive）。

    Horizon 語義：data_frequency="1d"（日線 bar）時，"Nd" = N 根 trading bars。
    point_forecast / expected_return 一律以 terminal_forecast（路徑最後一步）計算。
    """

    # ── 既有欄位（backward compatible）──
    model: str
    symbol: str
    as_of: datetime
    horizon: str
    point_forecast: float
    expected_return: float
    quantiles: dict[str, float | None]
    direction: str
    confidence: float
    data_grade: DataGrade
    warnings: list[str] = Field(default_factory=list)

    # ── V1 remediation：horizon integrity ──
    requested_horizon: str = ""
    effective_horizon_steps: int | None = None
    data_frequency: str = ""
    horizon_applied: bool = False
    forecast_path: list[dict[str, Any]] = Field(default_factory=list)
    forecast_dates: list[str] = Field(default_factory=list)
    terminal_forecast: float | None = None

    # ── V1 remediation：角色與雙重狀態 ──
    model_role: str = ModelRole.BASE_MODEL.value
    engineering_status: str = EngineeringStatus.NOT_RUN.value
    predictive_validation_status: str = PredictiveValidationStatus.UNVALIDATED.value

    # ── V1 remediation：eligibility ──
    eligible_for_price_reference: bool = False
    eligible_for_direction_vote: bool = False
    eligible_for_ensemble_weighting: bool = False

    # ── V1.1：model task 與 quantile contract ──
    model_task: str = ""
    quantile_type: str = QuantileType.NOT_AVAILABLE.value
    quantile_valid: bool | None = None
    quantile_invalid_reason: str = ""
    class_probabilities: dict[str, float | None] | None = None
    class_probabilities_calibrated: bool | None = None
    lower_reference: float | None = None
    upper_reference: float | None = None

    # ── V1.1：target calendar ──
    target_calendar: str = ""
    target_trading_dates: list[str] = Field(default_factory=list)
    calendar_grade: str = ""

    # ── V1.2：temporal anchor（forecast target 必須是未來 session）──
    forecast_origin: str = ""                       # 最後一根已觀察 bar 的 UTC 時間戳
    last_observed_trading_date: str = ""            # 最後一根已觀察 bar 的交易所當地交易日
    forecast_target_dates: list[str] = Field(default_factory=list)  # 未來 sessions（嚴格 > last_observed）
    exchange_timezone: str = ""                     # 交易所時區（Asia/Taipei / Asia/Tokyo）
    calendar_name: str = ""                         # XTAI / XTKS
    calendar_source: str = ""                       # exchange_calendars (QuantConnect)
    calendar_verified: bool = False                 # 未確認 → false（禁止假裝 exact）
    calendar_last_verified: str = ""

    # ── V1.2：classification probability calibration metadata ──
    probability_available: bool = False
    probability_calibrated: bool = False
    calibration_method: str = ""                    # "none" / "isotonic" / "platt"
    calibration_sample_size: int | None = None
    calibration_metrics: dict[str, Any] = Field(default_factory=dict)  # brier_score / ece

    # ── V1.1：build fingerprint ──
    market_ai_version: str = ""
    build_id: str = ""
    source_root: str = ""
    python_executable: str = ""
    server_started_at: str = ""
    schema_version: str = ""

    # ── V1.3：forecast reproducibility ──
    inference_seed: int | None = None
    input_data_hash: str = ""
    forecast_config_hash: str = ""
    model_revision: str = ""
    model_build_id: str = ""
    deterministic_mode: bool = True
    forecast_stochastic: bool = False
    sampling_config: dict[str, Any] = Field(default_factory=dict)

    # ── V1.3：market open / quote freshness ──
    market_open: bool | None = None
    tradable_now: bool | None = None
    source_timestamp: str = ""
    received_at: str = ""
    quote_age_seconds: float | None = None
    freshness_status: str = ""
    session_status: str = ""

    # ── V1.3.1：session / freshness 分離 ──
    quote_live: bool | None = None
    usable_for_live_decision: bool | None = None

    # ── 模型專屬 metadata（依 model_role 內容不同）──
    model_metadata: dict[str, Any] = Field(default_factory=dict)

    def attach_build(self, info: dict) -> "ForecastOutput":
        self.market_ai_version = info.get("market_ai_version", "")
        self.build_id = info.get("build_id", "")
        self.source_root = info.get("source_root", "")
        self.python_executable = info.get("python_executable", "")
        self.server_started_at = info.get("server_started_at", "")
        self.schema_version = info.get("schema_version", "")
        return self


class Provenance(BaseModel):
    """raw 資料 provenance metadata（spec §18）。"""

    provider: str
    symbol: str
    requested_at: datetime
    received_at: datetime
    first_timestamp: datetime
    last_timestamp: datetime
    row_count: int
    checksum: str
    adjusted: bool = False
    frequency: str
