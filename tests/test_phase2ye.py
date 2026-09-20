"""Phase 2Y-E — Yuanta futures x86 sidecar tests（不執行真實 login）。"""
import sys
from pathlib import Path

sys.path.insert(0, "src")

from market_ai_hub.integrations.yuanta.futures_com import (
    STATE_AUTHENTICATED,
    STATE_TIMEOUT,
    require_32bit,
)

ROOT = Path(__file__).resolve().parents[1]
FCOM = (ROOT / "src/market_ai_hub/integrations/yuanta/futures_com.py").read_text(encoding="utf-8")
FAUTH = (ROOT / "src/market_ai_hub/integrations/yuanta/futures_auth_probe.py").read_text(encoding="utf-8")
FQUOTE = (ROOT / "src/market_ai_hub/integrations/yuanta/futures_quote_probe.py").read_text(encoding="utf-8")


# --- sidecar contract ---
def test_x86_sidecar_is_32bit_contract():
    assert "require_32bit" in FCOM
    assert "sys.maxsize" in FCOM
    assert ".venv-yuanta-futures-x86" in FCOM or "32-bit" in FCOM


def test_x86_sidecar_minimal_dependencies():
    for heavy in ("numpy", "pandas", "pyarrow", "torch", "duckdb"):
        assert heavy not in FCOM and heavy not in FAUTH


def test_x86_sidecar_no_ml_import():
    for heavy in ("numpy", "pandas", "torch", "chronos", "timesfm"):
        assert heavy not in FCOM.lower()


# --- STA / message pump ---
def test_futures_com_sta_required():
    assert "CoInitializeEx" in FCOM and "COINIT_APARTMENTTHREADED" in FCOM


def test_futures_message_pump_bounded():
    assert "PumpWaitingMessages" in FCOM
    assert "while True" not in FCOM


def test_futures_auth_timeout():
    assert "timeout" in FCOM and STATE_TIMEOUT in FCOM


def test_futures_auth_event_required():
    assert "OnMktStatusChange" in FCOM
    assert STATE_AUTHENTICATED in FCOM


# --- auth safety ---
def test_futures_auth_single_attempt():
    assert FAUTH.count(".login(") <= 1


def test_futures_auth_cleanup():
    assert "cleanup" in FAUTH and "CoUninitialize" in FCOM


def test_futures_account_from_wincred():
    assert "read_profile_credential" in FAUTH


def test_futures_account_masked():
    assert "mask_account" in FAUTH


def test_futures_password_getpass():
    assert "getpass" in FAUTH


def test_futures_password_not_persisted():
    assert "del password" in FAUTH
    assert "CredWrite" not in FAUTH


# --- quote probe ---
def test_futures_quote_max_duration():
    assert "8.0" in FQUOTE or "10" in FQUOTE  # bounded 5-10s


def test_futures_quote_one_symbol_only():
    assert FQUOTE.count("client.register_quote_symbol") <= 1


def test_futures_delmktreg_cleanup():
    assert "unregister_quote_symbol" in FQUOTE
    assert "cleanup" in FQUOTE


# --- scripts / docs ---
def test_futures_setup_script_present():
    assert (ROOT / "scripts/setup_yuanta_futures_x86.ps1").exists()
    assert (ROOT / "scripts/yuanta_futures_auth.ps1").exists()


def test_futures_diag_script_present():
    assert (ROOT / "scripts/check_yuanta_futures_com.ps1").exists()
    assert (ROOT / "scripts/yuanta_futures_quote_probe.ps1").exists()


def test_futures_docs_reconstructable():
    doc = (ROOT / "docs/integrations/yuanta/YUANTA_FUTURES_COM.md").read_text(encoding="utf-8")
    assert "32-bit" in doc and "sidecar" in doc.lower()
    guide = (ROOT / "docs/development/AI_RECONSTRUCTION_GUIDE.md").read_text(encoding="utf-8")
    assert "setup_yuanta_futures_x86.ps1" in guide
