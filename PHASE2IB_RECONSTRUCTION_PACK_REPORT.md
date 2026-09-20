# Phase 2I-B — Repository Reconstruction Pack + AI-Readable Documentation + MCP/Skill Portability

- Gate: **PHASE2IB_PASS**
- build_id：`ccabe1e1552d9ae7`（未變，本棒純文件/設定）
- 測試：**356 passed**（342 + 14 2I-B；5 live deselected）

## 交付內容（對照 1–32）

| 項 | 交付 | 狀態 |
|---|---|---|
| SYSTEM_MANIFEST.yaml | machine-readable 系統 manifest | ✅ |
| README.md | 全面重寫（Phase 2，保留 V1 歷史連結） | ✅ |
| AI_RECONSTRUCTION_GUIDE.md | 16 步重建指引 | ✅ |
| ARCHITECTURE.md | Phase 2 架構（interactive vs background） | ✅ |
| MODEL_PIPELINE.md | 模型角色 / price vs direction / 4 層語義 | ✅ |
| AUTOMATED_LEARNING.md | 自動學習白話流程 | ✅ |
| DATA_SOURCE_MATRIX.md | 21 providers 完整矩陣 | ✅ |
| OSAKA_MICRO_ANALYSIS.md | TARGET/REFERENCE/PROXY（2H 已更新） | ✅ |
| MCP_TOOL_REFERENCE.md + export 腳本 | runtime introspection 21 tools | ✅ |
| examples/mcp/ | generic-stdio.json + cherry-studio.json + README | ✅ |
| skills/ | 3 個完整 SKILL.md（可搬移） | ✅ |
| SKILLS_REFERENCE.md | Skill ≠ MCP ≠ LLM | ✅ |
| CLIENT_INTEGRATION_MATRIX.md | TESTED / REFERENCE_ONLY | ✅ |
| INSTALL_WINDOWS.md + setup_windows.ps1 | Phase 2 | ✅ |
| model_manifest/registry | 同步（required 可下載模型一致） | ✅ |
| download_models.py | + --list / --required / --optional | ✅ |
| pyproject / requirements | Phase 2 deps | ✅ |
| .env.example | + BEA/ESTAT/EIA/EDINET（無真實 token） | ✅ |
| SECURITY.md | NO LIVE TRADING / NO ORDER / NO CRED | ✅ |
| .gitignore | + data 各 Phase 2 子目錄 | ✅ |
| THIRD_PARTY_NOTICES.md | code vs weights license 分開 | ✅ |
| LICENSE | Apache-2.0 | ✅ |
| scripts/reconstruct_verify.ps1 | 輕量重建驗證（不下 4GB model） | ✅ |
| config/capabilities.yaml | machine-readable 能力 | ✅ |
| PUBLICATION_FILE_MANIFEST.txt | 預計提交檔案 | ✅ |
| PUBLICATION_EXCLUDE_MANIFEST.txt | 明確不提交項目 | ✅ |
| CURRENT_HANDOFF.md | 更新為 Phase 2 | ✅ |

## 測試（14 新增）
system_manifest_valid / capabilities_manifest_valid / mcp_json_valid / mcp_json_no_secret /
skill_files_present / skill_required_mcp_valid / model_manifest_registry_consistency /
docs_no_stale_tool_count / docs_no_stale_target / docs_links_exist / env_example_no_secret /
gitignore_phase2_data / license_present / reconstruction_required_files。

## Reconstruction verification
`scripts/reconstruct_verify.ps1`：檢查 required files / Python / deps / manifest 有效性 /
MCP 啟動 / tool discovery / skills 存在，不要求下載 optional 4GB models。

## Remaining gaps（誠實揭露）
- OSE Micro per-contract OHLC：CONTRACT_ONLY（官方 xlsx/csv 無，settlement 作 close proxy）。
- BEA / e-Stat / EIA / EDINET：NEEDS_CONFIG。
- JPX investor flow / Fed FOMC JSON / CFTC / MOF：CONTRACT_ONLY。
- Dynamic Ensemble 未 forward-validated（UNVALIDATED_FORWARD）。
- Codex/OpenCode/其他 client：REFERENCE_ONLY（未實測其 MCP 設定）。

## 驗證
- `pytest tests/ -q` → 356 passed
- `python scripts/export_mcp_tool_reference.py` → 21 tools 由 runtime 產生
- build_id 維持 `ccabe1e1552d9ae7`
