"""Provider registry：統一列出所有 data source 狀態（graceful degradation 核心）。"""
from __future__ import annotations

from market_ai_hub.providers.base import ProviderInfo, ProviderStatus
from market_ai_hub.providers.finmind import FinMindProvider
from market_ai_hub.providers.fred import FredProvider
from market_ai_hub.providers.jquants import JQuantsProvider
from market_ai_hub.providers.tradingview_broker import BrokerProvider, TradingViewProvider
from market_ai_hub.providers.twse import TWSEProvider
from market_ai_hub.providers.yfinance_provider import YFinanceProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self.providers = {
            "twse": TWSEProvider(),
            "finmind": FinMindProvider(),
            "fred": FredProvider(),
            "yfinance": YFinanceProvider(),
            "jquants": JQuantsProvider(),
            "tradingview": TradingViewProvider(),
            "broker": BrokerProvider(),
        }

    def status_all(self) -> dict[str, ProviderInfo]:
        return {name: p.status() for name, p in self.providers.items()}

    def get(self, name: str):
        return self.providers[name]
