"""Phase 2F — Strategy Research Contract（StrategyCandidate + status）。"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

# 合法策略狀態
STRATEGY_STATUSES = ["EXPERIMENTAL", "RESEARCH_CANDIDATE", "SHADOW", "REJECTED"]

# 明確禁止（交易）
FORBIDDEN_STATUSES = ["PRODUCTION_TRADING"]

# 研究輸出（合法三態，不強迫每天 LONG/SHORT）
RESEARCH_OUTPUTS = ["TRADE_CANDIDATE", "WAIT", "NO_EDGE"]


class StrategyCandidate(BaseModel):
    strategy_id: str
    version: str = "1"

    market: str = ""
    instrument: str = ""
    horizon: str = ""

    entry_conditions: list[str] = Field(default_factory=list)
    exit_conditions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)

    regime_filter: dict[str, str] = Field(default_factory=dict)
    event_filter: list[str] = Field(default_factory=list)
    forecast_filter: dict[str, str] = Field(default_factory=dict)
    feature_filter: dict[str, str] = Field(default_factory=dict)

    holding_period: int = 1

    cost_assumption: str = "BASE_COST"
    slippage_assumption: str = "BASE"

    training_period: tuple[str, str] | None = None
    validation_period: tuple[str, str] | None = None
    test_period: tuple[str, str] | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_method: str = "interpretable_rule"
    status: str = "EXPERIMENTAL"

    def model_post_init(self, __context) -> None:
        if self.status in FORBIDDEN_STATUSES:
            raise ValueError(f"status {self.status} forbidden (no PRODUCTION_TRADING)")
        if self.status not in STRATEGY_STATUSES:
            raise ValueError(f"invalid status {self.status}; allowed={STRATEGY_STATUSES}")


def is_research_output(x: str) -> bool:
    return x in RESEARCH_OUTPUTS
