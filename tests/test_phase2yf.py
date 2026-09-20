"""Phase 2Y-F — Yuanta ground-truth / symbol resolution / docs tests。"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, "src")

ROOT = Path(__file__).resolve().parents[1]


def _doc(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


def _yaml(p: str) -> dict:
    return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))


# --- API family 修正 ---
def test_spark_supports_futures_by_official_contract():
    d = _doc("docs/integrations/yuanta/YUANTA_API_ARCHITECTURE.md")
    assert "Futures account" in d and "SPARK" in d


def test_spark_0112_means_permission_not_wrong_family():
    d = _doc("docs/integrations/yuanta/YUANTA_API_ARCHITECTURE.md")
    assert "0112" in d and "無此權限" in d


def test_yuanta_api_family_three_way_split():
    d = _doc("docs/integrations/yuanta/YUANTA_API_ARCHITECTURE.md")
    assert "SPARK" in d and "Quote COM" in d and "Trading API" in d


# --- JNU public code ---
def test_public_jnu_code_verified():
    c = _yaml("config/yuanta_product_codes.yaml")
    assert c["OSE_NIKKEI225_MICRO_FUTURES"]["public_product_code"] == "JNU"


def test_public_jnu_not_auto_quote_symbol():
    c = _yaml("config/yuanta_product_codes.yaml")
    m = c["OSE_NIKKEI225_MICRO_FUTURES"]
    assert m["public_product_code"] == "JNU"
    assert m["spark_quote_code"] != "JNU"  # quote 碼是合約月別 (JNU2609)，非裸 JNU
    assert "JNU" in m["spark_quote_code"]
    assert m["trading_order_code"] == "JNU"
    assert m["legacy_com_quote_symbol"] == "UNVERIFIED"


def test_legacy_com_scope_not_assumed():
    d = _doc("docs/integrations/yuanta/YUANTA_MARKET_DATA_PERMISSIONS.md")
    assert "DOMESTIC_ONLY" in d or "國內行情" in d


# --- docs completeness ---
def test_downloads_doc_complete():
    d = _doc("docs/integrations/yuanta/YUANTA_DOWNLOADS.md")
    assert "x64" in d and "交易 API" in d and "PUBLIC_PAGE_VERSION" in d


def test_certificate_doc_complete():
    d = _doc("docs/integrations/yuanta/YUANTA_CERTIFICATE_WINDOWS11.md")
    assert "憑證" in d and "Import" in d and "1 年" in d


def test_certificate_no_private_export():
    d = _doc("docs/integrations/yuanta/YUANTA_CERTIFICATE_WINDOWS11.md")
    assert "不得" in d or "不" in d
    script = _doc("scripts/check_yuanta_certificate.ps1")
    # 不得有私鑰匯出 cmdlet（Export-PfxCertificate）
    assert "Export-PfxCertificate" not in script
    assert "export-pfx" not in script.lower()


def test_permission_doc_complete():
    d = _doc("docs/integrations/yuanta/YUANTA_API_PERMISSIONS.md")
    assert "API 行情服務" in d and "API 交易服務" in d


def test_product_code_lookup_doc_complete():
    d = _doc("docs/integrations/yuanta/YUANTA_PRODUCT_CODE_LOOKUP.md")
    assert "下單代碼與訂閱報價商品代碼可能不同" in d or "JNU" in d


def test_trading_api_future_documented():
    d = _doc("docs/integrations/yuanta/YUANTA_FUTURES_TRADING_API_FUTURE.md")
    assert "1.6.1.3" in d and ("NOT_IMPLEMENTED" in d or "NOT IMPLEMENTED" in d)


def test_trading_api_not_runtime_imported():
    # 不得「定義/呼叫」order method（docstring 提到禁止清單不算）
    import re
    for p in (ROOT / "src/market_ai_hub/integrations/yuanta").rglob("*.py"):
        txt = p.read_text(encoding="utf-8", errors="replace")
        for pat in (r"def\s+send_(future_)?order", r"def\s+cancel", r"def\s+modify",
                    r"\.SendFutureOrder\(s", r"\.SendStockOrder\("):
            assert not re.search(pat, txt, re.I), f"{p.name} implements order API: {pat}"


def test_order_guard_still_passes():
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard

    assert OrderApiExposureGuard().scan()["gate"] == "PASS"


def test_publication_manifest_contains_all_yuanta_docs():
    pub = _doc("research/phase2/publication/PUBLICATION_FILE_MANIFEST.txt")
    for d in ("YUANTA_DOWNLOADS.md", "YUANTA_API_PERMISSIONS.md", "YUANTA_CERTIFICATE_WINDOWS11.md",
              "YUANTA_MARKET_DATA_PERMISSIONS.md", "YUANTA_PRODUCT_CODE_LOOKUP.md",
              "YUANTA_SUPPORT_CHECKLIST.md", "YUANTA_FUTURES_TRADING_API_FUTURE.md",
              "config/yuanta_official_sources.yaml", "config/yuanta_product_codes.yaml"):
        assert d in pub, f"missing in publication manifest: {d}"


def test_ai_reconstruction_yuanta_prerequisites():
    d = _doc("docs/development/AI_RECONSTRUCTION_GUIDE.md")
    assert "Apply API permission" in d and "Import certificate" in d and "WinCred" in d
