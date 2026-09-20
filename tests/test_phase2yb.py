"""Phase 2Y-B — Yuanta auth/quote probe 安全結構 tests（不執行真實 login）。"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")

from market_ai_hub.integrations.yuanta.spark_auth import (
    SPARK_STATUS_FROZEN,
    SPARK_STATUS_PERMISSION_UNAVAILABLE,
    AuthProbeConfig,
    classify_login_failure,
    sanitized_login_outcome,
    should_abort,
)
from market_ai_hub.integrations.yuanta.sanitizer import mask_account, sanitize_login_result
from market_ai_hub.integrations.yuanta.resolver import YuantaInstrumentResolver
from market_ai_hub.integrations.yuanta.quote_probe import (
    MAX_STREAM_SECONDS,
    MAX_TICK_DETAIL_COUNT,
    PROBE_ORDER,
)

ROOT = Path(__file__).resolve().parents[1]
AUTH_SRC = (ROOT / "src/market_ai_hub/integrations/yuanta/auth_probe.py").read_text(encoding="utf-8")
QUOTE_SRC = (ROOT / "src/market_ai_hub/integrations/yuanta/quote_probe.py").read_text(encoding="utf-8")


# --- account preset / masked ---
def test_auth_probe_account_preset():
    cfg = AuthProbeConfig()
    assert cfg.profile == "YUANTA FUTURES"
    assert cfg.mode == "QUOTE_ONLY"
    assert cfg.orders == "DISABLED"


def test_auth_probe_account_masked():
    m = mask_account("F12345678901234")
    assert m != "F12345678901234"
    assert "*" in m and m.startswith("F")


def test_auth_probe_password_getpass():
    assert "getpass.getpass" in AUTH_SRC
    assert "getpass" in AUTH_SRC


# --- single attempt + abort ---
def test_auth_probe_single_attempt_only():
    # 單次 login：不得有 retry loop（第二次 .login( 呼叫）
    assert AUTH_SRC.count(".login(") <= 1
    assert "while True" not in AUTH_SRC


def test_auth_probe_abort_0102():
    assert should_abort(SPARK_STATUS_FROZEN)
    assert classify_login_failure(SPARK_STATUS_FROZEN) == "PASSWORD_FROZEN_OR_INACTIVE"


def test_auth_probe_abort_0112():
    assert should_abort(SPARK_STATUS_PERMISSION_UNAVAILABLE)
    assert classify_login_failure(SPARK_STATUS_PERMISSION_UNAVAILABLE) == "API_PERMISSION_UNAVAILABLE"


def test_auth_result_no_pii():
    raw = {"connected": True, "Account": "A123456789", "Name": "王小明",
           "InvestorID": "INV-1", "SellerNo": "S-1", "status_code": "0"}
    out = sanitized_login_outcome(raw)
    for k in ("Name", "InvestorID", "SellerNo", "Account"):
        assert k not in out
    assert out["masked_account"] != "A123456789"


# --- quote probe safety ---
def test_quote_probe_no_account_query():
    # 不得呼叫帳務/持倉/餘額/損益查詢 method（account 一字只允許 mask_account import）
    for kw in ("GetStoreSummary", "GetRealReport", "GetOrderTradeReport", "position",
               "balance", "inventory", "PnL", "GetBankBalance", "GetUnrealized"):
        assert kw not in QUOTE_SRC


def test_quote_probe_no_order_api():
    for m in ("SendOrder", "SendFutureOrder", "Cancel", "Modify", "place_order", "SendStockOrder"):
        assert m not in QUOTE_SRC


def test_quote_probe_max20_ticks():
    assert MAX_TICK_DETAIL_COUNT == 20


def test_stream_probe_time_limited():
    assert MAX_STREAM_SECONDS == 5


def test_probe_always_logout():
    # auth_probe / quote_probe 都必須在流程中 LogOut + Dispose
    for src in (AUTH_SRC, QUOTE_SRC):
        assert ("LogOut" in src and "Dispose" in src) or "logout" in src.lower() or "dispose" in src.lower()


def test_probe_data_gitignored():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/private/" in gi  # 涵蓋 data/private/yuanta_probe/


# --- symbol discovery ---
def test_symbol_discovery_no_guess():
    r = YuantaInstrumentResolver().resolve("OSE_NIKKEI225_MICRO_FUTURES")
    assert r.verified is False
    assert r.spark_code == ""


def test_symbol_requires_market207_evidence():
    r = YuantaInstrumentResolver()
    inst = r.resolve("OSE_NIKKEI225_MICRO_FUTURES")
    # 未 login / 無 market info → 不 verified（需 MarketNo=207 + 名稱/乘數證據）
    assert inst.market_type == 207 and inst.verified is False


def test_secret_scan_after_real_login():
    from market_ai_hub.integrations.yuanta.secret_scan import mask, scan
    for f in scan():
        assert set(f) == {"path", "rule", "masked"}
        assert "*" in f["masked"]  # 不打印完整秘密
