"""Phase 2V-B.2 — Local OSE Micro data provenance static tests."""
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


MANIFEST = _yaml("research/phase2/manifests/LOCAL_OSE_DATA_PROVENANCE_MANIFEST.yaml")
REPORT = _doc("research/phase2/reports/PHASE2VB2_LOCAL_MICRO_PROVENANCE_REPORT.md")
DRAFT = _yaml("research/phase2/protocols/drafts/DIRECT_MICRO_BAR_OOS_PROTOCOL_DRAFT.yaml")


def test_micro_no_data_before_listing():
    listing = MANIFEST["micro_listing_date"]
    assert listing == "2023-05-29"
    for ds in MANIFEST["datasets"]:
        if "microf" in ds["dataset"]:
            assert ds["first_date"] >= "2023-05-29"
    assert MANIFEST["summary"]["pre_listing_micro_rows"] == 0


def test_prelisting_micro_reclassified():
    # 上市前 Micro 不得存在；若存在須重新分類（本棒驗證無 pre-listing）
    assert MANIFEST["summary"]["pre_listing_micro_rows"] == 0
    assert "0 筆上市前資料" in REPORT


def test_micro_and_mini_not_blindly_merged():
    d = MANIFEST["micro_mini_duplication"]
    assert d["volume_exact_match_rate"] < 0.1  # volume 差異極大 → 非同一契約
    assert "INDEPENDENT" in d["conclusion"]
    # Mini 為 REFERENCE_ONLY，非 direct
    for ds in MANIFEST["datasets"]:
        if "minif" in ds["dataset"]:
            assert ds["import_status"] == "REFERENCE_ONLY"


def test_bar_close_not_settlement():
    for ds in MANIFEST["datasets"]:
        if "microf" in ds["dataset"]:
            assert ds["close_semantics"] == "BAR_CLOSE"
    assert DRAFT["target"]["semantic"] == "NEXT_SESSION_BAR_CLOSE"
    assert "NEXT_SETTLEMENT" in DRAFT["target"]["forbidden_mislabels"]


def test_micro_tick_size_checked():
    assert MANIFEST["micro_tick_size"] == 5
    for ds in MANIFEST["datasets"]:
        if "microf" in ds["dataset"]:
            assert ds["tick_size_validated"] is True


def test_micro_timezone_verified():
    for ds in MANIFEST["datasets"]:
        if "microf" in ds["dataset"]:
            assert ds["timezone"] == "Asia/Tokyo (JST)"
    assert MANIFEST["session"]["validation"] == "PASS (matches OSE session structure exactly)"


def test_micro_volume_semantics():
    for ds in MANIFEST["datasets"]:
        if "microf" in ds["dataset"]:
            assert ds["volume_semantics"] == "PER_MINUTE_CONTRACT_VOLUME"


def test_local_data_provenance_required():
    # 每個 dataset 必須有 authority + import_status，不得只看檔名
    for ds in MANIFEST["datasets"]:
        assert ds.get("authority"), ds["dataset"]
        assert ds.get("import_status"), ds["dataset"]


def test_unverified_data_not_direct_target():
    # 僅 VERIFIED_OSE_MICRO 可當 direct；unverified 不得
    for ds in MANIFEST["datasets"]:
        if ds["import_status"] != "VERIFIED_OSE_MICRO":
            assert ds["import_status"] in ("REFERENCE_ONLY", "UNVERIFIED", "REJECTED_PRE_LISTING")


def test_raw_data_immutable():
    # raw source 不搬動；manifest 只記錄 source_path + hash，非複製
    assert "READ-ONLY" in REPORT
    for ds in MANIFEST["datasets"]:
        assert ds["source_path"].startswith("D:\\data")


def test_normalized_data_has_source_hash():
    # import 需保存 source hash（manifest 已含 sha256）
    for ds in MANIFEST["datasets"]:
        if "microf" in ds["dataset"]:
            assert len(ds.get("sha256", "")) >= 16


def test_direct_settlement_and_bar_exams_separate():
    assert DRAFT["separate_from_settlement_exam"] is True
    assert DRAFT["settlement_exam_status"] == "DIRECT_SETTLEMENT_INSUFFICIENT"
    assert "DIRECT_SETTLEMENT_INSUFFICIENT" in REPORT
    assert "DIRECT_MICRO_BAR_OOS_POSSIBLE" in REPORT
