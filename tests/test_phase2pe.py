"""Phase 2P-E — System Prompt compaction regression tests."""
import sys
from pathlib import Path

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

COMPACT = (ROOT / "docs" / "prompts" / "SYSTEM_PROMPT_V4_1_COMPACT.md").read_text(encoding="utf-8")
V4 = (ROOT / "docs" / "prompts" / "SYSTEM_PROMPT_V4_PHASE2_RC1.md").read_text(encoding="utf-8")


def test_direct_vs_proxy():
    assert "Direct != Proxy" in COMPACT
    assert "PROXY" in COMPACT and "N/A" in COMPACT


def test_eligible_votes_zero():
    assert "eligible_direction_vote_count = 0" in COMPACT
    assert "無有效模型方向共識" in COMPACT


def test_uncalibrated_score():
    assert "probability_calibrated=false" in COMPACT.replace(" ", "")
    assert "原始分類分數偏向" in COMPACT


def test_historical_not_forward():
    assert "Historical replay" in COMPACT and "Forward" in COMPACT
    assert "Historical" in COMPACT and "Forward" in COMPACT


def test_statistical_not_trading_edge():
    assert "Historical statistical evidence" in COMPACT
    assert "trading signal" in COMPACT or "trading edge" in COMPACT


def test_continuous_not_contract():
    assert "Continuous != Contract" in COMPACT
    assert "中心限月連續研究序列" in COMPACT


def test_bar_close_not_settlement():
    assert "Bar Close != Settlement" in COMPACT


def test_no_edge_allowed():
    assert "NO_EDGE" in COMPACT
    assert "WAIT" in COMPACT and "RESEARCH_ONLY" in COMPACT


def test_runtime_truth_overrides_stale_prompt():
    assert "Runtime" in COMPACT
    assert "優先" in COMPACT


def test_skill_routing():
    assert "osaka-micro-analysis" in COMPACT
    assert "taiwan-stock-v28" in COMPACT
    assert "model-validation-audit" in COMPACT


def test_compact_marked_recommended_and_v4_full_reference():
    assert "RECOMMENDED" in COMPACT
    assert "FULL REFERENCE" in V4
    assert "V4_1_COMPACT.md" in V4  # V4 連到 compact


def test_compact_does_not_hardcode_dynamic_facts():
    # compact 不得 hardcode forward N / build_id 作 authoritative / leaderboard
    assert "NONE_YET" not in COMPACT
    assert "get_forward_test_status" in COMPACT
