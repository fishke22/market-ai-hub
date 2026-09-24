"""Phase 2Y-G.2 — Yuanta contract resolution tests (FunctionList authoritative, no guessing)."""
from __future__ import annotations

import inspect
import sys
from datetime import date

import pytest

sys.path.insert(0, "src")

from market_ai_hub.integrations.yuanta.resolver import (
    OSE_QUOTE_CODE_PATTERNS,
    YuantaInstrumentResolver,
    function_list_path,
    ose_last_trading_date,
    select_nearest_valid,
    taifex_last_trading_date,
)

OSE_MICRO_PAT = OSE_QUOTE_CODE_PATTERNS["OSE_NIKKEI225_MICRO_FUTURES"]


# ── pure selection logic (no vendor file needed) ──
def test_ose_expiry_rule_is_business_day_before_second_friday():
    # 2026-09: second Friday = 2026-09-11 -> last trading day = 2026-09-10 (Thu)
    assert ose_last_trading_date(2026, 9) == date(2026, 9, 10)
    # 2026-12: second Friday = 2026-12-11 -> 2026-12-10 (Thu)
    assert ose_last_trading_date(2026, 12) == date(2026, 12, 10)


def test_taifex_expiry_rule_is_third_wednesday():
    assert taifex_last_trading_date(2026, 9) == date(2026, 9, 16)
    assert taifex_last_trading_date(2026, 10) == date(2026, 10, 21)


def test_select_nearest_skips_expired_month():
    codes = ["JNU2609", "JNU2612", "JNU2703"]
    assert select_nearest_valid(codes, OSE_MICRO_PAT, ose_last_trading_date, date(2026, 9, 24)) == "JNU2612"
    assert select_nearest_valid(codes, OSE_MICRO_PAT, ose_last_trading_date, date(2026, 9, 1)) == "JNU2609"


def test_select_nearest_is_asof_dependent_not_hardcoded():
    codes = ["JNU2612", "JNU2703"]
    assert select_nearest_valid(codes, OSE_MICRO_PAT, ose_last_trading_date, date(2026, 9, 24)) == "JNU2612"
    assert select_nearest_valid(codes, OSE_MICRO_PAT, ose_last_trading_date, date(2027, 1, 5)) == "JNU2703"


def test_select_nearest_returns_none_when_all_expired():
    assert select_nearest_valid(["JNU2609"], OSE_MICRO_PAT, ose_last_trading_date, date(2026, 9, 24)) is None


def test_select_nearest_ignores_pm_variants_and_junk():
    codes = ["JNUPM2612", "JUNK", "JNU2612"]
    assert select_nearest_valid(codes, OSE_MICRO_PAT, ose_last_trading_date, date(2026, 9, 24)) == "JNU2612"


# ── resolver integration (uses vendor FunctionList when present; fail-closed otherwise) ──
def test_ose_micro_quote_code_is_jnu_yymm():
    r = YuantaInstrumentResolver()
    inst = r.resolve("OSE_NIKKEI225_MICRO_FUTURES", asof=date(2026, 9, 24))
    assert inst.market_type == 207
    if function_list_path() is None:
        assert inst.verified is False  # fail closed without the authoritative source
        return
    import re
    assert inst.verified is True
    assert re.fullmatch(r"JNU\d{4}", inst.spark_code), inst.spark_code


def test_ose_micro_quote_code_is_not_expired():
    if function_list_path() is None:
        pytest.skip("vendor FunctionList absent")
    inst = YuantaInstrumentResolver().resolve("OSE_NIKKEI225_MICRO_FUTURES", asof=date(2026, 9, 24))
    year, month = 2000 + int(inst.spark_code[3:5]), int(inst.spark_code[5:7])
    assert ose_last_trading_date(year, month) >= date(2026, 9, 24)


def test_ose_micro_quote_code_differs_from_order_code():
    r = YuantaInstrumentResolver()
    inst = r.resolve("OSE_NIKKEI225_MICRO_FUTURES", asof=date(2026, 9, 24))
    assert r.order_code("OSE_NIKKEI225_MICRO_FUTURES") == "JNU"
    if inst.verified:
        assert inst.spark_code != "JNU"          # order code is not a quote code
        assert inst.spark_code.startswith("JNU")


def test_ose_mini_large_resolve_to_numeric_quote_codes():
    if function_list_path() is None:
        pytest.skip("vendor FunctionList absent")
    r = YuantaInstrumentResolver()
    mini = r.resolve("OSE_NIKKEI225_MINI_FUTURES", asof=date(2026, 9, 24))
    large = r.resolve("OSE_NIKKEI225_LARGE_FUTURES", asof=date(2026, 9, 24))
    assert mini.verified and mini.spark_code.startswith("19")
    assert large.verified and large.spark_code.startswith("18")


def test_taifex_domestic_contract_resolved():
    if function_list_path() is None:
        pytest.skip("vendor FunctionList absent")
    r = YuantaInstrumentResolver()
    for name, prefix in (("TAIFEX_TX", "TXF"), ("TAIFEX_MTX", "MXF"), ("TAIFEX_TMF", "TMF")):
        inst = r.resolve(name, asof=date(2026, 9, 24))
        assert inst.market_type == 3
        assert inst.verified is True
        assert inst.spark_code.startswith(prefix)


def test_unknown_instrument_stays_unverified():
    inst = YuantaInstrumentResolver().resolve("NOT_A_REAL_INSTRUMENT")
    assert inst.verified is False


# ── legacy quote probe fixes ──
def test_legacy_quote_probe_uses_legacy_login_id():
    from market_ai_hub.integrations.yuanta import futures_quote_probe

    src = inspect.getsource(futures_quote_probe)
    assert 'read_profile_credential("legacy_login_id")' in src
    assert 'read_profile_credential("futures")' not in src
    assert "SetMktLogon" in src


def test_legacy_quote_probe_is_domestic_only():
    from market_ai_hub.integrations.yuanta.futures_quote_probe import _is_domestic_symbol

    assert _is_domestic_symbol("TMFJ6") is True
    assert _is_domestic_symbol("TXFJ6") is True
    assert _is_domestic_symbol("JNU2612") is False
    assert _is_domestic_symbol("OSE_NIKKEI225_MICRO_FUTURES") is False
    assert _is_domestic_symbol("") is False


def test_legacy_quote_probe_has_order_guard():
    from market_ai_hub.integrations.yuanta import futures_quote_probe

    assert "OrderApiExposureGuard" in inspect.getsource(futures_quote_probe)
