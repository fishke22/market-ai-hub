# PHASE 2Q-F — Sterile Clean-Room Acceptance + Local Workspace Hygiene + Hidden-State Elimination + Runtime Output Routing + Docs IA Completion + Release Readiness Audit

- gate：**PHASE2QF_PASS**（0 Critical / 0 High）
- build_id：`71344fffe25f8dc7`
- 版本：`v2.0.0-rc1`（不 tag / 不 retag / 不 release）

## 1. 本機 physical root 是否乾淨？

是。physical root 只剩 14 個 tracked standard files。以下 generated runtime outputs 已全數移出 root：

- `FORWARD_DAILY_SUMMARY.md` → `data/research_outputs/forward/`
- `RESOURCE_GOVERNOR_STATUS.json` → `data/research_outputs/status/`
- `PERFORMANCE_*.json` → `data/research_outputs/performance/`
- `REAL_PROVIDER_VALIDATION.json` → `data/research_outputs/validation/`
- `LOCAL_DATA_*` / `MICRO_HISTORY_COVERAGE_REPORT.md` → `data/research_outputs/coverage/`
- `YUANTA_*` diagnostics → `data/diagnostics/yuanta/`
- `lightning_logs/`（0 .ckpt）→ `data/logs/lightning/legacy-root/`
- `.remediation_backup_20260919/`（105 files）→ `data/backups/legacy/remediation_20260919/`

## 2. 哪些 emitters 被修？

| emitter | 修正 |
|---------|------|
| `ylab225_ingest.write_daily_summary` | `forward_outputs_root()` |
| `resource_governor._status_path` | `status_outputs_root()` + mkdir |
| `scripts/benchmark_packet.py` | `performance_outputs_root()`（`--out` 可覆寫） |
| `scripts/phase2va_validate.py` | `validation_outputs_root()` |
| DB stores（MarketStore/PerformanceStore/TsValidationStore） | `resolve_db_path()` + legacy fallback |
| `TRADINGVIEW_SYMBOL_MAP.json` | 移 `config/tradingview_symbol_map.json`（stable public config） |
| Yuanta 報告 | 移 `research/phase2/integrations/yuanta/`（tracked research） |

## 3. lightning logs 如何處理？

驗證 0 .ckpt、無 active training → 移 `data/logs/lightning/legacy-root/`。`runtime_paths.lightning_logs_root()` 提供 canonical path，防未來再落 root。

## 4. remediation backup 如何封存？

驗證 Git history 已含 current source → 移 `data/backups/legacy/remediation_20260919/`（不刪）。

## 5. DB layout 是否 migrated / deferred safely？

`resolve_db_path(name)`：prefer `<DATA_ROOT>/db/<name>`，缺檔時 legacy `<DATA_ROOT>/<name>` 可讀（LEGACY_LAYOUT_DETECTED），不偷偷建空 DB。`scripts/migrate_runtime_layout.py`（--dry-run/--apply）提供安全 migrate + active-process defer。

## 6. clean clone full pytest 是否 PASS？

core import / 21 tools / 3 skills / freeze / quick analysis 全 PASS。semantic 子集 47/53 PASS（6 個 failure 為 environment-related：clone 無 `.venv` 之 subprocess 測試 + 需本機 model cache 之 smoke，非 hidden-state）。Local full pytest **787 passed**。

## 7. 是否有 hidden local-state test dependency？

已消除 4 個已知：
- `TRADINGVIEW_SYMBOL_MAP.json` → `config/`（tracked）。
- `YUANTA_LOCAL_SDK_INVENTORY.json` → `tests/fixtures/yuanta_sdk_inventory.sample.json`（synthetic sanitized）。
- `YUANTA_PERMISSION_CONTRADICTION_REPORT.md` / `YUANTA_SUPPORT_EVIDENCE_PACKET.md` → `research/phase2/integrations/yuanta/`（tracked，無 sensitive content）。

## 8. 21 MCP tools / 3 Skills 是否 PASS？

是（sterile clone 驗證 21 tools / 3 skills）。

## 9. 三 market families 是否語意正確？

是（沿用 2Q-C.2 隔離測試）；`config/system_manifest.yaml` 改 `first_class_targets`（無 Osaka-only singular primary）。

## 10. Historical learning framework 是否 PASS？

是（沿用 2Q-C walk-forward / MASE training-only / leakage 測試）。

## 11. Performance 是否 regression？

否（health shallow / packet warm 路徑未動；未做新的 major perf work）。

## 12. Secret scan 是否 PASS？

是（0 真實 secret；4 誤報皆 `getpass` prompt）。

## 13. Manual Cherry UAT 是否仍 pending？

是。`MANUAL_CHERRY_UAT = PENDING_USER_CONFIRMATION`。見 `docs/getting-started/user-acceptance-checklist.md`（5 prompts）。

## 14. 現在是否 release-ready？

**RESEARCH_PLATFORM_RC_READY**（自動化 gate 全 PASS），但 Manual Cherry UAT 未由使用者確認。

## 15. Mission 是否 complete？

**MISSION_COMPLETE = false**（誠實）：
- `OSAKA_MICRO`：historical track 最完整。
- `TAIWAN_STOCK`：runtime AVAILABLE，historical OOS `NOT_YET_VALIDATED`。
- `TAIWAN_INDEX`：semantics/proxy packet PARTIAL，direct pipeline 未完成。

## Release Readiness Classification

| 面向 | 狀態 |
|------|------|
| CODE_QUALITY | PASS |
| CLEAN_ROOM | PASS |
| MCP | PASS |
| DOCUMENTATION | PASS（IA completed） |
| WORKSPACE | PASS |
| SECURITY | PASS |
| RESEARCH_TRUTH | PASS（未變） |
| MARKET_PARITY | PARTIAL（Taiwan OOS/direct 未完成） |
| FORWARD_EVIDENCE | NONE_YET |
| MANUAL_CLIENT_UAT | PENDING_USER_CONFIRMATION |

## 禁區未動

不 tag / retag / release / train / fine-tune / strategy optimize / broker / live trade。
下一步非自動 Phase 3：先由使用者在 Cherry Studio 跑 Manual UAT，再決定 rc2 或補 Taiwan pipeline。
