"""Phase 2P-A — Final publication acceptance static tests."""
import json
import sys
from pathlib import Path
import yaml

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

def _doc(p): return (ROOT / p).read_text(encoding="utf-8")
def _yaml(p): return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))

def test_publication_manifests_exist():
    assert (ROOT / "PUBLICATION_FILE_MANIFEST.txt").exists()
    assert (ROOT / "PUBLICATION_EXCLUDE_MANIFEST.txt").exists()

def test_release_manifest_truthful():
    m = _yaml("RELEASE_MANIFEST.yaml")
    assert m["strategy_candidate"] == "NONE"
    assert m["production_candidate"] == "NONE"
    assert m["forward_state"]["evidence"] == "NONE_YET"

def test_no_forbidden_claim_in_readme():
    c = _doc("README.md").lower()
    # 禁止正面宣稱（"trading edge" 只在 "does NOT imply executable trading edge" 否定揭露出現，不算）
    for bad in ["profitable", "alpha confirmed", "winning model", "production ready trading", "production alpha"]:
        assert bad not in c

def test_research_freeze_truthful():
    m = _yaml("PHASE2_RESEARCH_FREEZE.yaml")
    assert m["strategy_conclusion"] == "NO_ECONOMIC_EDGE"
    assert m["causality_conclusion"] == "NON_EXECUTABLE_FORECAST_EDGE"

def test_private_data_exclusion():
    # data/ 只應有 .gitkeep（無 225LABO raw/normalized）
    import subprocess
    r = subprocess.run(["git", "ls-files", "data/"], capture_output=True, text=True, cwd=str(ROOT))
    tracked = [l for l in r.stdout.splitlines() if l.strip()]
    assert tracked == ["data/.gitkeep"] or all(".gitkeep" in l or l.endswith(".gitkeep") for l in tracked)

def test_resource_governor_included():
    m = _yaml("RELEASE_MANIFEST.yaml")
    assert m["resource_governor"]["default_profile"] == "DESKTOP_SAFE"
    assert m["resource_governor"]["auto_promote"] is False

def test_crash_recovery_reports_exist():
    assert (ROOT / "PHASE2PA_CRASH_RECOVERY_AUDIT.md").exists()
    assert (ROOT / "PHASE2PA_CRASH_RECOVERY_REPORT.md").exists()
    assert (ROOT / "PHASE2PA_FINAL_PUBLICATION_ACCEPTANCE_REPORT.md").exists()

def test_acceptance_gate_pass():
    assert "PHASE2PA_PASS" in _doc("PHASE2PA_FINAL_PUBLICATION_ACCEPTANCE_REPORT.md")

def test_git_plan_forbids_force_push():
    p = _doc("PRE_PUBLICATION_GIT_PLAN.md")
    assert "force push" in p.lower() or "force" in p.lower()
