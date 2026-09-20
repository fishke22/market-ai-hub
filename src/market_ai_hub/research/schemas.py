"""Phase 2A Prediction Registry schema（不可變 forecast + append-only outcome）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PredictionRecord(BaseModel):
    """一次預測的完整不可變記錄（建立後不得修改，只能 append outcome）。

    information_cutoff：模型可使用的資料最晚時間（任何 available_at > cutoff 的資料不得進模型）。
    """

    # identity / time
    forecast_id: str
    created_at: datetime = Field(default_factory=_now)
    information_cutoff: datetime

    # target
    market: str = ""
    target: str = ""
    instrument: str = ""
    contract: str = ""

    # horizon / calendar
    horizon: str = ""
    forecast_origin: datetime | None = None
    forecast_target_dates: list[str] = Field(default_factory=list)
    exchange_calendar: str = ""

    # model
    model_name: str
    model_task: str = ""
    model_revision: str = ""
    model_build_id: str = ""
    training_cutoff: datetime | None = None

    # reproducibility
    input_data_hash: str = ""
    dataset_version: str = ""
    feature_version: str = ""
    forecast_config_hash: str = ""
    inference_seed: int | None = None
    sampling_config: dict[str, Any] = Field(default_factory=dict)
    deterministic_mode: bool = True

    # forecast value
    point_forecast: float
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None
    origin_price: float | None = None  # forecast_origin 當時的價格（供結算方向 / scaled_error）

    # direction / probability
    direction: str = ""
    raw_class_scores: dict[str, float] | None = None
    probability_calibrated: bool = False

    # status
    engineering_status: str = ""
    predictive_validation_status: str = ""

    # context
    regime_as_known_at_prediction_time: str = "UNKNOWN"
    data_quality_state: str = ""

    # reference to raw model output artifact
    raw_output_reference: str = ""


class OutcomeRecord(BaseModel):
    """forecast horizon 到期後的結算（append-only，不得回頭改 forecast）。"""

    forecast_id: str
    actual: float
    actual_timestamp: datetime | None = None
    absolute_error: float
    squared_error: float
    scaled_error: float | None = None
    direction_result: str = ""  # "correct" / "incorrect" / "flat" / ""
    interval_hit: bool | None = None
    pinball_loss: float | None = None
    settled_at: datetime = Field(default_factory=_now)


class SettleNotReadyError(Exception):
    """target date 尚未到、或尚無 actual 資料可結算。"""


class LookAheadError(Exception):
    """資料 available_at > information_cutoff 的 look-ahead leakage。"""


def assert_no_lookahead(cutoff: datetime, timestamps: list[datetime]) -> None:
    """任何資料時間戳 > information_cutoff → LookAheadError（未來資料不得進模型）。"""
    c = cutoff if cutoff.tzinfo is not None else cutoff.replace(tzinfo=timezone.utc)
    for ts in timestamps:
        t = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
        if t > c:
            raise LookAheadError(f"look-ahead leakage: {t} > information_cutoff {c}")
