# MARKET_AI_HUB - read-only agent bootstrap.
# Prints ACTUAL repo facts (branch / HEAD / origin / status / build_id / V2 schemas / phase / providers).
# Never writes, never mutates, never prints secrets.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

function Show($label, $value) { Write-Host ("{0}: {1}" -f $label, $value) }

Write-Host "=== repo ==="
Show "branch" (git rev-parse --abbrev-ref HEAD)
Show "HEAD" (git rev-parse HEAD)
Show "origin/main" (git rev-parse origin/main)
Write-Host "git status --short:"
git status --short

Write-Host ""
Write-Host "=== runtime identity (read-only) ==="
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }
$env:PYTHONPATH = Join-Path $Root "src"
& $py -B -c "import json; from market_ai_hub.services.build_info import build_fingerprint; from market_ai_hub.research.v2.prediction_audit import v2_schema_versions; from market_ai_hub.integrations.yuanta.capabilities import PROVIDER_STATUS; fp = build_fingerprint(); print('build_id:', fp['build_id']); print('v2_schemas:', json.dumps(v2_schema_versions(), sort_keys=True)); print('providers:', json.dumps(PROVIDER_STATUS, sort_keys=True))"

Write-Host ""
Write-Host "=== current phase ==="
Get-Content -LiteralPath (Join-Path $Root "docs\development\project-status.md") -Encoding UTF8 |
  Select-String -Pattern "^\- (Current phase|Gate|build_id|Schemas)" | Select-Object -First 4 |
  ForEach-Object { $_.Line }

Write-Host ""
Write-Host "=== read next ==="
@(
  "AGENTS.md",
  "docs/development/AGENT_HANDOFF.md",
  "docs/development/project-status.md",
  "docs/architecture/v2-prediction-audit-contract.md",
  "docs/architecture/v2-session-factor-routing-contract.md",
  "docs/integrations/yuanta/YUANTA_LIVE_MULTIFACTOR_GUIDE_ZH_TW.md",
  "docs/integrations/yuanta/YUANTA_FROM_SCRATCH_SETUP_ZH_TW.md",
  "docs/integrations/yuanta/YUANTA_PRODUCT_CODE_AND_SESSION_RULES_ZH_TW.md",
  "config/yuanta_source_manifest.yaml",
  "config/yuanta_live_factor_matrix.yaml"
) | ForEach-Object { Show "read" $_ }
