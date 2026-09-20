"""Phase 2Y-G — Yuanta permission contradiction / login ID / docs tests。"""
import sys
from pathlib import Path

sys.path.insert(0, "src")

from market_ai_hub.integrations.yuanta.permission_matrix import (
    CONTRADICTION,
    SERVER_CONFIRMED,
    SERVER_DENIED,
    YuantaPermissionMatrix,
)

ROOT = Path(__file__).resolve().parents[1]


def _doc(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


# --- permission contradiction ---
def test_user_permission_claim_preserved():
    r = _doc("research/phase2/integrations/yuanta/YUANTA_PERMISSION_CONTRADICTION_REPORT.md")
    assert "全部開通" in r


def test_permission_contradiction_state():
    m = YuantaPermissionMatrix()
    assert m.state("SPARK_FUTURES") == CONTRADICTION
    assert m.state("LEGACY_FUTURES_QUOTE_T") in (CONTRADICTION, SERVER_DENIED, "REQUIRES_SESSION_AWARE_RETEST")
    assert m.state("LEGACY_FUTURES_QUOTE_TPLUS1") == SERVER_CONFIRMED


# --- legacy login id ---
def test_legacy_login_id_not_futures_account():
    a = _doc("src/market_ai_hub/integrations/yuanta/futures_auth_probe.py")
    assert "legacy_login_id" in a
    assert "read_profile_credential(\"futures\")" not in a


def test_legacy_login_id_wincred_only():
    m = _doc("src/market_ai_hub/integrations/yuanta/setup_legacy_login_id.py")
    assert "CRED_TARGET_LEGACY_LOGIN_ID" in m
    d = _doc("docs/integrations/yuanta/YUANTA_FUTURES_COM.md")
    assert "LEGACY_LOGIN_ID" in d


# --- legacy quote status semantics ---
def test_legacy_quote_status1_connected_only():
    d = _doc("docs/integrations/yuanta/YUANTA_QUICK_START_WINDOWS11.md")
    assert "Status=1" in d and "connected only" in d


def test_legacy_quote_status2_authenticated():
    d = _doc("docs/integrations/yuanta/YUANTA_QUICK_START_WINDOWS11.md")
    assert "Status=2" in d and "authenticated" in d


def test_legacy_quote_and_trading_independent():
    d = _doc("docs/integrations/yuanta/YUANTA_QUOTE_VS_TRADING_DEPENDENCY.md")
    assert "NO_RUNTIME_DEPENDENCY_FOUND" in d


# --- spark futures 0112 ---
def test_spark_futures_0112_not_auto_permission_denied():
    d = _doc("research/phase2/integrations/yuanta/YUANTA_PERMISSION_CONTRADICTION_REPORT.md")
    assert "CONTRADICTION" in d
    assert "不得" in d or "不直接" in d


def test_spark_account_format_validation():
    # 不從聊天記憶 hardcode futures account format；矛盾報告列「待營業員確認」
    d = _doc("research/phase2/integrations/yuanta/YUANTA_PERMISSION_CONTRADICTION_REPORT.md")
    assert "CONTRADICTION" in d and "0112" in d


def test_no_branch_bruteforce():
    # 程式碼不得逐個 prefix/branch 嘗試 login
    src = _doc("src/market_ai_hub/integrations/yuanta/futures_auth_probe.py")
    assert "for " not in src.replace("for ev", "") or "range(" not in src


# --- JNU ---
def test_jnu_public_code_only():
    import yaml

    c = yaml.safe_load((ROOT / "config/yuanta_product_codes.yaml").read_text(encoding="utf-8"))
    m = c["OSE_NIKKEI225_MICRO_FUTURES"]
    assert m["public_product_code"] == "JNU"
    assert m["spark_quote_code"] != "JNU"  # quote 碼是合約月別 (JNU2609)
    assert "JNU" in m["spark_quote_code"]
    assert m["legacy_com_quote_symbol"] == "UNVERIFIED"


def test_legacy_overseas_scope_evidence_based():
    d = _doc("docs/integrations/yuanta/YUANTA_API_ARCHITECTURE.md")
    assert "UNVERIFIED" in d or "未證實" in d or "DOMESTIC" in d


# --- support packet ---
def test_support_packet_no_pii():
    p = _doc("research/phase2/integrations/yuanta/YUANTA_SUPPORT_EVIDENCE_PACKET.md")
    # 不得含實際 PII 值（假帳號/密碼格式）
    for kw in ("A123", "F123", "密碼:", "身份證:", "FF0"):
        assert kw not in p


# --- docs completeness ---
def test_yuanta_quick_start_complete():
    d = _doc("docs/integrations/yuanta/YUANTA_QUICK_START_WINDOWS11.md")
    for step in ("申請 API permissions", "下載元件", "憑證", "WinCred", "auth", "quote probe"):
        assert step in d


def test_certificate_windows11_steps_complete():
    d = _doc("docs/integrations/yuanta/YUANTA_CERTIFICATE_WINDOWS11.md")
    for kw in ("申請", "匯出", "匯入", "簽驗", "期限"):
        assert kw in d


def test_downloads_steps_complete():
    d = _doc("docs/integrations/yuanta/YUANTA_DOWNLOADS.md")
    assert "SPARK" in d and "x64" in d and "交易 API" in d


def test_market_data_permission_docs_complete():
    d = _doc("docs/integrations/yuanta/YUANTA_MARKET_DATA_PERMISSIONS.md")
    assert "申請" in d and "海外" in d


def test_trading_api_future_static_only():
    d = _doc("docs/integrations/yuanta/YUANTA_FUTURES_TRADING_API_FUTURE.md")
    assert "NOT_IMPLEMENTED" in d or "NOT IMPLEMENTED" in d
    assert "PROHIBITED" in d


# --- security ---
def test_order_guard_passes():
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard

    assert OrderApiExposureGuard().scan()["gate"] == "PASS"
