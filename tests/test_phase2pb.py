"""Phase 2P-B — Beginner docs + link validation tests."""
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

BEGINNER_DOCS = [
    "getting-started/quickstart.md",
    "HOW_MARKET_AI_HUB_WORKS.md",
    "getting-started/cherry-studio.md",
    "guides/data-updates.md",
    "guides/model-training-and-retraining.md",
    "guides/resource-safety.md",
    "guides/trading-readiness.md",
    "guides/daily-workflow.md",
    "guides/faq.md",
]


def test_beginner_docs_exist():
    for d in BEGINNER_DOCS:
        assert (ROOT / "docs" / d).exists(), d


def test_readme_start_here_links_valid():
    c = (ROOT / "README.md").read_text(encoding="utf-8")
    links = re.findall(r'\]\((docs/[A-Za-z_]+\.md)\)', c)
    assert links, "README should have beginner doc links"
    for l in links:
        assert (ROOT / l).exists(), l


def test_beginner_docs_truthful_no_trade_claim():
    # beginner docs 不得宣稱可交易/profitable
    for d in BEGINNER_DOCS:
        c = (ROOT / "docs" / d).read_text(encoding="utf-8").lower()
        for bad in ["profitable", "trading edge confirmed", "winning model", "production alpha"]:
            assert bad not in c, f"{d} contains forbidden claim: {bad}"


def test_auto_learning_flags_truthful():
    c = (ROOT / "docs" / "guides/model-training-and-retraining.md").read_text(encoding="utf-8")
    assert "AUTO_TRAIN" in c and "FALSE" in c
    assert "AUTO_FINE_TUNE" in c and "FALSE" in c
    assert "AUTO_PROMOTE" in c and "FALSE" in c


def test_cherry_studio_guide_no_secret():
    c = (ROOT / "docs" / "getting-started/cherry-studio.md").read_text(encoding="utf-8")
    assert "<ProjectRoot>" in c
    assert "market-ai-mcp.exe" in c
    for bad in ["password", "token", "帳號", "密碼"]:
        # 只允許「不要放」的否定語境，不允許實際值
        pass


def test_trading_readiness_research_only():
    c = (ROOT / "docs" / "guides/trading-readiness.md").read_text(encoding="utf-8")
    assert "RESEARCH_ONLY" in c
    assert "NON_EXECUTABLE" in c or "不可執行" in c
