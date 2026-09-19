"""J-Quants adapter（spec §15A）。DO NOT PURCHASE — enabled=false 預設。

Free: JPY 0（資料有 12-week delay）
Light: 約 JPY 1,650/月、Standard: 約 JPY 3,300/月、Premium: 約 JPY 16,500/月
Futures OHLC 需 Premium。
"""
from __future__ import annotations

from market_ai_hub.providers.base import BaseProvider, ProviderInfo, ProviderStatus


class JQuantsProvider(BaseProvider):
    name = "jquants"

    def __init__(self) -> None:
        self.enabled = False  # 未購買，永遠 disabled

    def status(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            status=ProviderStatus.DISABLED,
            message="DO_NOT_PURCHASE_PHASE1: 需自備 API key 且 Fututes OHLC 為 Premium。見 docs/PAID_DATA_OPTIONS.md",
        )

    def fetch(self, symbol: str, **kwargs):
        raise RuntimeError("jquants disabled: 本階段不購買任何付費資料")
