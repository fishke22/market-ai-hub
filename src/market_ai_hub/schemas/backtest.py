"""Backtest 結果 schema（spec §24 + V1 remediation 擴充，全部 additive）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BacktestRecord(BaseModel):
    model: str
    model_version: str
    data_version: str
    symbol: str
    period: str
    horizon: str
    feature_set: str
    timestamp: datetime

    # 通用
    directional_accuracy: float
    mae: float | None = None
    rmse: float | None = None
    pinball_loss: float | None = None
    brier_score: float | None = None

    # 交易研究；只有真 realized return 才能填。無成本時必須另標 gross。
    hit_rate: float | None = None
    average_return: float | None = None
    expectancy: float | None = None
    profit_factor: float | None = None
    max_drawdown: float | None = None
    sharpe: float | None = None
    sortino: float | None = None

    n_samples: int

    # ── V1 remediation 新增（additive，預設 None = 無資料，不是 0）──
    task_type: str | None = None  # "classification" / "time_series"
    classes: list[int] | None = None
    flat_threshold: float | None = None
    accuracy: float | None = None
    balanced_accuracy: float | None = None
    macro_f1: float | None = None
    mcc: float | None = None
    mase: float | None = None
    class_distribution: dict[str, float | None] | None = None
    uniform_random_baseline_accuracy: float | None = None
    majority_class_baseline_accuracy: float | None = None
    baseline_threshold: float | None = None
    beats_majority_baseline: bool | None = None
    majority_class: int | None = None
    majority_class_train_prevalence: float | None = None
    uniform_random_baseline_balanced_accuracy: float | None = None
    majority_class_baseline_balanced_accuracy: float | None = None
    majority_class_baseline_macro_f1: float | None = None
    baseline_metric: str | None = None
    baseline_semantics: str | None = None

    # 真 realized-return diagnostics；不是含成本 economic edge。
    economic_metrics_status: str | None = None
    economic_return_semantics: str | None = None
    transaction_costs_included: bool | None = None
    n_active_trades: int | None = None

    # validation identity：inference/validation 必須使用同 adjustment contract。
    dataset_semantics: str | None = None
    adjustment_semantics: str | None = None
    source_semantics: str | None = None

    # ── V1 remediation：狀態與 eligibility（以記錄當下的判定為準）──
    engineering_status: str | None = None
    predictive_validation_status: str | None = None
    eligible_for_direction_vote: bool | None = None
    baseline_results: dict[str, Any] | None = None

    # 日期範圍
    sample_size: int | None = None
    date_range: dict[str, str] | None = None
