"""Phase 2I-B — reconstruction pack / documentation / portability tests。"""
import json
import re
import sys
from pathlib import Path

import yaml
import pytest

sys.path.insert(0, "src")

ROOT = Path(__file__).resolve().parents[1]


def _read(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


def _mcp_tool_names() -> set[str]:
    import asyncio
    from market_ai_hub.mcp.server import mcp

    return {t.name for t in asyncio.run(mcp.list_tools())}


# --- 1/2: manifests ---
def test_system_manifest_valid():
    d = yaml.safe_load(_read("config/system_manifest.yaml"))
    assert d["system"]["build_id"] == "runtime_introspected"  # 動態值不再 hardcode
    assert d["first_class_targets"]["OSAKA_MICRO"]["primary_target"] == "OSE_NIKKEI225_MICRO_FUTURES"
    assert set(d["first_class_targets"]) == {"OSAKA_MICRO", "TAIWAN_STOCK", "TAIWAN_INDEX"}
    assert set(d["target_families"]) == {"OSAKA_MICRO", "TAIWAN_STOCK", "TAIWAN_INDEX"}
    assert d["safety"]["live_trading"] is False
    assert d["automation"]["auto_promote_champion"] is False
    assert d["mcp"]["tool_count"] == 21


def test_capabilities_manifest_valid():
    d = yaml.safe_load(_read("config/capabilities.yaml"))
    assert d["live_trading"]["status"] == "PROHIBITED"
    assert d["yuanta_realtime"]["status"] == "DISABLED"
    assert d["tradingview_bridge"]["status"] == "OPTIONAL_NOT_INSTALLED"
    assert d["osaka_micro_research"]["status"] == "AVAILABLE"


# --- 3/4: MCP JSON ---
def test_mcp_json_valid():
    for f in ("generic-stdio.json", "cherry-studio.json"):
        d = json.loads(_read(f"examples/mcp/{f}"))
        assert "mcpServers" in d and "market-ai" in d["mcpServers"]


def test_mcp_json_no_secret():
    for f in ("generic-stdio.json", "cherry-studio.json"):
        txt = _read(f"examples/mcp/{f}").lower()
        for kw in ("password", "token", "secret", "api_key", "apikey"):
            assert kw not in txt


# --- 5/6: skills ---
def test_skill_files_present():
    for name in ("osaka-micro-analysis", "taiwan-stock-v28", "model-validation-audit"):
        assert (ROOT / "skills" / name / "SKILL.md").exists()


def test_skill_required_mcp_valid():
    tools = _mcp_tool_names()
    for name in ("osaka-micro-analysis", "taiwan-stock-v28", "model-validation-audit"):
        txt = _read(f"skills/{name}/SKILL.md")
        # 每個 skill 提到的 MCP tool 必須真實存在
        mentioned = set(re.findall(r"`([a-z_]+)`", txt))
        for m in mentioned:
            if m.startswith(("get_", "analyze_", "predict_", "health_", "backtest", "run_")):
                assert m in tools, f"{name}: unknown MCP tool {m}"


# --- 7: model manifest / registry consistency ---
def test_model_manifest_registry_consistency():
    man = yaml.safe_load(_read("config/model_manifest.yaml"))["models"]
    reg = yaml.safe_load(_read("config/model_registry.yaml"))["models"]
    reg_names = {m["name"] if isinstance(m, dict) else m for m in reg}
    required = {m["logical_name"] for m in man if m.get("required")}
    # required 可下載模型必在 registry
    assert required <= reg_names, f"manifest required missing in registry: {required - reg_names}"


# --- 8/9: docs no stale values ---
def test_docs_no_stale_tool_count():
    for p in ("README.md", "config/system_manifest.yaml", "docs/reference/MCP_TOOL_REFERENCE.md", "docs/development/project-status.md"):
        txt = _read(p)
        assert "13 tools" not in txt and "13 個 tool" not in txt


def test_docs_no_stale_target():
    txt = _read("README.md")
    assert "OSE Nikkei 225 Micro Futures" in txt
    assert "OSE_NIKKEI225_MICRO_FUTURES" in txt
    # 不得把 ^N225 宣稱為 execution target
    assert "execution target = ^N225" not in txt


# --- 10: docs links exist ---
def test_docs_links_exist():
    readme = _read("README.md")
    links = re.findall(r"\]\(([^)]+)\)", readme)
    for l in links:
        if l.startswith(("http", "#")):
            continue
        target = (ROOT / l.split("#")[0]) if l else None
        assert target is None or target.exists(), f"broken link in README: {l}"


# --- 11/12/13: env / gitignore / license ---
def test_env_example_no_secret():
    txt = _read(".env.example")
    for line in txt.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            val = line.split("=", 1)[1].strip()
            assert val == "", f".env.example has a value: {line}"


def test_gitignore_phase2_data():
    gi = _read(".gitignore")
    for d in ("data/registry", "data/tournament", "data/analysis_archive",
              "data/strategy", "data/feature_store", "data/normalized",
              "data/features", "data/predictions"):
        assert d in gi, f".gitignore missing {d}"


def test_license_present():
    txt = _read("LICENSE")
    assert "Apache License" in txt and "2.0" in txt


# --- 14: reconstruction required files ---
def test_reconstruction_required_files():
    required = [
        "README.md", "config/system_manifest.yaml", "docs/development/AI_RECONSTRUCTION_GUIDE.md",
        "docs/development/project-status.md", "config/model_registry.yaml", "config/model_manifest.yaml",
        "config/capabilities.yaml", "LICENSE", "SECURITY.md", ".env.example", ".gitignore",
        "pyproject.toml", "examples/mcp/generic-stdio.json", "examples/mcp/cherry-studio.json",
        "scripts/download_models.py", "scripts/setup_windows.ps1",
        "scripts/register_research_tasks.ps1", "scripts/unregister_research_tasks.ps1",
        "scripts/reconstruct_verify.ps1", "docs/reference/MCP_TOOL_REFERENCE.md", "docs/concepts/ARCHITECTURE.md",
    ]
    for p in required:
        assert (ROOT / p).exists(), f"missing required file: {p}"
