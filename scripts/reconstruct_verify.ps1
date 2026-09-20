# MARKET_AI_HUB — Reconstruction verification（模擬新電腦 clone 後的輕量驗證）
# 不要求下載 optional 4GB models 才能 PASS。
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$fail = 0

function Check($cond, $msg) {
  if ($cond) { Write-Host "  [OK]   $msg" } else { Write-Host "  [FAIL] $msg"; $script:fail++ }
}

Write-Host "== required files =="
$required = @(
  "README.md", "SYSTEM_MANIFEST.yaml", "docs/AI_RECONSTRUCTION_GUIDE.md",
  "CURRENT_HANDOFF.md", "config/model_registry.yaml", "config/model_manifest.yaml",
  "config/capabilities.yaml", "LICENSE", "SECURITY.md", ".env.example", ".gitignore",
  "pyproject.toml", "requirements-runtime.txt",
  "examples/mcp/generic-stdio.json", "examples/mcp/cherry-studio.json",
  "skills/osaka-micro-analysis/SKILL.md", "skills/taiwan-stock-v28/SKILL.md",
  "skills/model-validation-audit/SKILL.md",
  "scripts/download_models.py", "scripts/setup_windows.ps1",
  "scripts/register_research_tasks.ps1", "scripts/unregister_research_tasks.ps1",
  "docs/MCP_TOOL_REFERENCE.md", "docs/ARCHITECTURE.md"
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

Write-Host "== SYSTEM_MANIFEST validity =="
if (Test-Path $py) {
  $m = & $py -c "import yaml; d=yaml.safe_load(open('SYSTEM_MANIFEST.yaml',encoding='utf-8')); print(d['system']['build_id'])" 2>$null
  Check ($m -match "^[0-9a-f]{16}$") "SYSTEM_MANIFEST.yaml valid; build_id=$m"
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
