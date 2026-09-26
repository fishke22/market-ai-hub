"""Phase 2I-B — reconstruction pack / documentation / portability tests。"""
import json
import re
import shutil
import subprocess
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


def test_w7_portability_matrix_keeps_external_gates_unverified():
    d = yaml.safe_load(_read("docs/development/W7_PORTABILITY_ACCEPTANCE.yaml"))
    assert d["schema"] == "W7_PORTABILITY_ACCEPTANCE_V1"
    cells = d["cells"]
    for name in (
        "non_repo_cwd", "external_data_root_cjk_space",
        "fresh_bootstrap_venv_current_windows", "source_backup_restore_different_path",
        "scheduled_tasks_rebind_dry_run", "mcp_client_config_rebind",
    ):
        assert cells[name]["status"] == "PASS"
    for name in (
        "full_dependency_install_fresh_venv", "new_windows_clean_machine",
        "yuanta_wincred_recreation", "yuanta_certificate_reimport",
        "yuanta_com_registration_new_machine",
    ):
        assert cells[name]["status"] == "UNVERIFIED_EXTERNAL_GATE"
    assert cells["private_research_data_consistent_restore"]["status"] == "PASS"
    assert cells["private_research_data_consistent_restore"]["evidence"] == "W7.8"
    assert cells["c2_3_live_runtime_reverification"]["status"] == "WAITING_TIME_WINDOW"
    assert all(cell["status"] != "COMPLETE" for cell in cells.values())


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


def test_render_mcp_config_uses_explicit_relocated_root_from_non_repo_cwd(tmp_path):
    relocated = tmp_path / "新 MCP 路徑" / "MARKET_AI_HUB"
    command = relocated / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / (
        "market-ai-mcp.exe" if sys.platform == "win32" else "market-ai-mcp"
    )
    command.parent.mkdir(parents=True)
    command.write_bytes(b"")
    script = ROOT / "scripts" / "render_mcp_config.py"
    for client in ("generic", "cherry"):
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--client", client,
             "--project-root", str(relocated), "--require-command"],
            cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        server = payload["mcpServers"]["market-ai"]
        assert Path(server["command"]) == command
        assert server["args"] == []
        assert "<PROJECT>" not in result.stdout
        assert str(ROOT) not in result.stdout


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


def test_windows_lock_setuptools_security_floor():
    lock = _read("requirements-lock-windows-x64.txt")
    match = re.search(r"^setuptools==(\d+)\.(\d+)\.(\d+)", lock, re.MULTILINE)
    assert match, "Windows lock must pin setuptools explicitly"
    assert tuple(map(int, match.groups())) >= (83, 0, 0)
    assert "GHSA-5rjg-fvgr-3xxf" in lock
    assert "GHSA-h35f-9h28-mq5c" in lock


def test_ci_pins_node24_actions_and_runner_image():
    workflow = _read(".github/workflows/ci.yml")
    assert "runs-on: ubuntu-24.04" in workflow
    assert "uses: actions/checkout@v7" in workflow
    assert "uses: actions/setup-python@v7" in workflow
    assert "ubuntu-latest" not in workflow
    assert "actions/checkout@v4" not in workflow
    assert "actions/setup-python@v5" not in workflow


# --- 14: reconstruction required files ---
def test_reconstruct_verify_is_independent_of_caller_cwd_and_uses_runtime_build_identity():
    text = _read("scripts/reconstruct_verify.ps1")
    root_idx = text.index("$Root = Split-Path -Parent $PSScriptRoot")
    chdir_idx = text.index("Set-Location -LiteralPath $Root")
    manifest_idx = text.index("open('config/system_manifest.yaml'")
    assert root_idx < chdir_idx < manifest_idx
    assert '$m -eq "runtime_introspected"' in text
    assert "from market_ai_hub.services.build_info import build_fingerprint" in text
    assert '$runtimeBuild -match "^[0-9a-f]{16}$"' in text


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Scheduled Task scripts")
def test_scheduled_task_dry_run_rebinds_to_relocated_repo(tmp_path):
    relocated = tmp_path / "搬移 路徑" / "MARKET_AI_HUB"
    scripts = relocated / "scripts"
    scripts.mkdir(parents=True)
    for name in ("register_research_tasks.ps1", "register_forward_shadow_task.ps1"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    (scripts / "run_daily_forward_cycle.ps1").write_text("# dry-run fixture\n", encoding="utf-8")
    py = relocated / ".venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_bytes(b"")

    research = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(scripts / "register_research_tasks.ps1"), "-DryRun"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert research.returncode == 0, research.stdout + research.stderr
    research_plan = json.loads(research.stdout.lstrip("\ufeff"))
    assert Path(research_plan["repo_root"]) == relocated
    assert len(research_plan["tasks"]) == 2
    assert all(Path(task["working_directory"]) == relocated for task in research_plan["tasks"])
    assert all(str(relocated) in task["execute"] for task in research_plan["tasks"])
    assert str(ROOT) not in research.stdout

    forward = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(scripts / "register_forward_shadow_task.ps1"), "-DryRun"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert forward.returncode == 0, forward.stdout + forward.stderr
    forward_plan = json.loads(forward.stdout.lstrip("\ufeff"))
    assert Path(forward_plan["repo_root"]) == relocated
    assert str(relocated / "scripts" / "run_daily_forward_cycle.ps1") in forward_plan["arguments"]
    assert str(ROOT) not in forward.stdout


def test_forward_shadow_registration_refreshes_existing_path_by_default():
    text = _read("scripts/register_forward_shadow_task.ps1")
    assert "[switch]$DryRun" in text
    assert "[switch]$PreserveExisting" in text
    assert "Register-ScheduledTask" in text and "-Force" in text
    assert "if ($existing -and $PreserveExisting)" in text


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
