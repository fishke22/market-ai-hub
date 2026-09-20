"""Phase 2T — TradingViewResearchBridge（whitelisted optional bridge）。

只允許白名單 capability：health / chart state / symbol metadata / quote snapshot /
OHLCV summary / indicator snapshot / screenshot metadata / Pine research /
Strategy Tester summary / Replay research state。

禁止：place_order / broker_login / replay_trade / alert mutation / watchlist mutation /
generic ui_evaluate / arbitrary JavaScript。即使 upstream 有 ui_evaluate 也不暴露。

TradingView 關閉時 get_analysis_packet 仍正常（OPTIONAL_UNAVAILABLE，不 BLOCK 核心）。
"""
from __future__ import annotations

import yaml
from abc import ABC, abstractmethod
from pathlib import Path

from market_ai_hub.config.settings import project_root

# 資料語義（§13）
TRADINGVIEW_SOURCE = "TRADINGVIEW_OPTIONAL_UI"
OPTIONAL_EXTERNAL_UI_SOURCE = "OPTIONAL_EXTERNAL_UI_SOURCE"

# 白名單 capability（§11）
ALLOWED_CAPABILITIES = [
    "health", "chart_state", "symbol_metadata", "quote_snapshot", "ohlcv_summary",
    "indicator_snapshot", "screenshot_metadata", "pine_research",
    "strategy_tester_summary", "replay_state",
]

# 明確禁止（即使 upstream 有也不暴露）
FORBIDDEN_CAPABILITIES = [
    "place_order", "broker_login", "replay_trade", "alert_mutation",
    "watchlist_mutation", "ui_evaluate", "arbitrary_javascript",
]


class TradingViewConfig:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or project_root() / "config" / "tradingview.yaml"
        self.data = yaml.safe_load(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    @property
    def enabled(self) -> bool:
        return bool(self.data.get("enabled", False))

    def capability(self, name: str) -> bool:
        return bool(self.data.get("capabilities", {}).get(name, False))


class TradingViewResearchBridge(ABC):
    """whitelisted optional bridge。預設 disabled；使用者明確啟用才用。"""

    source = TRADINGVIEW_SOURCE
    authority = OPTIONAL_EXTERNAL_UI_SOURCE

    @abstractmethod
    def health(self) -> dict:
        ...

    @abstractmethod
    def get_chart_state(self) -> dict:
        ...

    @abstractmethod
    def get_symbol_metadata(self, symbol: str) -> dict:
        ...

    @abstractmethod
    def get_quote_snapshot(self, symbol: str) -> dict:
        ...

    @abstractmethod
    def get_ohlcv_summary(self, symbol: str) -> dict:
        ...

    @abstractmethod
    def get_indicator_snapshot(self) -> dict:
        ...

    @abstractmethod
    def capture_screenshot(self) -> dict:
        ...

    @abstractmethod
    def run_pine_research(self) -> dict:
        ...

    @abstractmethod
    def get_strategy_tester_summary(self) -> dict:
        ...

    @abstractmethod
    def get_replay_state(self) -> dict:
        ...

    # 明確不存在的 methods（§11/§9）：
    #   place_order / broker_login / replay_trade / alert_mutation /
    #   watchlist_mutation / ui_evaluate / arbitrary_javascript
