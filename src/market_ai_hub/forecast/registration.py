"""Phase 2G — Forward test registration（V）。

Joint / Scenario / Dynamic Ensemble 也必須註冊到 Prediction Registry，
由 Phase 2E automation settlement 自動計分，才能知道是否值得保留。
"""
from __future__ import annotations

from datetime import datetime, timezone

from market_ai_hub.forecast.contract import JointForecastResult
from market_ai_hub.research.schemas import PredictionRecord


def register_joint_forecast(registry, jf: JointForecastResult, origin_price: float,
                            model_name_override: str | None = None) -> str:
    """把 JointForecastResult 轉成 PredictionRecord 註冊，回傳 forecast_id。"""
    p50 = jf.p50
    direction = ""
    if p50 is not None and origin_price:
        direction = "up" if p50 > origin_price else ("down" if p50 < origin_price else "flat")
    rec = PredictionRecord(
        forecast_id=f"joint:{jf.joint_forecast_id}",
        created_at=jf.created_at or datetime.now(timezone.utc),
        information_cutoff=jf.information_cutoff,
        market="", target=jf.target, instrument="", contract="",
        horizon=jf.horizon,
        forecast_target_dates=jf.forecast_target_dates,
        model_name=model_name_override or jf.model_name,
        model_task="joint_forecast", model_revision=jf.model_revision,
        dataset_version=jf.input_panel_version, feature_version=jf.feature_version,
        point_forecast=p50 or 0.0, p10=jf.p10, p50=jf.p50, p90=jf.p90,
        origin_price=origin_price, direction=direction,
        regime_as_known_at_prediction_time="", data_quality_state=jf.data_quality,
        raw_output_reference=jf.joint_forecast_id,
    )
    registry.register(rec)
    return rec.forecast_id
