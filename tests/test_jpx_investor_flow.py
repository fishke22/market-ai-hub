from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_ai_hub.targets.jpx_investor_flow import (
    JPX_INVESTOR_FLOW_SCHEMA_VERSION,
    JPXInvestorFlowProvider,
    parse_jpx_2026_investor_flow_csv,
)


HEADER = (
    '"帳票種別 Product type","サイクル区分 Cycle","年月週 Year, Month, Week",'
    '"報告年月日（自）Period covered - from","報告年月日（至）Period covered - to",'
    '"投資部門コード Type of Investor","数量金額区分 Volume/Value",'
    '"売 Sales","売-差引 Balance","買 Purchases","買-差引 Balance","合計 Total"'
)


def _official_csv(period_to: str = "20260911") -> str:
    return "\n".join(
        [
            HEADER,
            f'"331","1","2026092","20260907","{period_to}","60","1",'
            '"5380786","0","5382462","1676","10763248"',
            f'"331","1","2026092","20260907","{period_to}","51","1",'
            '"1554899","2001","1552898","0","3107797"',
            f'"331","1","2026092","20260907","{period_to}","32","1",'
            '"12376","0","12900","524","25276"',
            f'"331","1","2026092","20260907","{period_to}","99","1",'
            '"10","0","12","2","22"',
            f'"331","1","2026092","20260907","{period_to}","60","2",'
            '"100","0","101","1","201"',
            f'"301","1","2026092","20260907","{period_to}","60","1",'
            '"123","0","124","1","247"',
        ]
    )


def test_parse_official_jpx_micro_weekly_receipt_time():
    retrieved = datetime(2026, 9, 17, 4, 30, tzinfo=timezone.utc)
    rows = parse_jpx_2026_investor_flow_csv(
        _official_csv(),
        source_url="https://example.invalid/Tousi_DV_W_20260907_20260911.csv",
        retrieved_at=retrieved,
    )
    assert len(rows) == 4
    assert {row.product_code for row in rows} == {"331"}
    assert {row.investor_code for row in rows} == {"60", "51", "32", "99"}
    labels = {row.investor_code: row.investor_type for row in rows}
    assert labels["60"] == "foreigners"
    assert labels["51"] == "individuals"
    assert labels["32"] == "business_companies"
    assert labels["99"] == "JPX_INVESTOR_CODE_99"
    foreign = next(row for row in rows if row.investor_code == "60")
    assert foreign.sell_volume == 5380786
    assert foreign.buy_volume == 5382462
    assert foreign.net_volume == 1676
    assert foreign.published_at == ""
    assert foreign.available_at == retrieved.isoformat()
    assert (
        foreign.availability_semantics
        == "RECEIPT_TIME_ONLY_PUBLICATION_TIMESTAMP_UNVERIFIED"
    )
    assert foreign.source_schema_version == JPX_INVESTOR_FLOW_SCHEMA_VERSION


def test_official_jpx_parser_fails_closed_on_schema_shift():
    raw = _official_csv().replace('"合計 Total"', '"Renamed Total"')
    with pytest.raises(ValueError, match="schema mismatch"):
        parse_jpx_2026_investor_flow_csv(
            raw,
            source_url="https://example.invalid/x.csv",
            retrieved_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
        )


def test_official_jpx_parser_requires_timezone_aware_receipt():
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_jpx_2026_investor_flow_csv(
            _official_csv(),
            source_url="https://example.invalid/x.csv",
            retrieved_at=datetime(2026, 9, 17),
        )


def test_official_jpx_parser_rejects_future_period():
    with pytest.raises(ValueError, match="future period"):
        parse_jpx_2026_investor_flow_csv(
            _official_csv(period_to="20260918"),
            source_url="https://example.invalid/x.csv",
            retrieved_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
        )


def test_discover_latest_weekly_csv(monkeypatch):
    provider = JPXInvestorFlowProvider()
    html = """
    <a href="/a/Tousi_DV_W_20260831_20260904.csv">old</a>
    <a href="/b/Tousi_DV_W_20260907_20260911.csv">new</a>
    """
    monkeypatch.setattr(provider, "_get_text", lambda url: html)
    assert provider.discover_latest_weekly_csv().endswith(
        "/b/Tousi_DV_W_20260907_20260911.csv"
    )


def test_provider_fetch_uses_receipt_time_and_official_parser(monkeypatch):
    provider = JPXInvestorFlowProvider()
    source = "https://example.invalid/Tousi_DV_W_20260907_20260911.csv"
    monkeypatch.setattr(provider, "discover_latest_weekly_csv", lambda: source)
    monkeypatch.setattr(provider, "_get_text", lambda url: _official_csv())
    retrieved = datetime(2026, 9, 17, 4, 30, tzinfo=timezone.utc)
    rows = provider.fetch(retrieved_at=retrieved)
    assert rows
    assert all(row.source_url == source for row in rows)
    assert all(row.available_at == retrieved.isoformat() for row in rows)
    assert all(row.product_code == "331" for row in rows)
