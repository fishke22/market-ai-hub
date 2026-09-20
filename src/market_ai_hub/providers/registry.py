"""Provider registry：統一列出所有 data source 狀態（graceful degradation 核心）。"""
from __future__ import annotations

from market_ai_hub.providers.base import ProviderInfo, ProviderStatus
from market_ai_hub.providers.boj import BojProvider
from market_ai_hub.providers.cftc_cot import CftcCotProvider
from market_ai_hub.providers.finmind import FinMindProvider
from market_ai_hub.providers.fred import FredProvider
from market_ai_hub.providers.jquants import JQuantsProvider
from market_ai_hub.providers.taifex import TaifexProvider
from market_ai_hub.providers.tradingview_broker import BrokerProvider, TradingViewProvider
from market_ai_hub.providers.twse import TWSEProvider
from market_ai_hub.providers.ustreasury import USTreasuryProvider
from market_ai_hub.providers.yfinance_provider import YFinanceProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self.providers = {
            "twse": TWSEProvider(),
            "finmind": FinMindProvider(),
            "fred": FredProvider(),
            "yfinance": YFinanceProvider(),
            "taifex": TaifexProvider(),
            "boj": BojProvider(),
            "ustreasury": USTreasuryProvider(),
            "cftc_cot": CftcCotProvider(),
            "jquants": JQuantsProvider(),
            "tradingview": TradingViewProvider(),
            "broker": BrokerProvider(),
        }

    def status_all(self, deep: bool = False) -> dict[str, ProviderInfo]:
        """provider 狀態。deep=False（預設）用 shallow（不 network probe），deep=True 才 live probe。"""
        if deep:
            return {name: p.status() for name, p in self.providers.items()}
        return {name: p.status_shallow() for name, p in self.providers.items()}

    def get(self, name: str):
        return self.providers[name]
