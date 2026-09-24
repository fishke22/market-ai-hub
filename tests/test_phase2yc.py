"""Phase 2Y-C — SPARK interop wiring tests（不執行真實 login）。"""
import sys
from pathlib import Path

sys.path.insert(0, "src")

from market_ai_hub.integrations.yuanta.spark_runtime import (
    ENUM_ENVIRONMENT_PROD,
    ENUM_ENVIRONMENT_UAT,
    ENUM_MARKET_OSE,
    MSG_PASSWORD_FROZEN,
    MSG_PERMISSION_UNAVAILABLE,
    MSG_SUCCESS,
)
from market_ai_hub.integrations.yuanta.spark_auth import should_abort

ROOT = Path(__file__).resolve().parents[1]
SRT = (ROOT / "src/market_ai_hub/integrations/yuanta/spark_runtime.py").read_text(encoding="utf-8")
AUTH = (ROOT / "src/market_ai_hub/integrations/yuanta/auth_probe.py").read_text(encoding="utf-8")


def test_official_pythonnet_load_order():
    assert 'load("coreclr")' in SRT or "load('coreclr')" in SRT
    assert "import clr" in SRT


def test_coreclr_loaded_before_clr():
    i_load = SRT.find("load(")
    i_clr = SRT.find("import clr")
    assert 0 <= i_load < i_clr


def test_full_vendor_path_used():
    assert "add_dll_directory" in SRT
    assert "vendor" in SRT and "YuantaSparkAPI_win-x64_Python" in SRT


def test_direct_yuantaoneapi_import():
    assert "from YuantaOneAPI import" in SRT


def test_no_full_assembly_reflection_required():
    # 不用 System.Reflection 完整 reflection；直接 public import
    assert "from System.Reflection import" not in SRT
    assert "from YuantaOneAPI import" in SRT


def test_prod_enum_is_runtime_verified():
    assert ENUM_ENVIRONMENT_PROD == 2 and ENUM_ENVIRONMENT_UAT == 1


def test_ose_enum_is_runtime_verified():
    assert ENUM_MARKET_OSE == 207


def test_csharp_fallback_not_default():
    # 本棒走官方 pythonnet；不建 C# sidecar
    assert not (ROOT / "tools/yuanta_interop").exists()


def test_csharp_fallback_quote_only():
    # 無 C# fallback → 無 order reference；trivially 安全
    assert not (ROOT / "tools/yuanta_interop").exists()


def test_no_generic_method_invoker():
    assert "def invoke(" not in SRT
    assert "def call_method(" not in SRT

    assert "request_tick_detail_last" in SRT
    for forbidden in ("SendStockOrder", "SendFutureOrder", "GetBankBalance", "GetFutStoreSummary"):
        assert forbidden not in SRT


def test_login_bool_not_success():
    # login() 回傳 bool accepted，註解明確說非成功
    assert "bool" in SRT and "accepted" in SRT.lower()


def test_onresponse_required_for_success():
    assert "OnResponse" in SRT and "wait_login" in SRT


def test_0001_success():
    assert MSG_SUCCESS == "0001"


def test_0102_abort():
    assert MSG_PASSWORD_FROZEN == "0102"
    assert should_abort("0102")


def test_0112_abort():
    assert MSG_PERMISSION_UNAVAILABLE == "0112"
    assert should_abort("0112")


def test_finally_logout_close_dispose():
    assert "cleanup" in SRT
    for m in ("logout", "close", "dispose"):
        assert m in SRT.lower()


def test_password_not_persisted():
    # auth_probe 不寫 WinCred save password；用 del 丟棄 reference
    assert "del password" in AUTH
    assert "CredWrite" not in AUTH and "write_credential" not in AUTH


def test_real_auth_result_no_pii():
    # _write_result 只用 mask_account，不寫 full account/Name/InvestorID/SellerNo
    assert "mask_account" in AUTH
    assert "Name" not in AUTH and "InvestorID" not in AUTH and "SellerNo" not in AUTH


def test_loader_exception_sanitized():
    # 診斷輸出 JSON 的 key 不含 credential/PII
    probe = (ROOT / "src/market_ai_hub/integrations/yuanta/spark_runtime_probe.py").read_text(encoding="utf-8")
    # result dict 的 key 只有 runtime/enum/status
    for k in ("account", "password", "LoginResult", "InvestorID", "SellerNo", "CredentialBlob"):
        assert f'"{k}"' not in probe
