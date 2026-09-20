"""Phase 2G.2 — official data live activation tests。

unit（mocked）tests 不需網路；live smoke tests（@pytest.mark.live）預設排除，
以 `-m live` 執行，網路失敗時 skip（避免 CI flaky）。
"""
import io
import sys
from datetime import datetime, timezone

import openpyxl
import pandas as pd
import pytest

sys.path.insert(0, "src")

from market_ai_hub.targets.coverage import LiveCoverageAuditor, LIVE_VERIFIED, CONTRACT_ONLY, NEEDS_CONFIG
from market_ai_hub.targets.events import OfficialEvent, event_visible, official_event_providers
from market_ai_hub.targets.jpx_investor_flow import parse_investor_flow_csv
from market_ai_hub.targets.jpx_market_data import parse_open_interest, parse_whole_day_volumes
from market_ai_hub.targets.jpx_settlement import PRODUCT_TOKENS, parse_settlement_csv
from market_ai_hub.targets.macro import BLSProvider, CboeVixProvider, PROVIDER_STATUS
from market_ai_hub.targets.release_time import (
    AS_KNOWN_AT_TIME, FIRST_RELEASE, REVISION_RISK, MacroObservation, as_known_at_time, revision_flag,
)
from market_ai_hub.targets.jpx_daily import MICRO_LISTING_DATE, assert_micro_not_before
from market_ai_hub.automation.incremental import missing_ranges


# ---------- helpers ----------
def _make_whole_day_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "market_data_Futures"
    ws.append(["OSE", "Index Futures", "日経225マイクロ先物\nNikkei 225 Micro Futures", "夜間 Night", 348668.0, "－", 225441451600.0, "－"])
    ws.append([None, None, None, "前場 Morning", 156839.0, None, 101183759100.0, None])
    ws.append([None, None, None, "後場 Afternoon", 248283.0, None, 161369170000.0, None])
    ws.append([None, None, None, "合計 Total", 753790.0, None, 487994380700.0, None])
    ws.append(["OSE", "Index Futures", "日経225先物\nNikkei 225 Futures", "夜間 Night", 6616.0, 437.0, 427619918400.0, 28231408400.0])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _make_oi_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "デリバティブ建玉残高状況"
    ws.append(["日経225マイクロ先物", None, None, None])
    ws.append(["2026年12月限", 687327, 54688, -5472, 60160])
    ws.append(["2026年10月限", 58673, 7368, -390, 7758])
    ws.append(["TOPIX Futures", None, None, None])  # 非日經 header → 停止歸屬
    ws.append(["2026年12月限", 999, 999, 0, 0])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


SETTLE_CSV = (
    "銘柄コード,銘柄名称,PUT/CAL,限月,権利行使価格,清算価格,理論価格,原資産価格,ボラティリティ,金利,残日数,原資産名称\n"
    "161120018,FUT_225_261210,,202612,,65100,65100,65018.95,,1.6469,84,日経225\n"
    "161120099,FUT_225M_261210,,202612,,65080,65080,65018.95,,1.6469,84,日経225\n"
    "161120100,FUT_225MC_261210,,202612,,65055,65055,65018.95,,1.6469,84,日経225\n"
)


def _net_skip():
    try:
        import httpx
        httpx.get("https://www.jpx.co.jp/", timeout=5)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"network unavailable: {e}")


# ---------- 1/2: JPX settlement ----------
def test_JPX_settlement_csv():
    rows = parse_settlement_csv(SETTLE_CSV.encode("shift_jis"), date="20260918")
    micro = [r for r in rows if r.product == "Nikkei 225 Micro Futures"]
    assert len(micro) == 1 and micro[0].contract == "202612" and micro[0].settlement_price == 65055.0
    assert set(PRODUCT_TOKENS) == {"FUT_225MC", "FUT_225M", "FUT_225"}


def test_settlement_not_close():
    # settlement 是清算價，與 OHLC close 分開（不存在 open/high/low 欄位）
    rows = parse_settlement_csv(SETTLE_CSV.encode("shift_jis"))
    assert len(rows) == 3
    for r in rows:
        assert r.final_settlement_price is None  # 最終清算值非此 CSV 欄位，不假造
    assert not hasattr(rows[0], "close")


def test_JPX_micro_listing_date():
    with pytest.raises(Exception):
        assert_micro_not_before("2023-05-28")
    assert_micro_not_before("2023-05-29")


# ---------- 1: whole_day + open interest xlsx ----------
def test_JPX_xlsx_whole_day_parser():
    vols = parse_whole_day_volumes(_make_whole_day_xlsx(), date="20260918")
    micro = [v for v in vols if "Micro" in v.product]
    assert len(micro) == 4  # night/morning/afternoon/total
    assert micro[0].session == "night" and micro[0].volume == 348668.0


def test_JPX_open_interest_parser():
    ois = parse_open_interest(_make_oi_xlsx(), date="20260918")
    micro = [o for o in ois if "Micro" in o.product]
    assert len(micro) == 2  # 2 個契約月；TOPIX 之後停止歸屬
    assert micro[0].open_interest == 54688


# ---------- 4: investor flow ----------
def test_JPX_investor_flow_parser():
    csv = ("period,product,investor_type,buy_volume,sell_volume,published_at,available_at\n"
           "2026-09,日経225系,foreign,1000,800,2026-09-19,2026-09-19\n")
    rows = parse_investor_flow_csv(csv)
    assert rows[0].net_volume == 200
    assert rows[0].product_aggregation != ""  # 無法單獨辨識 Micro → 標 aggregation


# ---------- 6: macro ----------
def test_BLS_live_parse():
    def fake_post(u, json):
        return {"Results": {"series": [
            {"seriesID": "CUUR0000SA0", "data": [
                {"year": "2024", "period": "M08", "periodName": "August", "value": "314.796"}]}]}}
    rows = BLSProvider().fetch(["CUUR0000SA0"], "2024", "2024", post=fake_post)
    assert rows[0].series_id == "CUUR0000SA0" and rows[0].value == 314.796


def test_Fed_calendar_parse():
    # Fed 是官方事件來源（FOMC calendar）；以 event_visible 驗證 release-time 語義
    fomc = OfficialEvent(event_name="FOMC", scheduled_at=datetime(2024, 6, 12, tzinfo=timezone.utc),
                         released_at=datetime(2024, 6, 12, 18, 0, tzinfo=timezone.utc), source="FED")
    cutoff = datetime(2024, 6, 12, 12, 0, tzinfo=timezone.utc)
    assert event_visible([fomc], cutoff) == []  # release 18:00 > cutoff 12:00
    assert event_visible([fomc], datetime(2024, 6, 13, tzinfo=timezone.utc)) == [fomc]


def test_BOJ_provider():
    assert "BOJ" in official_event_providers()
    assert PROVIDER_STATUS["BOJ"] == "LIVE_VERIFIED"


def test_MOF_intervention():
    providers = official_event_providers()
    assert "MOF" in providers
    assert any("intervention" in s.lower() for s in providers["MOF"].series)


def test_Cboe_VIX_parser():
    csv = ("Date,OPEN,HIGH,LOW,CLOSE\n2024-01-02,13.5,14.0,13.0,13.8\n2024-01-03,13.8,14.2,13.5,14.0\n")
    df = CboeVixProvider().fetch(getter=lambda u: csv.encode())
    assert len(df) == 2 and df["CLOSE"].iloc[-1] == 14.0


# ---------- 7: release time ----------
def test_release_time_no_lookahead():
    obs = MacroObservation(series_id="CPI", observation_period="2024-08", value=314.796,
                           actual_release_time=datetime(2024, 9, 11, 12, 30, tzinfo=timezone.utc),
                           has_historical_vintage=True)
    # 8 月 CPI 在 8 月看不見（release 在 9/11）
    assert as_known_at_time(obs, datetime(2024, 8, 31, tzinfo=timezone.utc))["available"] is False
    assert as_known_at_time(obs, datetime(2024, 9, 12, tzinfo=timezone.utc))["available"] is True


def test_revision_risk():
    obs = MacroObservation(series_id="CPI", observation_period="2024-08", value=314.796,
                           actual_release_time=datetime(2024, 9, 11, tzinfo=timezone.utc),
                           revision_policy=FIRST_RELEASE, has_historical_vintage=False)
    assert revision_flag(obs) == REVISION_RISK  # 無 vintage → 不得假稱 point-in-time perfect


# ---------- 8: incremental + cache ----------
def test_incremental_fetch():
    # 只補 missing range，不重抓已覆蓋區段
    gaps = missing_ranges(("2024-01-10", "2024-01-20"), ("2024-01-01", "2024-01-31"))
    assert gaps == [("2024-01-01", "2024-01-09"), ("2024-01-21", "2024-01-31")]
    assert missing_ranges(("2024-01-01", "2024-01-31"), ("2024-01-05", "2024-01-10")) == []


def test_cache_reuse(tmp_path):
    from market_ai_hub.automation.incremental import dedupe_and_write
    df = pd.DataFrame({"a": [1, 2, 3]})
    p = tmp_path / "c.parquet"
    n1, h1 = dedupe_and_write(p, df, ["a"])
    n2, h2 = dedupe_and_write(p, df, ["a"])  # 內容相同 → hash 不變，不重寫
    assert h1 == h2


# ---------- 9: coverage live status ----------
def test_coverage_live_status():
    recs = LiveCoverageAuditor().audit_osaka()
    statuses = {r.status for r in recs}
    assert LIVE_VERIFIED in statuses or CONTRACT_ONLY in statuses
    # 至少部分缺口被真實標記
    assert any(r.status in (CONTRACT_ONLY, NEEDS_CONFIG, "MISSING") for r in recs)


# ---------- live smoke（網路，預設排除；-m live 執行）----------
@pytest.mark.live
def test_live_smoke_jpx_micro():
    _net_skip()
    from market_ai_hub.targets.jpx_settlement import JPXSettlementProvider
    from market_ai_hub.targets.jpx_market_data import JPXMarketDataProvider
    import httpx
    d = "20260918"
    getter = lambda u: httpx.get(u, timeout=30, follow_redirects=True).content
    rows = JPXSettlementProvider().fetch_parse(d, getter=getter)
    assert any(r.product == "Nikkei 225 Micro Futures" for r in rows)
    vols = JPXMarketDataProvider().fetch_whole_day(d, getter=getter)
    assert any("Micro" in v.product for v in vols)


@pytest.mark.live
def test_live_smoke_bls():
    _net_skip()
    try:
        rows = BLSProvider().fetch(["CUUR0000SA0"], "2024", "2024")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"BLS unavailable: {e}")
    assert len(rows) > 0


@pytest.mark.live
def test_live_smoke_cboe():
    _net_skip()
    df = CboeVixProvider().fetch()
    assert len(df) > 100


@pytest.mark.live
def test_live_smoke_edgar():
    _net_skip()
    from market_ai_hub.targets.macro import SecEdgarProvider
    filings = SecEdgarProvider().recent_filings("0000320193")
    assert len(filings) > 0
