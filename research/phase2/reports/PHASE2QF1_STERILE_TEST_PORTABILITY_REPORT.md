# PHASE 2Q-F.1 — Sterile Test Portability Closure + Clean-Room Full-Pytest Truth

- gate：**PHASE2QF1_PASS**（0 Critical / 0 High）
- build_id：`2253d3829253ef59`
- 版本：`v2.0.0-rc1`（不 tag / 不 release）

## 1. Original 6 failures（47/53 semantic subset）

前一棒 2Q-F 的 sterile semantic subset = 47/53。6 failures 逐一分類：

| test node | root cause | classification |
|-----------|-----------|----------------|
| `test_phase2qa::test_restart_same_input_same_direction` | hardcode `ROOT/.venv/Scripts/python.exe` | **E. LOCAL_PATH_ASSUMPTION** |
| `test_phase2qf::test_runtime_outputs_not_project_root` | 當時 clone 是 2Q-F 前舊 code（無 `runtime_paths` 擴充） | **A. TEST_BUG**（測到舊 code） |
| `test_phase2qf::test_resource_governor_status_not_root` | 同上 | **A** |
| `test_phase2qf::test_forward_summary_not_root` | 同上 | **A** |
| `test_phase2qf::test_system_manifest_no_osaka_only_singular_primary` | 同上 | **A** |
| `test_phase2qf::test_lightning_logs_root_resolver` | 同上 | **A** |

註：前 5 個是 2Q-F 已修（新 `runtime_paths` / `first_class_targets`），但當時 clone 是 merge 前舊 main。真正 portability defect 只有 `.venv` hardcode（已修）。

## 2. TRUE full-pytest closure 發現的隱藏狀態（13 → 3 → 0）

真正 clean clone full pytest 逐輪收斂：

| 輪 | 結果 | 問題 |
|----|------|------|
| R1 | 13 failed | 隱藏 state：untracked config/research + local data + log FileNotFoundError |
| R2 | 3 failed | `logs/mcp.log` FileNotFoundError（FileHandler 在 import 後 emit 時開檔，但 clean clone 無 logs/） |
| R3 | **0 failed（772 passed, 20 deselected）** | — |

### 修掉的隱藏狀態（§15/§31/§32）

| 問題 | 修法 |
|------|------|
| `.venv/Scripts/python.exe` hardcode（4 tests） | → `sys.executable`（§8） |
| `market-ai-mcp.exe` hardcode（acceptance + mcp_health） | → `sys.executable -m market_ai_hub.mcp.server` |
| `config/tradingview_symbol_map.json` 未 track | → track（stable public config，移除 .gitignore pattern） |
| Yuanta 報告未 track | → track（research finding，無 PII） |
| `data/strategy/*.csv` / 225LABO parquet / forward status（5 tests） | → `@pytest.mark.private_data`（§10/§13） |
| `logs/mcp.log` FileNotFoundError | → file logging 改在 `main_sync()` 才配置（§5/§38） |
| `http_client.CACHE_ROOT = project_root()/data/cache` | → `data_root()/cache`（§37） |
| 誤 commit `data/backups/`（55 files） | → `git rm --cached` + `data/backups/` gitignore |

## 3. Test profiles（§12/§13）

- `DEFAULT`（addopts `-m 'not live and not optional_model and not private_data and not broker_diagnostic'`）：**772 passed**。
- `optional_model`（Chronos/TimesFM/FinCast smoke，需 GB weights）：deselected。
- `live`（需網路）：deselected。
- `private_data`（225LABO / strategy CSVs / forward status）：deselected。
- `broker_diagnostic` / `optional_integration`：保留供 optional。

## 4. Clean-room full pytest（§2/§4/§14）

- Sterile clone（origin/main，無 .venv/data/models/Yuanta/225LABO/ignored），`MARKET_AI_DATA_ROOT` 指 temp：
  **772 passed, 20 deselected, 122 warnings, 246s**。
- Local 同 profile：**772 passed, 20 deselected**。
- **一致**（§14）。

## 5. MCP / Skills（§37）

sterile clone：21 tools / 3 skills PASS。

## 6. 新增

- `scripts/verify_clean_room.ps1`（一命令：env check / default pytest / tool+skill discovery / docs links / secret scan）。
- `pyproject.toml` markers 擴充（optional_model / optional_integration / private_data / broker_diagnostic）。

## 7. Acceptance（§18）

- sterile clone fresh public env，DEFAULT full pytest PASS。
- local default PASS 一致。
- 21 tools / 3 skills PASS。
- 無 hidden local-state dependency（full suite 在 clean clone 無 data/ 仍 PASS）。
- 0 Critical / 0 High。

## 8. Manual UAT

`MANUAL_CHERRY_UAT = PENDING_USER_CONFIRMATION`（不執行 Cherry GUI UAT）。
