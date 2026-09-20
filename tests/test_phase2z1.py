"""Phase 2Z.1 — Yuanta API family disambiguation tests。"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, "src")

ROOT = Path(__file__).resolve().parents[1]


def _doc(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


# --- four families ---
def test_yuanta_leverage_api_separate_family():
    d = _doc("docs/integrations/yuanta/YUANTA_API_ARCHITECTURE.md")
    assert "Leveraged Trading" in d and "槓桿全球贏家" in d
    assert "SPARK" in d and "Legacy Quote" in d and "Legacy Trading" in d


def test_t_session_not_leverage_account():
    d = _doc("docs/integrations/yuanta/YUANTA_API_ARCHITECTURE.md")
    assert "T / T+1" in d and "session" in d.lower()
    assert "不是" in d  # T/T+1 不是一般期貨 vs 槓桿


def test_jnu_not_cfd():
    d = _doc("docs/integrations/yuanta/YUANTA_LEVERAGED_TRADING_API.md")
    assert "JNU" in d and "JPX Futures" in d
    assert "CFD" in d  # 明確寫 JNU 不是 CFD


def test_leveraged_api_not_core():
    d = _doc("docs/integrations/yuanta/YUANTA_LEVERAGED_TRADING_API.md")
    assert "DOCUMENTED_ONLY" in d or "OUT_OF_SCOPE" in d
    # SYSTEM_MANIFEST 標 primary_target_source: false
    m = yaml.safe_load((ROOT / "config/system_manifest.yaml").read_text(encoding="utf-8"))
    lev = m["integrations"]["yuanta"]["leveraged_trading"]
    assert lev["primary_target_source"] is False
    assert lev["current_status"] == "DOCUMENTED_ONLY"


def test_proprietary_leverage_pdf_excluded():
    exc = _doc("research/phase2/publication/PUBLICATION_EXCLUDE_MANIFEST.txt")
    assert "proprietary" in exc.lower() or "PDF" in exc or "WebView2" in exc


def test_webview2_not_broker_api():
    d = _doc("docs/integrations/yuanta/YUANTA_LEVERAGED_TRADING_API.md")
    assert "WebView2" in d and "UI_RUNTIME_DEPENDENCY" in d
