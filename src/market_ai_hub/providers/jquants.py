"""J-Quants adapter（Phase 2B：支援 Free tier；Premium 仍需自購）。

- Free plan：JPY 0，資料有約 12 週延遲，端點有限（不含 Futures OHLC）。
- Light/Standard/Premium 需自購（本專案不購買）。
- 標記：delay_status=FREE_PLAN_LIMITED；data_grade=OFFICIAL_DELAYED。
- 不得把 J-Quants Free 當 OSE 即時期貨來源。
"""
from __future__ import annotations

import logging

from market_ai_hub.config.settings import get_secret
from market_ai_hub.providers.base import BaseProvider, ProviderError, ProviderInfo, ProviderStatus
from market_ai_hub.providers.http_client import RateLimitedClient

log = logging.getLogger(__name__)

BASE_URL = "https://api.jquants.com/v1"


class JQuantsProvider(BaseProvider):
    name = "jquants"

    def __init__(self) -> None:
        self.client = RateLimitedClient(self.name, max_retries=3, default_ttl=86400)
        self._token = ""

    def status(self) -> ProviderInfo:
        if not get_secret("JQUANTS_API_KEY"):
            return ProviderInfo(name=self.name, status=ProviderStatus.NEEDS_CONFIG,
                                message="JQUANTS_API_KEY 未設定（Free plan 需自備免費 key）")
        return ProviderInfo(name=self.name, status=ProviderStatus.OK,
                            message="Free plan：delayed（~12 週），端點有限")

    def _auth_headers(self) -> dict:
        key = get_secret("JQUANTS_API_KEY")
        if not key:
            raise ProviderError("JQUANTS_API_KEY not set")
        if not self._token:
            import httpx

            r = httpx.post(f"{BASE_URL}/token/getpw", json={"mailaddress": key.split(":")[0], "password": key.split(":")[1]}, timeout=30.0)
            r.raise_for_status()
            self._token = r.json().get("refreshToken", "")
        return {"Authorization": f"Bearer {self._token}"}

    def fetch(self, endpoint: str, params: dict | None = None) -> dict:
        """呼叫 J-Quants API（Free plan 可用端點）。回傳 JSON dict。"""
        headers = self._auth_headers()
        return self.client.get_json(f"jq_{endpoint}_{params}", f"{BASE_URL}/{endpoint}",
                                    params=params, headers=headers, ttl=86400)
