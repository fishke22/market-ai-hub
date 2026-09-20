"""Phase 2B — 共用 HTTP client（cache + retry + exponential backoff）。

- 合理 cache（TTL），避免重複呼叫
- retry + exponential backoff（有上限，不得無限制重試）
- 失敗拋 ProviderError（graceful degradation 由 provider 處理）
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from market_ai_hub.config.settings import project_root
from market_ai_hub.config.runtime_paths import data_root
from market_ai_hub.providers.base import ProviderError

log = logging.getLogger(__name__)


class RateLimitedClient:
    def __init__(self, name: str, max_retries: int = 3, base_backoff: float = 1.0,
                 max_backoff: float = 30.0, default_ttl: int = 3600) -> None:
        self.name = name
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self.default_ttl = default_ttl
        self.cache_dir = data_root() / "cache" / name  # lazy：尊重 test isolation env
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{h}.json"

    def _cache_hit(self, path: Path, ttl: int | None) -> str | None:
        if ttl is None:
            return None
        if path.exists():
            age = time.time() - path.stat().st_mtime
            if age <= ttl:
                try:
                    return path.read_text(encoding="utf-8")
                except Exception:
                    return None
        return None

    def request(self, key: str, url: str, params: dict | None = None, headers: dict | None = None,
                ttl: int | None = None, text: bool = False) -> str:
        """GET 並回傳文字（json 或 text）。cache + retry + backoff。"""
        ttl = self.default_ttl if ttl is None else ttl
        path = self._cache_path(key)
        cached = self._cache_hit(path, ttl)
        if cached is not None:
            return cached

        backoff = self.base_backoff
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = httpx.get(url, params=params, headers=headers, timeout=30.0)
                resp.raise_for_status()
                body = resp.text
                if body.strip():  # 不 cache 空 body（避免 transient 空回應被 TTL 持久化）
                    path.write_text(body, encoding="utf-8")
                return body
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.warning("%s request failed (attempt %d/%d): %s", self.name, attempt, self.max_retries, e)
                if attempt < self.max_retries:
                    time.sleep(min(backoff, self.max_backoff))
                    backoff *= 2
        raise ProviderError(f"{self.name} request failed after {self.max_retries} retries: {last_err}")

    def get_json(self, key: str, url: str, params: dict | None = None, headers: dict | None = None,
                 ttl: int | None = None) -> dict | list:
        body = self.request(key, url, params=params, headers=headers, ttl=ttl)
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise ProviderError(f"{self.name} invalid JSON: {e}") from e

    def post(self, key: str, url: str, data: dict | None = None, headers: dict | None = None,
             ttl: int | None = None) -> str:
        """POST 並回傳文字（TAIFEX 等 form 提交場景）。cache + retry + backoff。"""
        ttl = self.default_ttl if ttl is None else ttl
        path = self._cache_path(key)
        cached = self._cache_hit(path, ttl)
        if cached is not None:
            return cached
        backoff = self.base_backoff
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = httpx.post(url, data=data, headers=headers, timeout=30.0)
                resp.raise_for_status()
                body = resp.text
                if body.strip():  # 不 cache 空 body
                    path.write_text(body, encoding="utf-8")
                return body
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.warning("%s post failed (attempt %d/%d): %s", self.name, attempt, self.max_retries, e)
                if attempt < self.max_retries:
                    time.sleep(min(backoff, self.max_backoff))
                    backoff *= 2
        raise ProviderError(f"{self.name} post failed after {self.max_retries} retries: {last_err}")
