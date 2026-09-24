"""Phase 2Y-G.3 — Yuanta secret normalization + EasyWin legacy namespace tests."""
from __future__ import annotations

import inspect
import sys
from datetime import date

import pytest

sys.path.insert(0, "src")

from market_ai_hub.integrations.yuanta.capabilities import PROVIDER_STATUS
from market_ai_hub.integrations.yuanta.credential_store import (
    CredentialBackendError,
    normalize_credential_secret,
)
from market_ai_hub.integrations.yuanta.easwin_resolver import (
    NAMESPACE_LEGACY_EASYWIN,
    NAMESPACE_SPARK,
    LegacyEasyWinResolver,
)


# ── UTF-16 WinCred secret normalization ──
def test_normalize_credential_secret_str_passthrough():
    assert normalize_credential_secret("hunter2") == "hunter2"
    assert normalize_credential_secret("") == ""


def test_normalize_credential_secret_utf16le_decodes():
    assert normalize_credential_secret("pw123456".encode("utf-16-le")) == "pw123456"
    assert normalize_credential_secret(bytearray("abc".encode("utf-16-le"))) == "abc"


def test_normalize_credential_secret_strips_trailing_nul():
    assert normalize_credential_secret("pw\x00".encode("utf-16-le")) == "pw"
    assert normalize_credential_secret("pw\x00\x00".encode("utf-16-le")) == "pw"


def test_normalize_credential_secret_odd_length_fails_closed():
    with pytest.raises(CredentialBackendError):
        normalize_credential_secret(b"\x01\x02\x03")


def test_normalize_credential_secret_wrong_type_fails_closed():
    with pytest.raises(CredentialBackendError):
        normalize_credential_secret(12345)
    with pytest.raises(CredentialBackendError):
        normalize_credential_secret(None)


def test_normalize_credential_secret_never_mutates_input():
    raw = "pw".encode("utf-16-le")
    normalize_credential_secret(raw)
    assert raw == "pw".encode("utf-16-le")


# ── login wiring: user / password sources ──
def test_legacy_auth_probe_uses_login_id_and_futures_secret():
    from market_ai_hub.integrations.yuanta import futures_auth_probe

    src = inspect.getsource(futures_auth_probe)
    assert 'read_profile_credential("legacy_login_id")' in src       # user = legacy login ID
    assert 'read_profile_password("futures")' in src                 # password = futures secret
    assert 'read_profile_credential("futures")' not in src


def test_legacy_quote_probe_uses_login_id_and_futures_secret():
    from market_ai_hub.integrations.yuanta import futures_quote_probe

    src = inspect.getsource(futures_quote_probe)
    assert 'read_profile_credential("legacy_login_id")' in src
    assert 'read_profile_password("futures")' in src
    assert 'read_profile_credential("futures")' not in src


def test_spark_auth_probe_uses_normalized_profile_secret():
    from market_ai_hub.integrations.yuanta import auth_probe

    src = inspect.getsource(auth_probe)
    assert "read_profile_password(args.profile)" in src


def test_wincred_and_getpass_sources_are_mutually_exclusive_fallbacks():
    from market_ai_hub.integrations.yuanta import futures_auth_probe, futures_quote_probe

    for mod in (futures_auth_probe, futures_quote_probe):
        src = inspect.getsource(mod)
        assert "getpass.getpass" in src          # fallback preserved
        assert "read_profile_password" in src    # WinCred preferred when present


# ── AddMktReg ReqType follows session ──
def test_req_type_follows_session():
    from market_ai_hub.integrations.yuanta.futures_quote_probe import REQ_TYPE_SESSIONS

    assert REQ_TYPE_SESSIONS["T"] == 1
    assert REQ_TYPE_SESSIONS["TPLUS1"] == 2


def test_legacy_quote_probe_no_longer_hardcodes_req_type_1():
    from market_ai_hub.integrations.yuanta import futures_quote_probe

    src = inspect.getsource(futures_quote_probe)
    assert "REQ_TYPE_SESSIONS" in src
    assert "register_quote_symbol(args.symbol, \"1\", 1)" not in src
    assert "req_type" in src


def test_err_code_not_interpreted():
    from market_ai_hub.integrations.yuanta import futures_quote_probe

    src = inspect.getsource(futures_quote_probe)
    assert "意" not in src or "UNKNOWN" in src          # ErrCode meaning stays UNKNOWN
    assert "reg_error_codes" in src
    assert "AUTH_VERIFIED_REGISTRATION_UNRESOLVED" in src


# ── EasyWin day / PM separation ──
def _resolve_or_skip():
    r = LegacyEasyWinResolver()
    if not r.available():
        pytest.skip("EasyWin M.TFX.TXT not present on this machine")
    return r


def test_easwin_day_and_pm_symbols_are_separated():
    r = _resolve_or_skip()
    day, pm = r.day_symbols(), r.pm_symbols()
    assert day and pm
    assert not any(s.endswith("PM") for s in day)
    assert all(s.endswith("PM") for s in pm)
    assert set(day).isdisjoint(set(pm))


def test_easwin_resolution_follows_session():
    r = _resolve_or_skip()
    for order, root in (("TMF", "TMF"), ("TX", "TXF"), ("MTX", "MXF")):
        d = r.resolve_quote_symbol(order, "T", asof=date(2026, 9, 24))
        p = r.resolve_quote_symbol(order, "T+1", asof=date(2026, 9, 24))
        assert d and d.startswith(root) and not d.endswith("PM")
        assert p == d + "PM"


def test_easwin_resolution_is_asof_aware():
    r = _resolve_or_skip()
    assert r.resolve_quote_symbol("TMF", "T", asof=date(2026, 9, 24)) is not None
    assert r.resolve_quote_symbol("TMF", "T", asof=date(2030, 1, 1)) is None


def test_easwin_unknown_order_code_returns_none():
    r = _resolve_or_skip()
    assert r.resolve_quote_symbol("JNU", "T") is None
    assert r.resolve_quote_symbol("NOPE", "T") is None


# ── SPARK / Legacy namespace separation ──
def test_spark_and_legacy_namespaces_cannot_mix():
    r = _resolve_or_skip()
    assert r.is_legacy_symbol("JNU2612") is False    # OSE is NOT in the legacy domestic list
    assert r.is_legacy_symbol("MNIK") is False       # SPARK CME code
    assert r.is_legacy_symbol("TMFJ6") is True
    assert r.is_legacy_symbol("TMFJ6PM") is True
    ns = r.namespaces()
    assert ns["SPARK"] != ns["LEGACY_EASYWIN"] != ns["TRADING_ORDER"]
    assert NAMESPACE_SPARK == "SPARK" and NAMESPACE_LEGACY_EASYWIN == "LEGACY_EASYWIN"


def test_spark_resolver_unchanged_by_legacy_resolver():
    from market_ai_hub.integrations.yuanta.resolver import YuantaInstrumentResolver

    ose = YuantaInstrumentResolver().resolve("OSE_NIKKEI225_MICRO_FUTURES", asof=date(2026, 9, 24))
    assert ose.market_type == 207
    # legacy resolver must not claim the OSE code
    r = LegacyEasyWinResolver()
    assert r.is_legacy_symbol(ose.spark_code or "JNU2612") is False


# ── machine-readable provider status ──
def test_provider_status_machine_readable():
    assert PROVIDER_STATUS["legacy_futures_auth"] == "VERIFIED"
    assert PROVIDER_STATUS["legacy_domestic_quote"] == "AUTH_VERIFIED_REGISTRATION_UNRESOLVED"
    assert PROVIDER_STATUS["spark_futures"] == "EXTERNAL_ENTITLEMENT_RETEST_REQUIRED"
    assert PROVIDER_STATUS["ose_micro_live"] == "NOT_AVAILABLE"
    assert PROVIDER_STATUS["taifex_live"] == "NOT_AVAILABLE_UNTIL_CALLBACK"
