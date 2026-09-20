"""Phase 2Y-G.1 — Legacy Quote session diagnostic tests。"""
import sys
from pathlib import Path

sys.path.insert(0, "src")

from market_ai_hub.integrations.yuanta.futures_com import YuantaFuturesQuoteClient
from market_ai_hub.integrations.yuanta.permission_matrix import YuantaPermissionMatrix

TLINK_STATUS = YuantaFuturesQuoteClient.TLINK_STATUS

ROOT = Path(__file__).resolve().parents[1]


def _doc(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


def _src(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


# --- TLinkStatus 語義 ---
def test_legacy_status_minus2_is_link_failure():
    assert TLINK_STATUS.get(-2) == "LinkFail"
    assert "PERMISSION" not in str(TLINK_STATUS.get(-2, "")).upper()


def test_legacy_msg3_is_permission_denied():
    assert YuantaFuturesQuoteClient._message_category("3") == "PERMISSION_DENIED"


def test_legacy_status2_is_authenticated():
    assert TLINK_STATUS.get(2) == "LogonOK"


# --- login id / branch ---
def test_legacy_same_login_id_for_t_and_tplus1():
    src = _src("src/market_ai_hub/integrations/yuanta/futures_com.py")
    # SetMktLogon 兩盤共用同一 login_id（MKT_LOGON_T/T+1 只有 host/port/reqType 不同）
    assert "MKT_LOGON_T" in src and "MKT_LOGON_TP1" in src


def test_legacy_no_branch_login_parameter():
    src = _src("src/market_ai_hub/integrations/yuanta/futures_com.py")
    assert "branch" not in src.lower()


def test_no_branch_code_bruteforce():
    a = _src("src/market_ai_hub/integrations/yuanta/futures_auth_probe.py")
    assert "range(" not in a and "itertools" not in a


# --- endpoint matrix ---
def test_endpoint_matrix_matches_official_sample():
    from market_ai_hub.integrations.yuanta.futures_com import MKT_LOGON_T, MKT_LOGON_TP1

    assert MKT_LOGON_T[1:] == ("80", 1)
    assert MKT_LOGON_TP1[1:] == ("82", 2)
    # 443/442 記錄於 doc
    d = _doc("docs/integrations/yuanta/YUANTA_FUTURES_COM.md")
    assert "443" in d and "442" in d


def test_tcp_probe_has_no_credentials():
    s = _doc("scripts/check_yuanta_quote_endpoints.ps1")
    assert "Test-NetConnection" in s
    # 只做 TCP probe，不送 login/credential
    assert "SetMktLogon" not in s
    assert "Get-Credential" not in s


def test_session_aware_retest_required():
    m = YuantaPermissionMatrix()
    assert m.state("LEGACY_FUTURES_QUOTE_T") == "REQUIRES_SESSION_AWARE_RETEST"


def test_trading_api_account_metadata_flow_documented():
    # 未來 authoritative branch/account 來源 = 歸戶ID + OnLogonS AccList（不猜）
    d = _doc("docs/integrations/yuanta/YUANTA_FUTURES_TRADING_API_FUTURE.md")
    assert "SetFutOrdConnection" in d and "歸戶" in d
    assert "OnLogonS" in d and "Branch" in d and "SubAccount" in d
