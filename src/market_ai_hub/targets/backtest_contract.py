"""Phase 2G.1 — Backtest Contract（8）+ MCP policy（9）。

- 保留 FEV / OOS / Walk-forward / Forward Paper 作模型預測驗證。
- NautilusTraderAdapter 為 interface，本棒不啟用 Live Execution。
- Forecast Evaluation ≠ Trading Strategy Backtest。
- TradingView Strategy Tester 只能 SECONDARY_VALIDATION。
- 不新增大量外部 MCP；官方 API 做 MARKET_AI_HUB provider。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

FORECAST_EVALUATION = "FORECAST_EVALUATION"
STRATEGY_BACKTEST = "STRATEGY_BACKTEST"
SECONDARY_VALIDATION = "SECONDARY_VALIDATION"

# 預留 market-ai tools（不新增大量外部 MCP；TradingView 保持 OPTIONAL）
RESERVED_MARKET_AI_TOOLS = [
    "get_data_coverage",
    "get_event_calendar",
    "get_official_release_snapshot",
    "get_target_instrument_state",
]


class NautilusTraderAdapter(ABC):
    """NautilusTrader strategy backtest interface（本棒不啟用 Live Execution）。"""

    live_execution_enabled: bool = False

    @abstractmethod
    def load_data(self, *args, **kwargs):
        ...

    @abstractmethod
    def run_backtest(self, *args, **kwargs):
        ...

    @abstractmethod
    def load_strategy(self, *args, **kwargs):
        ...


def evaluation_kind(uses_trading_simulator: bool) -> str:
    """Forecast Evaluation 與 Strategy Backtest 是不同東西。"""
    return STRATEGY_BACKTEST if uses_trading_simulator else FORECAST_EVALUATION


def tradingview_tester_role() -> str:
    return SECONDARY_VALIDATION
