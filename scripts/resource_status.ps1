# Phase 2V-F — Resource governor status（只讀）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) { Write-Error "venv python not found"; exit 1 }

& $python -c @"
import json
from market_ai_hub.services.resource_governor import get_governor
g = get_governor()
g.write_status()
print(json.dumps(g.status(), indent=2, default=str))
"@
