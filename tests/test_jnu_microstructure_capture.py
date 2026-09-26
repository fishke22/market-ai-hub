from types import SimpleNamespace

from market_ai_hub.integrations.yuanta import live_quote_recorder as R


def _t():
    return SimpleNamespace(bytHour=8, bytMin=45, bytSec=1, ushtMSec=250)


def test_extract_stock_tick_microstructure():
    obj = SimpleNamespace(
        StkCode="JNU2612",
        MarketType=207,
        Time=_t(),
        SerialNo=123,
        BuyPrice=66000,
        SellPrice=66005,
        DealPrice=66005,
        DealVol=3,
        InOutFlag=1,
        Type=0,
    )
    p = R._extract_payload(obj, "SubscribeStockTick")
    assert p["instrument_code"] == "JNU2612"
    assert p["market_no"] == 207
    assert p["microstructure_kind"] == "TRADE_TICK"
    assert p["SerialNo"] == 123
    assert p["DealVol"] == 3
    assert p["source_time_of_day"] == "08:45:01.250"


def test_extract_five_tick_full_first_five():
    nested = SimpleNamespace(**{
        **{f"BuyPrice{i}": 66000 - (i - 1) * 5 for i in range(1, 6)},
        **{f"BuyVol{i}": i * 10 for i in range(1, 6)},
        **{f"SellPrice{i}": 66005 + (i - 1) * 5 for i in range(1, 6)},
        **{f"SellVol{i}": i * 12 for i in range(1, 6)},
    })
    obj = SimpleNamespace(
        StkCode="JNU2612",
        MarketType=207,
        IndexFlag=50,
        IndexFlag_50=nested,
    )
    p = R._extract_payload(obj, "SubscribeFiveTickA")
    assert p["microstructure_kind"] == "DEPTH"
    assert p["depth_index_flag"] == 50
    assert p["bid_price_1"] == 66000
    assert p["bid_size_5"] == 50
    assert p["ask_price_1"] == 66005
    assert p["ask_size_5"] == 60


def test_jnu_microstructure_pairs_are_exact_and_bounded():
    cfg = {"jnu_microstructure": {"enabled": True, "market_no": 207, "code_prefix": "JNU", "max_contracts": 2}}
    pairs = [
        (207, "JNU2612", "ose_micro"),
        (207, "JNU2703", "ose_micro"),
        (207, "JNU_CONT", "bad"),
        (203, "NQ_202612", "nq"),
    ]
    assert R._jnu_microstructure_pairs(cfg, pairs) == [
        (207, "JNU2612", "ose_micro"),
        (207, "JNU2703", "ose_micro"),
    ]
