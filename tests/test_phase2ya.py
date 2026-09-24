"""Phase 2Y-A — Yuanta credential / boundary / resolver / secret-scan tests。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")

from market_ai_hub.integrations.yuanta.credential_store import (
    CRED_TARGET_FUTURES,
    CredentialBackendError,
    read_credential,
    write_credential,
)
from market_ai_hub.integrations.yuanta.sanitizer import (
    SENSITIVE_FIELDS,
    assert_no_sensitive,
    mask_account,
    sanitize_login_result,
)
from market_ai_hub.integrations.yuanta.gateway import YuantaQuoteOnlyGateway
from market_ai_hub.integrations.yuanta.resolver import YuantaInstrumentResolver, function_list_path
from market_ai_hub.integrations.yuanta.contracts import OSE_MARKET_TYPE
from market_ai_hub.integrations.yuanta.function_list import find_overseas_futures, parse_market_enum

ROOT = Path(__file__).resolve().parents[1]


# --- credential backend ---
def test_wincred_backend_contract():
    import market_ai_hub.integrations.yuanta.credential_store as cs
    # 只允許 Windows Credential Manager（win32cred）
    import inspect
    src = inspect.getsource(cs._require_wincred)
    assert "win32cred" in src  # backend 鎖定 win32cred，非 keyring
    assert "fail-closed" in src or "CredentialBackendError" in src


def test_credential_no_plaintext():
    # 原始碼不得 hardcode 密碼字串（password= 帶真實值）
    import re
    for p in ROOT.rglob("*.py"):
        if "site-packages" in str(p) or ".venv" in str(p):
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        # 排除測試檔案自己用的 FAKE 值
        if "test_phase2ya" in str(p):
            continue
        assert not re.search(r"(?i)password\s*=\s*['\"][^'\"]{4,}", txt), f"plaintext password in {p}"


def test_credential_fake_roundtrip(monkeypatch):
    fake = {}

    def fake_write(cred):
        fake[cred["TargetName"]] = (cred["UserName"], cred["CredentialBlob"])

    def fake_read(target, ttype):
        if target not in fake:
            raise Exception("not found")
        return {"UserName": fake[target][0], "CredentialBlob": fake[target][1]}

    import market_ai_hub.integrations.yuanta.credential_store as cs
    monkeypatch.setattr(cs, "_require_wincred", lambda: None)
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, "win32cred", SimpleNamespace(CredWrite=fake_write, CredRead=fake_read))

    write_credential(CRED_TARGET_FUTURES, "FAKE_USER", "FAKE_PASSWORD")
    c = read_credential(CRED_TARGET_FUTURES)
    assert c.username == "FAKE_USER" and c.password == "FAKE_PASSWORD"


def test_credential_log_redaction():
    from market_ai_hub.integrations.yuanta.logger import SafeYuantaLogger
    lg = SafeYuantaLogger()
    out = lg._redact("login account=REAL123456 password=hunter2 InvestorID=INV-1")
    assert "hunter2" not in out and "REAL123456" not in out


# --- sanitizer ---
def test_login_result_sanitizer():
    raw = {"connected": True, "Account": "A123456789", "Name": "王小明",
           "InvestorID": "INV-999", "SellerNo": "S-1", "status_code": 0}
    out = sanitize_login_result(raw)
    assert "Name" not in out and "InvestorID" not in out and "SellerNo" not in out
    assert out["masked_account"] != "A123456789"


def test_no_name_in_mcp():
    raw = {"Name": "王小明", "connected": True}
    assert "Name" in assert_no_sensitive(raw)
    out = sanitize_login_result(raw)
    assert "Name" not in out


def test_no_investorid_in_mcp():
    raw = {"InvestorID": "INV-1", "connected": True}
    out = sanitize_login_result(raw)
    assert "InvestorID" not in out


# --- quote gateway no order ---
def test_quote_gateway_no_order_methods():
    g = YuantaQuoteOnlyGateway()
    for m in ("send_order", "send_future_order", "cancel", "modify", "place_order",
              "account_query", "position_query", "login", "subscribe"):
        assert not hasattr(g, m)
    assert g.quote_only is True
    assert g.realtime_recorder_enabled is False


def test_order_api_exposure_guard():
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard
    r = OrderApiExposureGuard().scan()
    assert r["gate"] == "PASS"  # 架構上無 order method


# --- resolver ---
def test_instrument_resolver_from_functionlist():
    if function_list_path() is None:
        pytest.skip("vendor FunctionList absent (fail-closed)")
    r = YuantaInstrumentResolver().resolve("OSE_NIKKEI225_MICRO_FUTURES")
    assert r.verified is True  # 2Y-G.2: FunctionList 股票代碼總表 已含 OSE(207) JNU<YYMM>
    assert r.spark_code.startswith("JNU")


def test_market_enum_local_validation():
    r = YuantaInstrumentResolver()
    assert r.ose_market_type() == OSE_MARKET_TYPE == 207


def test_capability_unknown_before_login():
    from market_ai_hub.integrations.yuanta.capabilities import capability
    c = capability("WATCHLIST_FIELDS")
    assert c.status == "UNKNOWN"  # 未 login 前不標 SUPPORTED_BY_ACCOUNT


def test_function_list_parser(tmp_path):
    import openpyxl
    p = tmp_path / "FunctionList.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "市場類"
    ws.append(["市場代碼", "市場名稱"])
    ws.append(["1", "TWSE"])
    ws.append(["207", "OSE"])
    ws2 = wb.create_sheet("股票代碼總表")
    ws2.append(["市場別", "市場代碼", "商品代碼", "商品名稱"])
    ws2.append(["CME", "203", "MNIK", "微型日經"])
    wb.save(p)
    enum = parse_market_enum(p)
    assert enum.get("OSE") == 207
    ov = find_overseas_futures(p)
    assert any(r["code"] == "MNIK" for r in ov)


# --- gitignore / secret scan ---
def test_vendor_gitignored():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "vendor/" in gi
    assert "*.dll" in gi
    assert "*.pfx" in gi


def test_secret_scan_masked_output():
    from market_ai_hub.integrations.yuanta.secret_scan import mask, scan
    assert mask("A123456789") != "A123456789"
    assert "*" in mask("A123456789")
    findings = scan()
    # 不應包含真實秘密內容；只驗證回傳結構
    for f in findings:
        assert set(f) == {"path", "rule", "masked"}
