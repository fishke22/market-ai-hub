"""Phase 2F — TradingView Optional Bridge（M/N）— 僅 integration contract / interface。

定位：OPTIONAL_RESEARCH_TOOL（chart state / indicator values / screenshot /
Pine Script / Strategy Tester / Bar Replay）。不自動安裝、不取 cookie/password/session secret。
不得作為核心 training datasource、不得取代官方 providers、不依賴 TradingView 才能分析。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

# 資料來源標記：來自 TradingView 的資料必須標此，不得混入 authoritative training dataset。
OPTIONAL_EXTERNAL_UI_SOURCE = "OPTIONAL_EXTERNAL_UI_SOURCE"


class TradingViewResearchBridge(ABC):
    """預留 interface。本棒不實作、不安裝。"""

    @abstractmethod
    def health(self) -> dict:
        ...

    @abstractmethod
    def get_chart_state(self) -> dict:
        ...

    @abstractmethod
    def get_indicator_snapshot(self) -> dict:
        ...

    @abstractmethod
    def capture_chart(self) -> bytes:
        ...

    @abstractmethod
    def run_pine_research(self) -> dict:
        ...

    @abstractmethod
    def get_strategy_tester_summary(self) -> dict:
        ...

    # 明確禁止（不存在以下方法）：
    #   place_order / broker_order / automated execution
