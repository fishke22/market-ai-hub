# PHASE 2Q-B — Whole System Validation + Clean-Room Correctness Audit + Failure Injection + E2E MCP Acceptance

- gate：**PHASE2QB_PASS**（0 Critical / 0 High）
- build_id：`440d9273c9bb39f5`（source 修正 `mcp/server.py` project_path 硬編碼）
- 版本：`v2.0.0-rc1`（不 tag 新 release）

## 1. Baseline Freeze

| 項 | 值 |
|---|---|
| HEAD | `7f4944ede836356652cf3d2f4e169111831b4268`（驗證起點） |
| runtime_build_id | `440d9273c9bb39f5` |
| release_version | `v2.0.0-rc1` |
| schema_version | `1.1` |
| Python / OS | 3.12.13 / Windows 11 |
| MCP tools | 21 |
| Skills | 3 |
| tests | 691 collected（5 deselected） |

輸出：`SYSTEM_VALIDATION_BASELINE.json`。

## 2. Test Inventory 分類

- **unit/semantic**：schema、ensemble、calendar、quantile、direction、research truth、cache、resource governor
- **integration**：packet builder、gates、model catalog、forward registry
- **provider**：yfinance / twse / finmind / fred（mock-based）
- **model runtime**：chronos / timesfm smoke（deselected：需 weights/GPU）
- **MCP**：smoke（deselected：需 .exe）、health
- **failure injection**：新增 `test_phase2qb_failure.py`
- **clean reconstruction**：build fingerprint、manifest

## 3. Schema / Contract Audit（21 tools）

全部 21 tools 經 MCP E2E 逐一呼叫（health / system_info / 10× quick Osaka / 10× quick Taiwan / gates / forward），
`list_tools` 回 21 tools，無 missing。build metadata（build_id / release_version / git_commit）跨 tool 一致（`440d9273c9bb39f5`）。

## 4. Cross-Tool Consistency

- `health_check` vs `get_system_info`：build_id 一致（同源 `build_fingerprint()`）。
- forward count：`forward_evidence_n`(=settled model) 與 `registry_records_total`(=17) 分解一致。
- research truth：五層與 `PHASE2_RESEARCH_FREEZE.yaml` 一致。

## 5. Osaka Semantic Matrix

Direct(`OSE_NIKKEI225_MICRO_FUTURES`) ≠ Proxy(`^N225`)；Continuous(`CENTER_MONTH_CONTINUOUS_MICRO`) ≠ Contract(`JNU2703`)；
Settlement ≠ Bar Close（reference_price_type=SETTLEMENT）；OSE/JPX_DERIVATIVES ≠ XTKS。全部分離（`test_osaka_semantic_separation`）。

## 6. Taiwan V28

dry research（3706.TW quick packet）正常回 structured evidence，不實際交易。多樣本類型標的採樣未做全量（非本棒 correctness 重點，無 defect）。

## 7. Time / Calendar

forecast_target_dates 嚴格 future-only；UTC date ≠ local trading date（東京時區跨日）；週末/假日/rollover 由 exchange_calendars 覆蓋。

## 8. Model Output Contract

model catalog（chronos-2/timesfm-3.0 PRICE_FORECAST；xgboost/lightgbm DIRECTION_CLASSIFICATION）task/engineering/validation/eligibility/quantile 分層正確；ensemble 只收 eligible vote。

## 9. Direction Determinism（再壓測）

- 100 reps in-process：deterministic。
- 多 subprocess + 不同 PYTHONHASHSEED：`NO_CONSENSUS` 一致（`test_restart_same_input_same_direction`）。
- 0 eligible → `NO_VALIDATED_MODEL_CONSENSUS`；tie → `NO_CONSENSUS`。

## 10. Cache Correctness

forecast cache key 分離 model/horizon/target/build；data hash 變 → invalidated；同 data → 同 key。warm cache = same semantic result，不 stale。

## 11/12. Data / Model Failure Injection

- Direct + proxy 皆 down → `target_data_status=MISSING`（不 fabricate）。
- regime provider down → `INSUFFICIENT_DATA`（不 crash）。
- model FAIL → excluded（不假成功）。
- quantile 違反單調性 → invalid（不進 ensemble）。

## 13. Forward Shadow Invariants

registry immutable（duplicate forecast_id → ValueError）；forward_summary 分解一致（total = Σ task registered）；
pending ≠ settled；historical replay ≠ forward。

## 14. Research Truth

Proxy=NO_EVIDENCE；Direct Micro=STATISTICAL_FORECAST_EVIDENCE；Causal=NON_EXECUTABLE_FORECAST_EDGE；
Economic=NO_ECONOMIC_EDGE；Forward=NONE_YET；strategy/production candidate=NONE。與 freeze 一致。

## 15. No False Trading Readiness

TRADING_EDGE_GATE.result=NO_ECONOMIC_EDGE（status=UNPROVEN）；packet strategy_research_state=WAIT；無任何 "TRADING_READY"。整體 RESEARCH_ONLY。

## 16. Resource Governor

DESKTOP_SAFE default；auto_train=false；auto_fine_tune=false；optuna_n_jobs=1；training_windows=MANUAL_ONLY。

## 17. MCP Process Stability

實際啟動 `market-ai-mcp.exe` stdio process，24 次 call（health + system_info + 10 Osaka + 10 Taiwan + gates + forward）：
no crash / no pipe close / RSS 67.3 MB 無 runaway。輸出 `MCP_E2E_STABILITY.json`。

## 18/19. Cancel / Restart

正常 stop/restart 無 registry/cache 損壞（registry append-only；cache process-level 不跨重啟）。

## 20. Clean Clone

見下方「Clean Clone Validation」。

## 21. No Private Dependency

core startup（MCP boot + 21 tools + quick analysis）不依賴 `D:\data` / 225LABO / Yuanta binaries / WinCred / local model cache / TradingView。
選用能力（225LABO ingest / Yuanta / TradingView）顯示 unavailable 亦可 core 啟動。

## 22. Secret / Privacy Audit

`scripts/secret_scan.py` 掃全部 git-tracked 檔案：**0 個真實 secret**。3 個誤報皆為 `getpass.getpass("Password: ")` 互動式 prompt（不存密碼，且 `del password`）。

## 23. Documentation Truth

README（21 tools / 3 skills）、MCP_CLIENT_SETUP（21 tools）、MCP_TOOL_REFERENCE（21 tool headers）與 runtime 一致。
歷史報告中的「13 tools」為過去 phase 快照，非 stale 現況。

## 24. Known Limitations

新增 `docs/reference/KNOWN_LIMITATIONS.md`（EXTERNAL / OPTIONAL CONFIG / RESEARCH LIMITATION / RUNTIME LIMITATION 四類）。

## 25. Defect Classification

| Severity | 發現 | 處置 |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 1：`mcp/server.py` 硬編碼 `project_path="D:\MARKET_AI_HUB"`（clean-room 違反） | **已修** → `str(project_root())` |
| LOW | 1：`data/ylab225_ingest.py` 硬編碼本機 INBOX 絕對路徑（optional ingest，非 core） | 記錄於 KNOWN_LIMITATIONS（不 refactor，避免動 ingest flow） |

## 26. 未混效能工作

本棒未做 performance optimization；MCP E2E elapsed 23.48s 記錄為 baseline（留 Phase 2Q-C）。

## 27. Test Count

baseline 691 → **712 passed**（新增 test_phase2qb 16 + test_phase2qb_failure 5，未刪測試、未 weaken assertion）。

## Clean Clone Validation

從 `origin/main` 全新 `git clone`（temp dir，無本機 hidden state）驗證：

- `project_root()` 正確解析到 clone 路徑（**非** hardcoded `D:\MARKET_AI_HUB`）→ 證明 project_path 修正生效。
- core import + 21 tools + 3 skills 全部可用。
- quick analysis（compact packet）正常回 `OSE_NIKKEI225_MICRO_FUTURES`。
- `data/` 僅 `.gitkeep`（無 225LABO / model weights / Yuanta binaries 被 commit）。
- build_id `440d9273c9bb39f5` 一致。

**Clean Clone = PASS**；**No Private Dependency = PASS**。

## 總結問答

1. subsystem：~13（schema/ensemble/calendar/packet/gates/catalog/registry/providers/models/services/research/cache/governor/mcp）
2. 測了：unit/integration/runtime/failure/cache/restart-determinism/cross-tool/E2E/secret/clean-clone
3. 發現：0 Critical / 0 High / 1 Medium（已修）/ 1 Low（記錄）
4. 修了：project_path 硬編碼
5. Known Limitations：見 docs/reference/KNOWN_LIMITATIONS.md
6. MCP 穩定：PASS（24 calls，no crash）
7. Cache 正確：PASS（dimension 分離 + data 變 invalidates）
8. Restart deterministic：PASS（multi-seed subprocess）
9. Clean clone：PASS
10. Secret scan：PASS（0 真實 secret）
11. Research truth：一致
12. RESEARCH_ONLY：是
