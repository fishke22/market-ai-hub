"""Phase 2B provider tests：contract / timestamp / available_at / delay /
fallback / rate limit / offline failure。"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from market_ai_hub.providers.base import ProviderError, ProviderStatus
from market_ai_hub.providers.contract import (
    PROVIDER_SPECS,
    DataProviderContract,
    make_contract,
    provider_spec,
)
from market_ai_hub.providers.http_client import RateLimitedClient


def test_contract_fields():
    c = make_contract("twse", "2330", event_time=datetime(2026, 9, 18, 5, 30, tzinfo=timezone.utc))
    d = c.model_dump()
    for k in ("source_name", "authority", "market", "instrument", "event_time", "source_timestamp",
              "received_at", "available_at", "freshness", "frequency", "data_grade",
              "license", "delay_status", "target_match", "information_cutoff_compatible"):
        assert k in d, k


def test_all_sources_have_spec():
    for name in ("twse", "finmind", "fred", "yfinance", "taifex", "boj", "ustreasury", "cftc_cot", "jquants"):
        assert name in PROVIDER_SPECS, name


def test_timestamp_normalization_and_available_at():
    naive = datetime(2026, 9, 18, 5, 30)  # naive
    c = make_contract("twse", "2330", source_timestamp=naive)
    assert c.source_timestamp.tzinfo is not None
    assert c.available_at.tzinfo is not None
    assert c.available_at == c.source_timestamp  # twse delay=0


def test_jquants_delayed_available_at():
    c = make_contract("jquants", "NK225M", source_timestamp=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert c.delay_status == "FREE_PLAN_LIMITED"
    assert c.data_grade == "OFFICIAL_DELAYED"
    assert c.available_at > c.source_timestamp  # 84 天延遲
    assert (c.available_at - c.source_timestamp).days >= 80


def test_delay_tagging():
    assert provider_spec("twse").delay_status == "REALTIME"
    assert provider_spec("cftc_cot").delay_status == "DELAYED"
    assert provider_spec("jquants").delay_status == "FREE_PLAN_LIMITED"
    assert provider_spec("yfinance").delay_status == "BEST_EFFORT"
    # yfinance 不得是交易所級
    assert provider_spec("yfinance").data_grade == "RESEARCH_PROXY"
    # jquants 不得是 OSE 即時期貨來源
    assert provider_spec("jquants").data_grade != "OFFICIAL_DAILY"


def test_source_fallback_registry():
    from market_ai_hub.providers.registry import ProviderRegistry

    reg = ProviderRegistry()
    names = set(reg.status_all().keys())
    assert {"twse", "finmind", "fred", "yfinance", "taifex", "boj", "ustreasury", "cftc_cot", "jquants"} <= names
    # yfinance 是 fallback（ok），jquants 需 key（needs_config）
    assert reg.get("yfinance").status().status == ProviderStatus.OK
    assert reg.get("jquants").status().status == ProviderStatus.NEEDS_CONFIG


def test_rate_limit_no_unlimited_retry(monkeypatch, tmp_path):
    import market_ai_hub.providers.http_client as hc

    calls = {"n": 0}

    class Boom:
        @staticmethod
        def get(url, params=None, headers=None, timeout=None):
            calls["n"] += 1
            raise RuntimeError("network down")

    monkeypatch.setattr(hc, "httpx", Boom())
    client = RateLimitedClient("t", max_retries=3, base_backoff=0.01, max_backoff=0.02, default_ttl=0)
    with pytest.raises(ProviderError):
        client.request("k", "http://x", ttl=0)
    assert calls["n"] == 3  # 恰好 max_retries 次，不得無限制重試


def test_cache_avoids_repeat_call(monkeypatch, tmp_path):
    import market_ai_hub.providers.http_client as hc

    calls = {"n": 0}

    class FakeResp:
        text = '{"a":1}'

        def raise_for_status(self):
            return None

    class Fake:
        @staticmethod
        def get(url, params=None, headers=None, timeout=None):
            calls["n"] += 1
            return FakeResp()

    monkeypatch.setattr(hc, "httpx", Fake())
    monkeypatch.setattr(hc, "data_root", lambda: tmp_path)
    client = RateLimitedClient("t", default_ttl=3600)
    client.get_json("k", "http://x")
    client.get_json("k", "http://x")
    assert calls["n"] == 1  # 第二次命中 cache


def test_offline_failure_raises_provider_error(monkeypatch, tmp_path):
    import market_ai_hub.providers.http_client as hc

    class Fake:
        @staticmethod
        def get(url, params=None, headers=None, timeout=None):
            raise ConnectionError("offline")

    monkeypatch.setattr(hc, "httpx", Fake())
    monkeypatch.setattr(hc, "data_root", lambda: tmp_path)
    client = RateLimitedClient("t", max_retries=2, base_backoff=0.01, default_ttl=0)
    with pytest.raises(ProviderError):
        client.request("k", "http://x", ttl=0)


def test_ustreasury_parse(monkeypatch, tmp_path):
    from market_ai_hub.providers.ustreasury import USTreasuryProvider

    csv = ('Date,"2 Yr","5 Yr","10 Yr","30 Yr"\n'
           '09/18/2026,4.76,4.86,5.01,5.34\n'
           '09/17/2026,4.67,4.78,4.94,5.29\n')
    import market_ai_hub.providers.http_client as hc

    monkeypatch.setattr(hc, "data_root", lambda: tmp_path)
    p = USTreasuryProvider()

    class FakeResp:
        def __init__(self, t):
            self.text = t

        def raise_for_status(self):
            return None

    class Fake:
        @staticmethod
        def get(url, params=None, headers=None, timeout=None):
            return FakeResp(csv)

    monkeypatch.setattr(hc, "httpx", Fake())
    df = p.fetch_daily_rates(2026)
    assert list(df.columns) == ["date", "dgs2", "dgs5", "dgs10", "dgs30", "source_name"]
    assert df.iloc[-1]["dgs10"] == 5.01


def test_jquants_free_needs_config(monkeypatch):
    from market_ai_hub.providers.jquants import JQuantsProvider

    monkeypatch.delenv("JQUANTS_API_KEY", raising=False)
    assert JQuantsProvider().status().status == ProviderStatus.NEEDS_CONFIG


def test_contract_information_cutoff_compatible():
    # 官方來源皆 compatible；delay 只影響 available_at，不影響 compatible
    for name in ("twse", "taifex", "boj", "ustreasury", "cftc_cot", "jquants", "fred", "finmind"):
        assert provider_spec(name).information_cutoff_compatible is True, name
