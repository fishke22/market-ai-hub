"""Phase 2Y-D — Yuanta futures COM interop tests（不執行真實 login）。"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, "src")

from market_ai_hub.integrations.yuanta.futures_com import (
    CLSID_STR,
    MKT_LOGON_T,
    MKT_LOGON_TP1,
    PROG_ID,
    require_32bit,
)

ROOT = Path(__file__).resolve().parents[1]
FCOM = (ROOT / "src/market_ai_hub/integrations/yuanta/futures_com.py").read_text(encoding="utf-8")
FAUTH = (ROOT / "src/market_ai_hub/integrations/yuanta/futures_auth_probe.py").read_text(encoding="utf-8")
DIAG = (ROOT / "src/market_ai_hub/integrations/yuanta/futures_com_diag.py").read_text(encoding="utf-8")


def _doc(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


# --- API split ---
def test_securities_uses_spark():
    d = _doc("docs/integrations/yuanta/YUANTA_SECURITIES_SPARK.md")
    assert "YuantaSparkAPITrader" in d and "pythonnet" in d


def test_futures_does_not_use_spark():
    d = _doc("docs/integrations/yuanta/YUANTA_FUTURES_COM.md")
    assert "SetMktLogon" in d          # futures 登入是 SetMktLogon
    assert "禁止" in d or "❌" in d    # 明確禁止用 Spark 登期貨
    assert "登期貨帳號" in d or "登期貨" in d


def test_futures_uses_com():
    d = _doc("docs/integrations/yuanta/YUANTA_API_ARCHITECTURE.md")
    assert "YuantaQuote" in d and ("ActiveX" in d or "OCX" in d or "Quote COM" in d)


# --- COM architecture ---
def test_futures_com_architecture_detected():
    assert "x86" in FCOM or "32-bit" in FCOM or "32bit" in FCOM.lower()
    assert "YuantaQuote_v2.1.2.9.ocx" in FCOM or "2.1.2.9" in FCOM


def test_futures_com_registration_check():
    # diagnostic 記錄 32-bit 註冊狀態
    assert "registered_32bit" in DIAG
    assert "KEY_WOW64_32KEY" in DIAG or "WOW64" in DIAG


def test_futures_no_spark_error_semantics():
    # 不沿用 Spark 0001/0102/0112
    for code in ("0001", "0102", "0112"):
        assert code not in FCOM


# --- auth safety ---
def test_futures_auth_getpass():
    assert "getpass" in FAUTH


def test_futures_auth_single_attempt():
    assert FAUTH.count(".login(") <= 1


def test_futures_login_requires_event_confirmation():
    assert "OnMktStatusChange" in FCOM and "wait_login" in FCOM


def test_futures_cleanup():
    assert "cleanup" in FCOM and "disconnect" in FCOM


# --- quote-only / no order ---
def test_futures_quote_no_order():
    for m in ("SendOrder", "SendFutureOrder", "CancelOrder", "ModifyOrder", "place_order",
              "order", "Order"):
        assert m not in FCOM.replace("YuantaOrderAPI", "") or m == "order"


# --- symbol no guess ---
def test_futures_symbol_no_guess():
    assert "OSE:NK225MC1!" not in FCOM
    assert "FUT_225MC" not in FCOM


# --- docs / manifest ---
def test_yuanta_docs_api_split():
    nav = _doc("docs/integrations/yuanta/YUANTA_SETUP_AND_LOGIN.md")
    assert "SECURITIES" in nav and "FUTURES" in nav
    assert "0112" in nav  # decision tree 明確寫 0112 = wrong API family


def test_system_manifest_yuanta_split():
    d = yaml.safe_load((ROOT / "config/system_manifest.yaml").read_text(encoding="utf-8"))
    yuanta = d["integrations"]["yuanta"]
    assert yuanta["spark"]["securities"]["auth_verified"] is True
    assert yuanta["spark"]["futures"]["status"] in ("NEEDS_ACCOUNT_API_PERMISSION", "CONTRADICTION")
    assert yuanta["futures_quote_com"]["interop"] == "COMTYPES_32BIT"


def test_publication_manifest_contains_yuanta_docs():
    pub = (ROOT / "research/phase2/publication/PUBLICATION_FILE_MANIFEST.txt").read_text(encoding="utf-8")
    for d in ("YUANTA_SETUP_AND_LOGIN.md", "YUANTA_SECURITIES_SPARK.md",
              "YUANTA_FUTURES_COM.md", "YUANTA_FUTURES_ERROR_CODES.md"):
        assert d in pub
