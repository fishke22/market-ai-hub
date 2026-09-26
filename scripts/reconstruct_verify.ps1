# MARKET_AI_HUB — Reconstruction verification（模擬新電腦 clone 後的輕量驗證）
# 不要求下載 optional 4GB models 才能 PASS。
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$fail = 0

function Check($cond, $msg) {
  if ($cond) { Write-Host "  [OK]   $msg" } else { Write-Host "  [FAIL] $msg"; $script:fail++ }
}

Write-Host "== required files =="
$required = @(
  "README.md", "config/system_manifest.yaml", "docs/development/AI_RECONSTRUCTION_GUIDE.md",
  "docs/development/project-status.md", "config/model_registry.yaml", "config/model_manifest.yaml",
  "config/capabilities.yaml", "LICENSE", "SECURITY.md", ".env.example", ".gitignore",
  "pyproject.toml", "requirements-runtime.txt",
  "examples/mcp/generic-stdio.json", "examples/mcp/cherry-studio.json",
  "skills/osaka-micro-analysis/SKILL.md", "skills/taiwan-stock-v28/SKILL.md",
  "skills/model-validation-audit/SKILL.md",
  "scripts/download_models.py", "scripts/setup_windows.ps1",
  "scripts/register_research_tasks.ps1", "scripts/unregister_research_tasks.ps1",
  "docs/reference/MCP_TOOL_REFERENCE.md", "docs/concepts/ARCHITECTURE.md"
)
foreach ($f in $required) {
  Check (Test-Path (Join-Path $Root $f)) "file: $f"
}

Write-Host "== Python =="
$py = Join-Path $Root ".venv\Scripts\python.exe"
Check (Test-Path $py) "venv python exists"
if (Test-Path $py) {
  $ver = & $py -c "import sys; print(sys.version.split()[0])" 2>$null
  Check ($ver -match "3\.1[12]") "python version $ver"
}

Write-Host "== dependencies =="
if (Test-Path $py) {
  $ok = & $py -c "import pandas, numpy, duckdb, pydantic, httpx, pyarrow; print('ok')" 2>$null
  Check ($ok -eq "ok") "core dependencies importable"
}

Write-Host "== SYSTEM_MANIFEST + runtime identity =="
if (Test-Path $py) {
  $m = & $py -c "import yaml; d=yaml.safe_load(open('config/system_manifest.yaml',encoding='utf-8')); print(d['system']['build_id'])" 2>$null
  Check ($m -eq "runtime_introspected") "config/system_manifest.yaml build_id uses runtime introspection sentinel"
  $runtimeBuild = & $py -c "from market_ai_hub.services.build_info import build_fingerprint; print(build_fingerprint()['build_id'])" 2>$null
  Check ($runtimeBuild -match "^[0-9a-f]{16}$") "runtime build fingerprint valid; build_id=$runtimeBuild"
  $c = & $py -c "import yaml; d=yaml.safe_load(open('config/capabilities.yaml',encoding='utf-8')); print(d['live_trading']['status'])" 2>$null
  Check ($c -eq "PROHIBITED") "capabilities.yaml live_trading=PROHIBITED"
}

Write-Host "== MCP startup + tool discovery =="
if (Test-Path $py) {
  $tc = & $py -c "import sys,asyncio; sys.path.insert(0,'src'); from market_ai_hub.mcp.server import mcp; n=asyncio.run(mcp.list_tools()); print(len(n))" 2>$null
  Check ($tc -ge 21) "MCP tools discovered: $tc"
}

Write-Host ""
if ($fail -gt 0) {
  Write-Host "RESULT: FAIL ($fail checks failed)"
  exit 1
}
Write-Host "RESULT: PASS"
