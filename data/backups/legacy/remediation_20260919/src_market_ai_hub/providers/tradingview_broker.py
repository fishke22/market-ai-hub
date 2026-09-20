"""TradingView / Broker 介面（spec §16）。禁止 scraping / 逆向 / websocket 竊取。

enabled=false。未來若使用者提供合法 TradingView integration / 合法 broker feed /
官方 API / 合法 MCP 再實作。
"""
from __future__ import annotations

from market_ai_hub.providers.base import BaseProvider, ProviderInfo, ProviderStatus


class TradingViewProvider(BaseProvider):
    name = "tradingview"

    def __init__(self) -> None:
        self.enabled = False

    def status(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            status=ProviderStatus.DISABLED,
            message="NO_SCRAPING: 禁止 scraping/逆向/websocket。等待合法 integration 授權",
        )

    def fetch(self, symbol: str, **kwargs):
        raise RuntimeError("tradingview disabled: 需要合法授權的 integration")


class BrokerProvider(BaseProvider):
    name = "broker"

    def __init__(self) -> None:
        self.enabled = False  # NO LIVE TRADING / NO BROKER API

    def status(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            status=ProviderStatus.DISABLED,
            message="NO_BROKER_BY_POLICY: 本專案無 broker/order 能力",
        )

    def fetch(self, symbol: str, **kwargs):
        raise RuntimeError("broker disabled: 本系統禁止 broker 連線與下單")
