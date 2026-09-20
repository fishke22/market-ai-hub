"""Phase 2Y-H — Yuanta local SDK forensics static tests。"""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, "src")

ROOT = Path(__file__).resolve().parents[1]


def _doc(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


def _yaml(p: str) -> dict:
    return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))


def _json(p: str):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def test_local_sdk_inventory_schema():
    d = _json("tests/fixtures/yuanta_sdk_inventory.sample.json")
    assert "files" in d and isinstance(d["files"], list)
    f = d["files"][0]
    for k in ("root", "relative_path", "filename", "size", "modified_utc", "extension", "sha256"):
        assert k in f
    assert all(len(r.get("sha256", "")) == 64 for r in d["files"] if "sha256" in r)


def test_spark_jnu_code_verified():
    c = _yaml("config/yuanta_product_codes.yaml")
    m = c["OSE_NIKKEI225_MICRO_FUTURES"]
    assert m["spark_quote_code"] != "JNU"
    assert "JNU" in m["spark_quote_code"]
    assert m["trading_order_code"] == "JNU"
    assert m.get("verified") is True
    # 永久保存 source SHA256，防再誤判 UNRESOLVED
    assert c.get("functionlist_sha256") and len(c["functionlist_sha256"]) == 64
    assert c.get("verified_at")


def test_easywin_symbol_semantics_separate():
    d = _doc("docs/integrations/yuanta/YUANTA_EASYWIN_SYMBOL_MAPPING.md")
    assert "EASYWIN" in d and "UNRESOLVED" in d
    assert "JNU2609" in d and "SPARK" in d  # 三套 namespace 分離


def test_legacy_quote_symbol_not_guessed():
    c = _yaml("config/yuanta_product_codes.yaml")
    m = c["OSE_NIKKEI225_MICRO_FUTURES"]
    assert m["legacy_com_quote_symbol"] == "UNVERIFIED"  # 不得猜 EASYWIN 碼


def test_quote_login_id_contract():
    d = _doc("research/phase2/integrations/yuanta/PHASE2YH_LOCAL_SDK_FORENSICS_REPORT.md")
    assert "SetMktLogon" in d and "身份證ID" in d


def test_quote_status_contract():
    d = _doc("research/phase2/integrations/yuanta/PHASE2YH_LOCAL_SDK_FORENSICS_REPORT.md")
    assert "lsLogonOK" in d and "-2" in d
    assert "無權限" in d  # Msg[0]='3'


def test_trading_bitness_contract():
    c = _yaml("config/yuanta_product_codes.yaml")
    assert c["legacy_trading_progid_32"] == "Yuanta.YuantaOrdCtrl.1"
    assert c["legacy_trading_progid_64"] == "Yuanta.YuantaOrdCtrl.64"


def test_quote_trading_independence():
    d = _doc("research/phase2/integrations/yuanta/PHASE2YH_LOCAL_SDK_FORENSICS_REPORT.md")
    assert "apiquote.yuantafutures.com.tw" in d
    assert "api.yuantafutures.com.tw" in d
    assert "INDEPENDENT_BY_DESIGN" in d


def test_proprietary_sdk_excluded():
    d = _doc("research/phase2/publication/PUBLICATION_EXCLUDE_MANIFEST.txt")
    for token in ("ocx", "YuantaQuote", "YuantaOrd", "YuantaCAPIDLL", "BToCAPI", "元大行情API"):
        assert token.lower() in d.lower()
